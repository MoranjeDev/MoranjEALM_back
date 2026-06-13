"""Rapprochement entre le bilan GL officiel et les inputs ALM."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import Count, Q, Sum

from apps.balance_sheet.models import BalanceSheetLine
from apps.inputs import models as M
from apps.inputs.models import Output
from apps.mapping.models import ProductMapping
from apps.off_balance.models import OffBalanceSheetItem


@dataclass(frozen=True)
class AlmFamily:
    kind: str
    label: str
    model_cls: type
    amount_field: str
    sens: str


ALM_MAPPING = [
    AlmFamily("credit", "Crédits clientèle", M.InputCredit, "capital_restant", "actif"),
    AlmFamily("terme", "Prêts à terme", M.InputTerme, "montant", "actif"),
    AlmFamily("decouvert", "Découverts", M.InputDecouvert, "montant", "actif"),
    AlmFamily("bta", "BTA", M.InputBta, "solde", "actif"),
    AlmFamily("ota", "OTA", M.InputOta, "solde", "actif"),
    AlmFamily("emprunt_obl", "Emprunts obligataires", M.InputEmpruntObl, "solde", "actif"),
    AlmFamily("pret_cor", "Prêts correspondants", M.InputPretCor, "capital_restant", "actif"),
    AlmFamily("pret_inter_banc", "Prêts interbancaires à blanc", M.InputPretInterBanc, "solde", "actif"),
    AlmFamily("beac", "Compte BEAC", M.InputBeac, "cumul", "actif"),
    AlmFamily("pret_titre", "Prêts de titres", M.InputPretTitre, "montant", "actif"),
    AlmFamily("billet", "Billets et pièces", M.InputBillet, "solde", "actif"),
    AlmFamily("cpte_corr", "Comptes correspondants", M.InputCpteCorr, "cumul", "passif"),
    AlmFamily("depot_terme", "Dépôts à terme", M.InputDepotTerme, "montant", "passif"),
    AlmFamily("bon_caisse", "Bons de caisse", M.InputBonCaisse, "montant", "passif"),
    AlmFamily("pension_livree", "Pensions livrées", M.InputPensionLivree, "montant", "passif"),
    AlmFamily("emprunt_inter", "Emprunts interbancaires", M.InputEmpruntInter, "montant", "passif"),
    AlmFamily("compte_courant", "Comptes courants 371", M.InputCompteCourant, "cumul", "passif"),
    AlmFamily("compte_cheque", "Comptes chèques 372", M.InputCompteCheque, "cumul", "passif"),
    AlmFamily("compte_livret", "Comptes livrets 373", M.InputCompteLivret, "cumul", "passif"),
    AlmFamily("avance_beac", "Avances BEAC", M.InputAvanceBeac, "montant_total_rembourse", "passif"),
    AlmFamily("emprunt_titre", "Emprunts de titres", M.InputEmpruntTitre, "montant_total_rembourse", "passif"),
]

DIRECT_CODE_ALIASES = {
    "credit": ["credit", "credit_corp"],
    "terme": ["pret_ter_cor", "terme"],
    "bta": ["bta"],
    "ota": ["ota"],
    "emprunt_obl": ["emprunt_obl"],
    "decouvert": ["decouvert"],
    "beac": ["beac"],
    "billet": ["billet", "cash"],
    "pret_cor": ["pret_cor", "nostro"],
    "pret_inter_banc": ["inter_blanc", "pret_inter_banc", "placement_ib"],
    "cpte_corr": ["compte_vue_cor", "cpte_corr", "dda_fcy"],
    "depot_terme": ["depot_terme", "dat"],
    "bon_caisse": ["bon", "bon_caisse"],
    "emprunt_inter": ["emprunt_inter_banc", "emprunt_inter", "borrow_ib"],
    "compte_courant": ["compte_371", "compte_courant", "dda"],
    "compte_cheque": ["compte_372", "compte_cheque", "checking"],
    "compte_livret": ["compte_373", "compte_livret", "savings"],
    "avance_beac": ["avance_beac"],
    "emprunt_titre": ["emprunt_titre"],
}

OUTPUT_TYPE_BY_KIND = {
    "credit": "credit",
    "terme": "pret_ter_cor",
    "decouvert": "decouvert",
    "bta": "bta",
    "ota": "ota",
    "emprunt_obl": "emprunt_obl",
    "pret_cor": "pret_cor",
    "pret_inter_banc": "inter_blanc",
    "beac": "beac",
    "pret_titre": "pret_titre",
    "billet": "billet",
    "cpte_corr": "compte_vue_cor",
    "depot_terme": "depot_terme",
    "bon_caisse": "bon",
    "pension_livree": "pension_livree",
    "emprunt_inter": "emprunt_inter_banc",
    "compte_courant": "compte_371",
    "compte_cheque": "compte_372",
    "compte_livret": "compte_373",
    "avance_beac": "avance_beac",
    "emprunt_titre": "emprunt_titre",
}


def _number(value: Any) -> float:
    return float(value or 0)


def _sum(qs, field_name: str) -> float:
    return _number(qs.aggregate(total=Sum(field_name))["total"])


def _date_arrete(value: str | None) -> date | None:
    if value:
        return date.fromisoformat(value)
    return (
        BalanceSheetLine.objects.order_by("-date_arrete")
        .values_list("date_arrete", flat=True)
        .first()
    )


def _mapping_codes(kind: str) -> list[str]:
    return list(
        ProductMapping.objects.filter(is_active=True, target_kind=kind)
        .values_list("source_code", flat=True)
    )


def _direct_codes(kind: str) -> list[str]:
    return DIRECT_CODE_ALIASES.get(kind, [kind])


def _build_gl_filter(codes: list[str], direct_codes: list[str]) -> Q:
    query = Q()
    for code in [c for c in codes + direct_codes if c]:
        query |= Q(product_code__iexact=code)
        query |= Q(compte_gl__istartswith=code)
    return query


def _gl_queryset(family: AlmFamily, arrete: date):
    mapped_codes = _mapping_codes(family.kind)
    direct_codes = _direct_codes(family.kind)
    query = _build_gl_filter(mapped_codes, direct_codes)
    base = BalanceSheetLine.objects.filter(date_arrete=arrete, sens=family.sens)
    if not query:
        return base.none(), mapped_codes, direct_codes
    return base.filter(query), mapped_codes, direct_codes


def _status(diff: float, gl_total: float, alm_total: float, mapped: bool) -> str:
    if not mapped and gl_total == 0 and alm_total == 0:
        return "empty"
    if not mapped and alm_total != 0:
        return "missing_gl_mapping"
    if gl_total == 0 and alm_total != 0:
        return "missing_gl_reference"
    if alm_total == 0 and gl_total != 0:
        return "missing_alm_input"
    pct = abs(diff) / max(abs(gl_total), 1) * 100
    if pct < 1:
        return "ok"
    if pct < 5:
        return "warning"
    return "error"


def _note(status: str) -> str:
    notes = {
        "ok": "Le solde GL et le solde ALM sont alignés.",
        "warning": "Écart faible à contrôler : arrondis, intérêts ou retraitements peuvent l'expliquer.",
        "error": "Écart significatif : contrôler le mapping produit, la date d'arrêté et les règles de projection.",
        "empty": "Aucune donnée GL ni input ALM pour cette famille.",
        "missing_gl_mapping": "Input ALM présent, mais aucune ligne GL rapprochée : compléter le mapping produit/GL.",
        "missing_gl_reference": "Input ALM présent sans référence GL identifiée sur cette date d'arrêté.",
        "missing_alm_input": "Solde GL présent mais aucun input ALM correspondant n'a été importé.",
    }
    return notes.get(status, "Écart à analyser.")


def _primary_status(source_status: str, output_status: str, output_lines: int, gl_total: float) -> str:
    """Use the engine output as primary evidence when it is available.

    The raw input table can be a historical stock or a support table, while the
    output is the amount actually consumed by the ALM calculations.
    """
    if not gl_total or not output_lines:
        return source_status
    if output_status == "ok":
        return "ok" if source_status in {"ok", "warning"} else "warning"
    if output_status == "warning" and source_status == "error":
        return "warning"
    return source_status


def _reconciliation_note(source_status: str, output_status: str, primary_status: str, output_lines: int) -> str:
    if output_lines and output_status == "ok" and source_status != "ok":
        return (
            "Le flux moteur est aligné avec le bilan GL. L'écart sur le stock source "
            "vient de l'historique, des intérêts ou des règles de transformation."
        )
    if output_lines and output_status == "warning" and source_status == "error":
        return (
            "Le rapprochement moteur est proche du bilan GL; l'écart source doit être "
            "documenté mais ne bloque pas la lecture ALM."
        )
    return _note(primary_status)


def _mapping_status(mapped_codes: list[str], gl_total: float) -> str:
    if mapped_codes:
        return "mapped"
    if gl_total:
        return "direct_code"
    return "missing_mapping"


def _output_for_kind(kind: str) -> tuple[str | None, int, float]:
    output_type = OUTPUT_TYPE_BY_KIND.get(kind)
    if not output_type:
        return None, 0, 0.0
    qs = Output.objects.filter(type_output=output_type)
    return output_type, qs.count(), _sum(qs, "montant")


def _devises(qs) -> list[dict[str, Any]]:
    return [
        {"devise": row["devise"], "montant_lcy": _number(row["total"])}
        for row in qs.values("devise").annotate(total=Sum("montant_lcy")).order_by("devise")
    ]


def _row(family: AlmFamily, arrete: date) -> dict[str, Any]:
    alm_total = _sum(family.model_cls.objects.all(), family.amount_field)
    gl_qs, mapped_codes, direct_codes = _gl_queryset(family, arrete)
    gl_total = _sum(gl_qs, "montant_lcy")
    output_type, output_lines, output_total = _output_for_kind(family.kind)
    diff = alm_total - gl_total
    output_diff = output_total - gl_total
    mapped = bool(mapped_codes) or gl_total != 0
    source_status = _status(diff, gl_total, alm_total, mapped)
    output_status = _status(output_diff, gl_total, output_total, mapped=True)
    status = _primary_status(source_status, output_status, output_lines, gl_total)
    pct = (diff / gl_total * 100) if gl_total else None
    output_pct = (output_diff / gl_total * 100) if gl_total else None

    return {
        "kind": family.kind,
        "label": family.label,
        "sens": family.sens,
        "alm_table": family.model_cls._meta.db_table,
        "amount_field": family.amount_field,
        "alm_total": alm_total,
        "output_type": output_type,
        "output_lines": output_lines,
        "output_total": output_total,
        "gl_reference": gl_total,
        "gl_lines": gl_qs.count(),
        "ecart": diff,
        "ecart_pct": round(pct, 2) if pct is not None else None,
        "output_ecart": output_diff,
        "output_ecart_pct": round(output_pct, 2) if output_pct is not None else None,
        "source_status": source_status,
        "output_status": output_status,
        "status": status,
        "status_label": _reconciliation_note(source_status, output_status, status, output_lines),
        "source_status_label": _note(source_status),
        "output_status_label": _note(output_status),
        "mapping_status": _mapping_status(mapped_codes, gl_total),
        "mapped_source_codes": mapped_codes,
        "direct_codes_used": direct_codes,
        "devise_breakdown": _devises(gl_qs),
    }


def _summary_ecart(gl_total: float, alm_total: float) -> dict[str, Any]:
    diff = alm_total - gl_total
    pct = (diff / gl_total * 100) if gl_total else None
    status = _status(diff, gl_total, alm_total, mapped=gl_total != 0)
    return {
        "diff": diff,
        "pct": round(pct, 2) if pct is not None else None,
        "status": status,
        "note": _note(status),
    }


def _empty_currency_control() -> dict[str, Any]:
    return {
        "rows": [],
        "consolidated": {"actif_lcy": 0, "passif_lcy": 0, "net_lcy": 0, "hors_bilan_lcy": 0},
        "lcy": {"actif_lcy": 0, "passif_lcy": 0, "net_lcy": 0},
        "fcy": {"actif_lcy": 0, "passif_lcy": 0, "net_lcy": 0, "actif_fcy": 0, "passif_fcy": 0, "net_fcy": 0},
    }


def _balance_currency_control(arrete: date) -> dict[str, Any]:
    qs = BalanceSheetLine.objects.filter(date_arrete=arrete)
    rows = []
    for row in (
        qs.values("devise")
        .annotate(
            actif_lcy=Sum("montant_lcy", filter=Q(sens="actif")),
            passif_lcy=Sum("montant_lcy", filter=Q(sens="passif")),
            hors_bilan_lcy=Sum("montant_lcy", filter=Q(sens="hors_bilan")),
            actif_fcy=Sum("montant_fcy", filter=Q(sens="actif")),
            passif_fcy=Sum("montant_fcy", filter=Q(sens="passif")),
            hors_bilan_fcy=Sum("montant_fcy", filter=Q(sens="hors_bilan")),
        )
        .order_by("devise")
    ):
        actif_lcy = _number(row["actif_lcy"])
        passif_lcy = _number(row["passif_lcy"])
        hors_bilan_lcy = _number(row["hors_bilan_lcy"])
        actif_fcy = _number(row["actif_fcy"])
        passif_fcy = _number(row["passif_fcy"])
        hors_bilan_fcy = _number(row["hors_bilan_fcy"])
        rows.append({
            "devise": row["devise"] or "XAF",
            "actif_lcy": actif_lcy,
            "passif_lcy": passif_lcy,
            "net_lcy": actif_lcy - passif_lcy,
            "hors_bilan_lcy": hors_bilan_lcy,
            "actif_fcy": actif_fcy,
            "passif_fcy": passif_fcy,
            "net_fcy": actif_fcy - passif_fcy,
            "hors_bilan_fcy": hors_bilan_fcy,
            "is_fcy": (row["devise"] or "XAF") != "XAF",
        })

    lcy = [row for row in rows if not row["is_fcy"]]
    fcy = [row for row in rows if row["is_fcy"]]
    return {
        "rows": rows,
        "consolidated": {
            "actif_lcy": sum(row["actif_lcy"] for row in rows),
            "passif_lcy": sum(row["passif_lcy"] for row in rows),
            "net_lcy": sum(row["net_lcy"] for row in rows),
            "hors_bilan_lcy": sum(row["hors_bilan_lcy"] for row in rows),
        },
        "lcy": {
            "actif_lcy": sum(row["actif_lcy"] for row in lcy),
            "passif_lcy": sum(row["passif_lcy"] for row in lcy),
            "net_lcy": sum(row["net_lcy"] for row in lcy),
        },
        "fcy": {
            "actif_lcy": sum(row["actif_lcy"] for row in fcy),
            "passif_lcy": sum(row["passif_lcy"] for row in fcy),
            "net_lcy": sum(row["net_lcy"] for row in fcy),
            "actif_fcy": sum(row["actif_fcy"] for row in fcy),
            "passif_fcy": sum(row["passif_fcy"] for row in fcy),
            "net_fcy": sum(row["net_fcy"] for row in fcy),
        },
    }


def _off_balance_control(arrete: date) -> dict[str, Any]:
    qs = OffBalanceSheetItem.objects.filter(date_arrete=arrete)
    weighted_drawdown = 0
    for item in qs.only("notionnel", "prob_tirage_pct"):
        weighted_drawdown += int(item.notionnel * item.prob_tirage_pct / 100)

    by_type = [
        {
            "type_engagement": row["type_engagement"],
            "count": row["count"],
            "notionnel": _number(row["notionnel"]),
            "utilise": _number(row["utilise"]),
        }
        for row in qs.values("type_engagement").annotate(
            count=Count("id"),
            notionnel=Sum("notionnel"),
            utilise=Sum("montant_utilise"),
        ).order_by("type_engagement")
    ]

    by_currency = [
        {
            "devise": row["devise"] or "XAF",
            "notionnel": _number(row["notionnel"]),
            "utilise": _number(row["utilise"]),
        }
        for row in qs.values("devise").annotate(
            notionnel=Sum("notionnel"),
            utilise=Sum("montant_utilise"),
        ).order_by("devise")
    ]

    summary = qs.aggregate(total_notionnel=Sum("notionnel"), total_utilise=Sum("montant_utilise"))
    return {
        "count": qs.count(),
        "total_notionnel": _number(summary["total_notionnel"]),
        "total_utilise": _number(summary["total_utilise"]),
        "total_pondere_tirage": weighted_drawdown,
        "by_type": by_type,
        "by_currency": by_currency,
        "integration_matrix": [
            {"module": "Liquidity gap", "included": True, "note": "Flux pondérés intégrés via le moteur hors-bilan."},
            {"module": "Multi-devise / position FX", "included": True, "note": "Engagements FCY intégrés dans la position nette devise."},
            {"module": "EVE Sensitivity", "included": True, "note": "Option disponible dans le calcul EVE enrichi."},
            {"module": "Bilan comptable officiel", "included": False, "note": "Hors-bilan suivi séparément du bilan GL."},
        ],
    }


def _empty_off_balance_control() -> dict[str, Any]:
    return {
        "count": 0,
        "total_notionnel": 0,
        "total_utilise": 0,
        "total_pondere_tirage": 0,
        "by_type": [],
        "by_currency": [],
        "integration_matrix": [
            {"module": "Liquidity gap", "included": True, "note": "Flux pondérés intégrés via le moteur hors-bilan."},
            {"module": "Multi-devise / position FX", "included": True, "note": "Engagements FCY intégrés dans la position nette devise."},
            {"module": "EVE Sensitivity", "included": True, "note": "Option disponible dans le calcul EVE enrichi."},
            {"module": "Bilan comptable officiel", "included": False, "note": "Hors-bilan suivi séparément du bilan GL."},
        ],
    }


def _empty_summary() -> dict[str, Any]:
    empty_ecart = _summary_ecart(0, 0)
    return {
        "date_arrete": None,
        "gl_actif": 0,
        "gl_passif": 0,
        "mapped_gl_actif": 0,
        "mapped_gl_passif": 0,
        "unmapped_gl_actif": 0,
        "unmapped_gl_passif": 0,
        "alm_actif": 0,
        "alm_passif": 0,
        "output_actif": 0,
        "output_passif": 0,
        "ecart_actif": empty_ecart,
        "ecart_passif": empty_ecart,
        "ecart_output_actif": empty_ecart,
        "ecart_output_passif": empty_ecart,
        "status_counts": {},
        "reading_note": "Aucune ligne de bilan GL importée pour alimenter le rapprochement.",
    }


def compute_reconciliation(date_arrete: str | None = None) -> dict[str, Any]:
    """Retourne le rapprochement bilan GL officiel vs inputs ALM."""
    arrete = _date_arrete(date_arrete)
    if arrete is None:
        return {
            "date_arrete": None,
            "summary": _empty_summary(),
            "currency_control": _empty_currency_control(),
            "off_balance_control": _empty_off_balance_control(),
            "rows": [],
        }

    gl_base = BalanceSheetLine.objects.filter(date_arrete=arrete)
    gl_actif = _sum(gl_base.filter(sens="actif"), "montant_lcy")
    gl_passif = _sum(gl_base.filter(sens="passif"), "montant_lcy")

    rows = [_row(family, arrete) for family in ALM_MAPPING]
    alm_actif = sum(row["alm_total"] for row in rows if row["sens"] == "actif")
    alm_passif = sum(row["alm_total"] for row in rows if row["sens"] == "passif")
    output_actif = sum(row["output_total"] for row in rows if row["sens"] == "actif")
    output_passif = sum(row["output_total"] for row in rows if row["sens"] == "passif")
    mapped_gl_actif = sum(row["gl_reference"] for row in rows if row["sens"] == "actif")
    mapped_gl_passif = sum(row["gl_reference"] for row in rows if row["sens"] == "passif")

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    summary = {
        "date_arrete": str(arrete),
        "gl_actif": gl_actif,
        "gl_passif": gl_passif,
        "mapped_gl_actif": mapped_gl_actif,
        "mapped_gl_passif": mapped_gl_passif,
        "unmapped_gl_actif": gl_actif - mapped_gl_actif,
        "unmapped_gl_passif": gl_passif - mapped_gl_passif,
        "alm_actif": alm_actif,
        "alm_passif": alm_passif,
        "output_actif": output_actif,
        "output_passif": output_passif,
        "ecart_actif": _summary_ecart(gl_actif, alm_actif),
        "ecart_passif": _summary_ecart(gl_passif, alm_passif),
        "ecart_output_actif": _summary_ecart(gl_actif, output_actif),
        "ecart_output_passif": _summary_ecart(gl_passif, output_passif),
        "status_counts": status_counts,
        "reading_note": (
            "Les écarts ne sont pas tous des erreurs : ils peuvent venir des projections "
            "moteur, intérêts, hypothèses comportementales ou mappings GL incomplets."
        ),
    }
    return {
        "date_arrete": str(arrete),
        "summary": summary,
        "currency_control": _balance_currency_control(arrete),
        "off_balance_control": _off_balance_control(arrete),
        "rows": rows,
    }
