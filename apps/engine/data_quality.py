"""Data quality and lineage helpers for ALM inputs and generated outputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Count, Max, Min, Sum
from django.http import Http404

from apps.inputs.models import INPUT_LABELS, INPUT_MODELS, Output
from apps.tracking.models import Tracking


@dataclass(frozen=True)
class InputLineageConfig:
    output_type: str | None
    amount_field: str | None
    date_field: str | None


LINEAGE_CONFIG: dict[str, InputLineageConfig] = {
    "credit": InputLineageConfig("credit", "capital_restant", "date_deu_echeance"),
    "terme": InputLineageConfig("pret_ter_cor", "montant", "maturite"),
    "decouvert": InputLineageConfig("decouvert", "montant", "date_fin"),
    "bta": InputLineageConfig("bta", "solde", "maturite"),
    "ota": InputLineageConfig("ota", "solde", "maturite"),
    "emprunt_obl": InputLineageConfig("emprunt_obl", "solde", "maturite"),
    "tab_amort": InputLineageConfig(None, "amort_calcul", "date_echeance"),
    "pret_cor": InputLineageConfig("pret_cor", "capital_restant", "date_dern_echeance"),
    "pret_inter_banc": InputLineageConfig("inter_blanc", "solde", "maturite"),
    "beac": InputLineageConfig("beac", "cumul", "date"),
    "pret_titre": InputLineageConfig("pret_titre", "montant", "date_echeance"),
    "billet": InputLineageConfig("billet", "solde", "date"),
    "cpte_corr": InputLineageConfig("compte_vue_cor", "cumul", "date"),
    "depot_terme": InputLineageConfig("depot_terme", "montant", "maturite"),
    "bon_caisse": InputLineageConfig("bon", "montant", "maturite"),
    "pension_livree": InputLineageConfig("pension_livree", "montant", "echeance"),
    "emprunt_inter": InputLineageConfig("emprunt_inter_banc", "montant", "echance"),
    "emprunt_inter_banc": InputLineageConfig(None, "principal", "date_pro_echeance"),
    "compte_courant": InputLineageConfig("compte_371", "cumul", "date"),
    "compte_cheque": InputLineageConfig("compte_372", "cumul", "date"),
    "compte_livret": InputLineageConfig("compte_373", "cumul", "date"),
    "avance_beac": InputLineageConfig("avance_beac", "montant_total_rembourse", "echeance"),
    "emprunt_titre": InputLineageConfig("emprunt_titre", "montant_total_rembourse", "echeance"),
}

TRANSFORMATION_NOTES: dict[str, str] = {
    "credit": "Le moteur projette les remboursements futurs du capital restant; le total moteur ne correspond donc pas toujours au stock brut source.",
    "terme": "Les prêts à terme sont ventilés sur les échéances futures, avec la logique de maturité utilisée par le moteur.",
    "decouvert": "Les découverts peuvent intégrer intérêts et date de fin; un léger écart peut être normal.",
    "bta": "Les titres sont projetés par maturité; l'écart est attendu si le moteur ajoute ou exclut des flux selon la date de référence.",
    "ota": "Les titres sont projetés par maturité et peuvent intégrer des coupons/intérêts.",
    "emprunt_obl": "Les emprunts obligataires sont projetés avec principal et intérêts/coupons; le moteur peut donc dépasser le solde source.",
    "tab_amort": "Cette feuille sert de support d'amortissement et n'a pas d'output moteur direct.",
    "pret_cor": "Les prêts correspondants sont projetés selon les échéances futures, pas rapprochés comme un stock simple.",
    "pret_inter_banc": "Les prêts interbancaires sont projetés dans l'output inter_blanc selon leur maturité.",
    "beac": "Le champ source est un cumul historique; le moteur retient une position/projection BEAC exploitable pour les buckets ALM.",
    "pret_titre": "Les prêts titres sont projetés par date d'échéance et peuvent être absents si aucune ligne n'entre dans la fenêtre moteur.",
    "billet": "La caisse est reprise comme liquidité immédiate; elle doit généralement se rapprocher directement.",
    "cpte_corr": "Les comptes à vue correspondent à des soldes comportementaux; le moteur applique des hypothèses de stabilité/retrait.",
    "depot_terme": "Les dépôts à terme sont ventilés par maturité et scénarios de retrait.",
    "bon_caisse": "Les bons de caisse sont projetés à maturité, avec remboursement et coût associé selon le moteur.",
    "pension_livree": "Les pensions livrées sont projetées à échéance.",
    "emprunt_inter": "Les emprunts interbancaires sont projetés par échéance dans le moteur.",
    "emprunt_inter_banc": "Cette feuille de détail peut servir de source sans output direct selon le mapping actuel.",
    "compte_courant": "Les comptes courants sont des dépôts comportementaux; le moteur applique les hypothèses de retrait.",
    "compte_cheque": "Les comptes chèques sont des dépôts comportementaux; le moteur applique les hypothèses de retrait.",
    "compte_livret": "Les comptes livrets sont des dépôts comportementaux; le moteur applique les hypothèses de retrait.",
    "avance_beac": "Les avances BEAC sont projetées à échéance; un output nul signale souvent une ligne hors fenêtre ou un mapping à vérifier.",
    "emprunt_titre": "Les emprunts titres sont projetés à échéance; un output nul signale souvent une ligne hors fenêtre ou un mapping à vérifier.",
}

DIRECT_RECONCILIATION_KINDS = {"billet"}
SOURCE_ONLY_KINDS = {"tab_amort", "emprunt_inter_banc"}

EXPECTED_TRANSFORMATION_KINDS = {
    "credit",
    "terme",
    "decouvert",
    "bta",
    "ota",
    "emprunt_obl",
    "pret_cor",
    "pret_inter_banc",
    "beac",
    "pret_titre",
    "cpte_corr",
    "depot_terme",
    "bon_caisse",
    "pension_livree",
    "emprunt_inter",
    "compte_courant",
    "compte_cheque",
    "compte_livret",
    "avance_beac",
    "emprunt_titre",
}

STATUS_SEVERITY = {
    "ok": "ok",
    "empty": "info",
    "source_only": "info",
    "transformed": "info",
    "out_of_window": "warning",
    "mapping_review": "warning",
    "review": "warning",
    "missing_output": "error",
}


def _sum_abs(model, field_name: str | None) -> float:
    if not field_name:
        return 0.0
    value = model.objects.aggregate(total=Sum(field_name))["total"] or 0
    return float(abs(value))


def _date_bounds(model, field_name: str | None) -> tuple[Any, Any]:
    if not field_name:
        return None, None
    bounds = model.objects.aggregate(first=Min(field_name), last=Max(field_name))
    return bounds["first"], bounds["last"]


def _model_fields(model) -> list[str]:
    return [
        field.name
        for field in model._meta.fields
        if not field.name.startswith("_")
    ]


def _preview_rows(queryset, fields: list[str], limit: int) -> list[dict[str, Any]]:
    return list(queryset.values(*fields)[:limit])


def _is_zero_difference(source_amount: float, output_amount: float, difference: float) -> bool:
    tolerance = max(1.0, abs(source_amount) * 0.000001, abs(output_amount) * 0.000001)
    return abs(difference) <= tolerance


def _status(
    kind: str,
    source_count: int,
    output_count: int,
    output_type: str | None,
    source_amount: float,
    output_amount: float,
    difference: float,
) -> str:
    if source_count == 0 and output_count == 0:
        return "empty"
    if source_count == 0 and output_count > 0:
        return "mapping_review"
    if source_count > 0 and not output_type:
        return "source_only"
    if source_count > 0 and output_count == 0:
        if kind in EXPECTED_TRANSFORMATION_KINDS:
            return "out_of_window"
        return "missing_output"
    if _is_zero_difference(source_amount, output_amount, difference):
        return "ok"
    if kind in DIRECT_RECONCILIATION_KINDS:
        return "review"
    if kind in EXPECTED_TRANSFORMATION_KINDS:
        return "transformed"
    return "review"


def _comparison_basis(kind: str, output_type: str | None, status: str) -> str:
    if status == "ok":
        return "Aucun souci détecté"
    if status == "empty":
        return "Aucune donnée à contrôler"
    if status == "missing_output":
        return "Output moteur manquant"
    if status == "out_of_window":
        return "Hors fenêtre moteur"
    if status == "mapping_review":
        return "Mapping à revoir"
    if status == "source_only" or not output_type:
        return "Source sans output direct"
    if kind in {"billet"}:
        return "Reprise directe"
    if status == "review":
        return "Écart à expliquer"
    return "Stock source vs flux projetés"


def _variance_label(difference_pct: float | None) -> str:
    if difference_pct is None:
        return "-"
    return f"{difference_pct:+.2f}%"


def _money_label(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _comparison_note(kind: str, status: str) -> str:
    if status == "ok":
        return "Aucun souci détecté : le montant source et le montant moteur sont alignés pour cette famille."
    if status == "empty":
        return "Aucune ligne source et aucun flux moteur n'ont été trouvés pour cette famille."
    if status == "missing_output":
        return "Des lignes existent dans la source, mais aucun flux moteur n'a été généré; le mapping ou la fenêtre de projection doit être vérifié."
    if status == "out_of_window":
        return "Des lignes existent dans la source, mais aucune n'entre dans la fenêtre de projection moteur actuelle."
    if status == "mapping_review":
        return "Des flux moteur existent sans lignes source rapprochées; le mapping source/output doit être revu."
    if status == "source_only":
        return TRANSFORMATION_NOTES.get(kind, "Cette source n'a pas d'output moteur direct dans le mapping actuel.")
    if status == "review":
        return "Un flux moteur existe sans source rapprochée; le mapping ou l'import source doit être contrôlé."
    return TRANSFORMATION_NOTES.get(
        kind,
        "Le moteur ALM peut retraiter le montant source via maturité, intérêts, hypothèses ou règles de mapping.",
    )


def _diagnostic(
    kind: str,
    status: str,
    source_amount: float,
    output_amount: float,
    difference: float,
    difference_pct: float | None,
) -> str:
    pct = _variance_label(difference_pct)
    if status == "ok":
        return "Contrôle aligné : aucun écart matériel entre la source et le moteur."
    if status == "empty":
        return "Aucune alimentation observée sur la feuille source et aucun flux moteur généré."
    if status == "source_only":
        return "Source informative ou support de calcul : aucune sortie moteur directe n'est attendue dans ce mapping."
    if status == "missing_output":
        return (
            "Anomalie potentielle : la source est alimentée mais le moteur ne produit aucun output. "
            "Vérifier le mapping, la date de référence et relancer la génération."
        )
    if status == "out_of_window":
        return (
            "Contrôle de fenêtre : la source est alimentée, mais aucun output n'a été généré dans les buckets moteur. "
            "Vérifier les dates d'échéance, la date d'arrêté et la fenêtre de projection."
        )
    if status == "mapping_review":
        return (
            "Mapping à revoir : le moteur contient des flux, mais aucune source importée n'est rapprochée. "
            "Contrôler le code produit, la feuille source et le type d'output."
        )
    if status == "review":
        if kind in DIRECT_RECONCILIATION_KINDS:
            return (
                f"Écart non attendu pour une reprise directe : source {_money_label(source_amount)} FCFA, "
                f"moteur {_money_label(output_amount)} FCFA, variation {pct}."
            )
        return (
            f"Écart à documenter : source {_money_label(source_amount)} FCFA, moteur {_money_label(output_amount)} FCFA, "
            f"variation {pct}."
        )
    return (
        f"Écart attendu par transformation ALM : source {_money_label(source_amount)} FCFA, "
        f"moteur {_money_label(output_amount)} FCFA, variation {pct}."
    )


def _action_hint(kind: str, status: str) -> str:
    if status == "ok":
        return "Aucune action requise."
    if status == "empty":
        return "Alimenter la feuille seulement si cette famille est utilisée par la banque."
    if status == "source_only":
        if kind in SOURCE_ONLY_KINDS:
            return "Contrôle informatif; conserver comme support ou rattacher un output si la banque l'exige."
        return "Confirmer que cette source n'a pas d'output direct attendu."
    if status == "missing_output":
        return "Prioritaire : vérifier mapping, dates d'échéance et régénérer les outputs."
    if status == "out_of_window":
        return "Vérifier les dates source, la date d'arrêté et la fenêtre utilisée par le moteur."
    if status == "mapping_review":
        return "Revoir le mapping source/output et confirmer que la bonne feuille alimente cette famille."
    if status == "review":
        return "Justifier l'écart ou corriger la source/le mapping avant validation."
    return "Valider que la transformation moteur correspond à la règle métier documentée."


def _recent_imports(limit: int = 8) -> list[dict[str, Any]]:
    qs = (
        Tracking.objects.filter(libelle__icontains="Import")
        | Tracking.objects.filter(libelle__icontains="Chargement données test")
        | Tracking.objects.filter(libelle__icontains="Régénération")
    )
    return [
        {
            "id": item.id,
            "label": item.libelle,
            "description": item.description,
            "user": item.utilisateur.username if item.utilisateur else None,
            "timestamp": item.horodatage,
        }
        for item in qs.select_related("utilisateur").order_by("-horodatage")[:limit]
    ]


def compute_data_quality() -> dict[str, Any]:
    output_by_type = {
        row["type_output"]: row
        for row in (
            Output.objects.values("type_output")
            .annotate(
                count=Count("id"),
                total_amount=Sum("montant"),
                first_date=Min("date"),
                last_date=Max("date"),
            )
        )
    }

    rows = []
    total_source_count = 0
    total_source_amount = 0.0
    total_output_count = 0
    total_output_amount = 0.0

    for kind, model in INPUT_MODELS.items():
        label, side = INPUT_LABELS.get(kind, (kind, "actif"))
        config = LINEAGE_CONFIG.get(kind, InputLineageConfig(kind, None, None))
        output_row = output_by_type.get(config.output_type or "")
        source_count = model.objects.count()
        source_amount = _sum_abs(model, config.amount_field)
        first_source_date, last_source_date = _date_bounds(model, config.date_field)
        output_count = int(output_row["count"]) if output_row else 0
        output_amount = float(output_row["total_amount"] or 0) if output_row else 0.0
        difference = output_amount - source_amount
        difference_pct = (difference / source_amount * 100) if source_amount else None
        status = _status(
            kind,
            source_count,
            output_count,
            config.output_type,
            source_amount,
            output_amount,
            difference,
        )
        comparison_note = _comparison_note(kind, status)
        diagnostic = _diagnostic(kind, status, source_amount, output_amount, difference, difference_pct)

        total_source_count += source_count
        total_source_amount += source_amount
        total_output_count += output_count
        total_output_amount += output_amount

        rows.append({
            "kind": kind,
            "label": label,
            "side": side,
            "category": getattr(model, "CATEGORY", "core"),
            "source_count": source_count,
            "source_amount": source_amount,
            "source_first_date": first_source_date,
            "source_last_date": last_source_date,
            "amount_field": config.amount_field,
            "date_field": config.date_field,
            "output_type": config.output_type,
            "output_count": output_count,
            "output_amount": output_amount,
            "output_first_date": output_row["first_date"] if output_row else None,
            "output_last_date": output_row["last_date"] if output_row else None,
            "difference": difference,
            "difference_pct": difference_pct,
            "variance_label": _variance_label(difference_pct),
            "status": status,
            "severity": STATUS_SEVERITY.get(status, "warning"),
            "is_expected_difference": status in {"ok", "empty", "source_only", "transformed"},
            "comparison_basis": _comparison_basis(kind, config.output_type, status),
            "explanation_title": _comparison_basis(kind, config.output_type, status),
            "comparison_note": comparison_note,
            "explanation": comparison_note,
            "diagnostic": diagnostic,
            "action_hint": _action_hint(kind, status),
            "detail_url": f"/outputs-control/{kind}",
            "lineage": [
                "Input Excel multi-feuilles",
                f"Table source {model._meta.db_table}",
                f"Montant source: {config.amount_field or 'n/a'}",
                f"Date de bucket: {config.date_field or 'n/a'}",
                f"Output moteur: {config.output_type or 'aucun output direct'}",
            ],
        })

    rows.sort(key=lambda row: (row["side"], row["label"]))
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    return {
        "summary": {
            "families": len(rows),
            "source_count": total_source_count,
            "source_amount": total_source_amount,
            "output_count": total_output_count,
            "output_amount": total_output_amount,
            "difference": total_output_amount - total_source_amount,
            "status_counts": status_counts,
        },
        "rows": rows,
        "recent_imports": _recent_imports(),
    }


def compute_data_quality_detail(kind: str, limit: int = 50) -> dict[str, Any]:
    if kind not in INPUT_MODELS:
        raise Http404(f"Famille d'input inconnue: {kind}")

    limit = max(5, min(limit, 200))
    model = INPUT_MODELS[kind]
    label, side = INPUT_LABELS.get(kind, (kind, "actif"))
    config = LINEAGE_CONFIG.get(kind, InputLineageConfig(kind, None, None))
    output_qs = Output.objects.filter(type_output=config.output_type) if config.output_type else Output.objects.none()

    source_count = model.objects.count()
    source_amount = _sum_abs(model, config.amount_field)
    first_source_date, last_source_date = _date_bounds(model, config.date_field)
    output_count = output_qs.count()
    output_amount = float(output_qs.aggregate(total=Sum("montant"))["total"] or 0)
    first_output_date = output_qs.aggregate(first=Min("date"))["first"] if config.output_type else None
    last_output_date = output_qs.aggregate(last=Max("date"))["last"] if config.output_type else None
    difference = output_amount - source_amount
    difference_pct = (difference / source_amount * 100) if source_amount else None
    status = _status(
        kind,
        source_count,
        output_count,
        config.output_type,
        source_amount,
        output_amount,
        difference,
    )

    source_fields = _model_fields(model)
    output_fields = ["id", "type_output", "date", "montant", "created_at", "updated_at"]
    source_qs = model.objects.all().order_by("-created_at")
    output_preview_qs = output_qs.order_by("date", "id")

    bucket_summary = []
    if config.output_type:
        bucket_summary = list(
            output_qs.values("date")
            .annotate(count=Count("id"), total_amount=Sum("montant"))
            .order_by("date")[:limit]
        )

    return {
        "kind": kind,
        "label": label,
        "side": side,
        "category": getattr(model, "CATEGORY", "core"),
        "status": status,
        "severity": STATUS_SEVERITY.get(status, "warning"),
        "is_expected_difference": status in {"ok", "empty", "source_only", "transformed"},
        "comparison_basis": _comparison_basis(kind, config.output_type, status),
        "explanation_title": _comparison_basis(kind, config.output_type, status),
        "comparison_note": _comparison_note(kind, status),
        "explanation": _comparison_note(kind, status),
        "diagnostic": _diagnostic(kind, status, source_amount, output_amount, difference, difference_pct),
        "action_hint": _action_hint(kind, status),
        "source": {
            "table": model._meta.db_table,
            "count": source_count,
            "amount": source_amount,
            "first_date": first_source_date,
            "last_date": last_source_date,
            "amount_field": config.amount_field,
            "date_field": config.date_field,
            "fields": source_fields,
            "rows": _preview_rows(source_qs, source_fields, limit),
        },
        "output": {
            "type": config.output_type,
            "count": output_count,
            "amount": output_amount,
            "first_date": first_output_date,
            "last_date": last_output_date,
            "fields": output_fields,
            "rows": _preview_rows(output_preview_qs, output_fields, limit) if config.output_type else [],
            "bucket_summary": bucket_summary,
        },
        "difference": difference,
        "difference_pct": difference_pct,
        "variance_label": _variance_label(difference_pct),
        "limit": limit,
        "lineage": [
            {"label": "Feuille source", "value": f"{label} ({model._meta.db_table})"},
            {"label": "Champ montant source", "value": config.amount_field or "Non applicable"},
            {"label": "Champ date / bucket", "value": config.date_field or "Non applicable"},
            {"label": "Output moteur", "value": config.output_type or "Aucun output direct"},
            {"label": "Transformation", "value": TRANSFORMATION_NOTES.get(kind, "Règle moteur standard ou mapping à documenter.")},
            {"label": "Action", "value": _action_hint(kind, status)},
        ],
    }
