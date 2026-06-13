"""Lecture d'impact des hypothèses comportementales appliquées au moteur."""
from __future__ import annotations

from typing import Any

from django.db.models import Sum

from apps.inputs.models import INPUT_LABELS, INPUT_MODELS, Output
from .behavioral_resolver import resolve_behavioral_params
from .data_quality import LINEAGE_CONFIG


BEHAVIORAL_FAMILIES = [
    ("credit", "credit"),
    ("compte_courant", "compte_371"),
    ("compte_cheque", "compte_372"),
    ("compte_livret", "compte_373"),
    ("cpte_corr", "compte_vue_cor"),
    ("depot_terme", "depot_terme"),
    ("bon_caisse", "bon"),
]


def _sum_model(kind: str) -> float:
    model = INPUT_MODELS.get(kind)
    config = LINEAGE_CONFIG.get(kind)
    if not model or not config or not config.amount_field:
        return 0.0
    return float(model.objects.aggregate(total=Sum(config.amount_field))["total"] or 0)


def _sum_output(output_type: str) -> float:
    return float(Output.objects.filter(type_output=output_type).aggregate(total=Sum("montant"))["total"] or 0)


def _classify(kind: str, params: dict[str, Any]) -> str:
    if kind in {"compte_courant", "compte_cheque", "compte_livret", "cpte_corr"}:
        return (
            f"Répartition NMD: stable coeur {params['stable_core_pct']:.1f}%, "
            f"stable non-coeur {params['stable_non_core_pct']:.1f}%, volatile {params['volatile_pct']:.1f}%."
        )
    if kind == "credit":
        return f"Crédits: CPR annuel {params['cpr_annual_pct']:.1f}% projeté en remboursement anticipé."
    return (
        f"Passifs à terme: retrait anticipé {params['early_withdrawal_pct']:.1f}%, "
        f"rollover {params['rollover_rate_pct']:.1f}%."
    )


def compute_behavioral_impact() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_kind, output_type in BEHAVIORAL_FAMILIES:
        label, side = INPUT_LABELS.get(source_kind, (source_kind, ""))
        params = resolve_behavioral_params(output_type)
        source_amount = abs(_sum_model(source_kind))
        output_amount = abs(_sum_output(output_type))
        difference = output_amount - source_amount
        difference_pct = (difference / source_amount * 100) if source_amount else None
        rows.append({
            "kind": source_kind,
            "output_type": output_type,
            "label": label,
            "side": side,
            "source_amount": source_amount,
            "behavioral_amount": output_amount,
            "difference": difference,
            "difference_pct": difference_pct,
            "param_source": params.get("source"),
            "param_code": params.get("param_code") or "",
            "stable_core_pct": params.get("stable_core_pct"),
            "stable_non_core_pct": params.get("stable_non_core_pct"),
            "volatile_pct": params.get("volatile_pct"),
            "runoff_core_months": params.get("runoff_core_months"),
            "runoff_non_core_months": params.get("runoff_non_core_months"),
            "repricing_lag_months": params.get("repricing_lag_months"),
            "pass_through_pct": params.get("pass_through_pct"),
            "cpr_annual_pct": params.get("cpr_annual_pct"),
            "early_withdrawal_pct": params.get("early_withdrawal_pct"),
            "rollover_rate_pct": params.get("rollover_rate_pct"),
            "interpretation": _classify(source_kind, params),
            "detail_url": f"/outputs-control/{source_kind}",
        })
    return rows
