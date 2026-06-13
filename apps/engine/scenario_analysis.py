"""Scenario Analysis ALM.

Cette vue se distingue de la synthèse classique : elle consolide plusieurs
moteurs (liquidité, LCR, NII, EVE, basis risk, hors-bilan) pour produire une
lecture comparative par scénario.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from apps.analytics.eve import compute_eve_sensitivity
from apps.analytics.nii import compute_nii_sensitivity
from apps.governance.services import get_assumption_value
from apps.governance.models import AssumptionVersion
from apps.inputs.models import Output

from .lcr import compute_lcr_all
from .mco import compute_mco
from .rate_gap import compute_rate_gap_enriched
from .synthesis import SCENARIOS, compute_all_scenarios

SCENARIO_ANALYSIS_CACHE_TIMEOUT = 10 * 60


def _latest_marker(model, field: str = "updated_at") -> str:
    if not any(item.name == field for item in model._meta.fields):
        field = "created_at"
    value = model.objects.aggregate(latest=Max(field)).get("latest")
    return value.isoformat() if value else "empty"


def _cache_key(mode: str) -> str:
    output_marker = _latest_marker(Output)
    assumption_marker = _latest_marker(AssumptionVersion)
    return f"scenario-analysis:v2:{mode}:outputs:{output_marker}:assumptions:{assumption_marker}"


def _cumulative(values: list[float]) -> list[float]:
    total = 0.0
    result = []
    for value in values:
        total = round(total + value, 2)
        result.append(total)
    return result


def _dynamic_series(data: dict[str, Any]) -> dict[str, Any]:
    """Construit une simulation dynamique simple.

    Hypothèse : une part des tombées d'actifs/passifs d'un bucket est renouvelée
    dans le bucket suivant. Les pourcentages sont gouvernés dans les hypothèses.
    """
    asset_rollover = max(0.0, get_assumption_value("dynamic_asset_rollover_pct", 80.0) / 100)
    liability_rollover = max(0.0, get_assumption_value("dynamic_liability_rollover_pct", 75.0) / 100)

    assets = [float(v) for v in data.get("total_assets", [])]
    liabilities = [float(v) for v in data.get("total_depense", [])]
    dyn_assets = assets[:]
    dyn_liabilities = liabilities[:]

    for index in range(1, len(assets)):
        dyn_assets[index] = round(dyn_assets[index] + assets[index - 1] * asset_rollover, 2)
        dyn_liabilities[index] = round(dyn_liabilities[index] + liabilities[index - 1] * liability_rollover, 2)

    net = [round(a - l, 2) for a, l in zip(dyn_assets, dyn_liabilities)]
    off_balance = [float(v) for v in data.get("off_balance_net", [0.0] * len(net))]
    net_with_ob = [round(n + ob, 2) for n, ob in zip(net, off_balance)]

    return {
        "total_assets": dyn_assets,
        "total_depense": dyn_liabilities,
        "net_funding": net,
        "cumulative_net_funding": _cumulative(net),
        "net_funding_with_off_balance": net_with_ob,
        "cumulative_net_funding_with_off_balance": _cumulative(net_with_ob),
        "assumptions": {
            "dynamic_asset_rollover_pct": round(asset_rollover * 100, 2),
            "dynamic_liability_rollover_pct": round(liability_rollover * 100, 2),
        },
    }


def _scenario_metrics(code: str, data: dict[str, Any], lcr: dict[str, Any], mco: dict[str, Any]) -> dict[str, Any]:
    cum = data.get("cumulative_net_funding_with_off_balance") or data.get("cumulative_net_funding") or []
    net = data.get("net_funding_with_off_balance") or data.get("net_funding") or []
    min_cum = min(cum) if cum else 0.0
    min_index = cum.index(min_cum) if cum else -1
    buckets = data.get("buckets", [])
    return {
        "scenario": code,
        "label": (data.get("scenario_config") or {}).get("label", code),
        "reference_date": data.get("reference_date"),
        "lcr_pct": lcr.get(code, {}).get("lcr_pct"),
        "lcr_compliant": lcr.get(code, {}).get("compliant"),
        "mco": mco.get("scenarios", {}).get(code, {}).get("mco", 0.0),
        "mco_label": mco.get("scenarios", {}).get(code, {}).get("mco_label"),
        "min_cumulative_gap": round(min_cum, 2),
        "min_cumulative_gap_label": buckets[min_index] if 0 <= min_index < len(buckets) else None,
        "negative_buckets": len([v for v in net if v < 0]),
        "total_assets": round(sum(data.get("total_assets", [])), 2),
        "total_liabilities": round(sum(data.get("total_depense", [])), 2),
        "off_balance_included": bool(data.get("off_balance_included")),
    }


def compute_scenario_analysis(balance_sheet_mode: str = "static", force_refresh: bool = False) -> dict[str, Any]:
    """Retourne une comparaison base/modéré/sévère orientée ALCO."""
    mode = balance_sheet_mode if balance_sheet_mode in {"static", "dynamic"} else "static"
    key = _cache_key(mode)
    if not force_refresh:
        cached = cache.get(key)
        if cached:
            payload = deepcopy(cached)
            payload["cache"] = {**payload.get("cache", {}), "hit": True}
            return payload

    synthesis = compute_all_scenarios()
    dynamic_assumptions: dict[str, float] = {}
    if mode == "dynamic":
        transformed = {}
        for code, data in synthesis.items():
            dyn = _dynamic_series(data)
            dynamic_assumptions = dyn["assumptions"]
            transformed[code] = {**data, **dyn}
        synthesis = transformed

    lcr = compute_lcr_all()
    mco = compute_mco(include_off_balance=True)
    nii = compute_nii_sensitivity()
    eve = compute_eve_sensitivity()
    rate_gap = compute_rate_gap_enriched()

    rows = [_scenario_metrics(code, synthesis[code], lcr, mco) for code in SCENARIOS]
    base_row = rows[0] if rows else {}
    for row in rows:
        row["delta_min_cumulative_gap_vs_base"] = round(
            row["min_cumulative_gap"] - float(base_row.get("min_cumulative_gap", 0.0)),
            2,
        )
        row["delta_lcr_vs_base"] = (
            round(row["lcr_pct"] - base_row["lcr_pct"], 2)
            if row.get("lcr_pct") is not None and base_row.get("lcr_pct") is not None
            else None
        )

    stressed_nii = [s for s in nii.get("scenarios", []) if s.get("scenario") != "base"]
    stressed_eve = [s for s in eve.get("scenarios", []) if s.get("scenario") != "base"]
    worst_nii = min(stressed_nii, key=lambda s: s.get("delta_nii", 0.0), default=None)
    worst_eve = min(stressed_eve, key=lambda s: s.get("delta_eve", 0.0), default=None)
    basis_alerts = rate_gap.get("basis_risk_summary", []) or []

    payload = {
        "balance_sheet_mode": mode,
        "mode_label": "Bilan dynamique" if mode == "dynamic" else "Bilan statique",
        "mode_note": (
            "Simulation avec renouvellement des tombées selon les hypothèses actives."
            if mode == "dynamic"
            else "Lecture à bilan statique, sans renouvellement de production nouvelle."
        ),
        "dynamic_assumptions": dynamic_assumptions,
        "scenarios": rows,
        "liquidity_curves": {
            code: {
                "buckets": data.get("buckets", []),
                "net_funding": data.get("net_funding_with_off_balance") or data.get("net_funding", []),
                "cumulative_net_funding": data.get("cumulative_net_funding_with_off_balance") or data.get("cumulative_net_funding", []),
                "total_assets": data.get("total_assets", []),
                "total_depense": data.get("total_depense", []),
                "off_balance_net": data.get("off_balance_net", []),
            }
            for code, data in synthesis.items()
        },
        "interest_rate": {
            "base_nii": nii.get("base_nii", 0.0),
            "worst_nii": worst_nii,
            "base_eve": eve.get("base_eve", 0.0),
            "worst_eve": worst_eve,
            "basis_risk_alerts": basis_alerts,
            "basis_risk_count": len(basis_alerts),
        },
        "cache": {
            "hit": False,
            "generated_at": timezone.now().isoformat(),
            "timeout_seconds": SCENARIO_ANALYSIS_CACHE_TIMEOUT,
        },
    }
    cache.set(key, deepcopy(payload), SCENARIO_ANALYSIS_CACHE_TIMEOUT)
    return payload
