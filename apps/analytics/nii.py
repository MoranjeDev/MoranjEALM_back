"""
NII Sensitivity — sensibilité du résultat net d'intérêts aux chocs de taux.

Méthode : on calcule pour chaque actif et passif sensible aux taux le revenu
ou la charge d'intérêt sur l'horizon (par défaut 12 mois), puis on applique
des chocs parallèles ou non parallèles à la courbe de taux.

Hypothèses :
- L'horizon est paramétrable (12 mois par défaut, conformément à la pratique
  bancaire usuelle pour le NII).
- Les positions sont supposées stables sur l'horizon (vue statique). Une vue
  dynamique avec roll-over et production nouvelle est à implémenter en
  réutilisant les modèles RolloverModel et NmdModel.
- Les chocs sont des déplacements parallèles ±100, ±200 bp ainsi que les
  scénarios non parallèles Bâle (steepener, flattener, short up/down).

Résultat : ΔNII en valeur absolue (FCFA) et en pourcentage du NII de base.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from django.utils import timezone

from apps.engine.buckets import build_buckets
from apps.engine.lineage import report_lineage
from apps.engine.rate_gap import ASSETS_RATE_INPUTS, LIABILITIES_RATE_INPUTS
from apps.engine.rate_behavior import (
    rate_behavior_for_input,
    shock_days_after_lag,
    summarize_rate_behaviors,
)
from apps.governance.services import get_assumption_value
from apps.parameters.models import Parameter

DEFAULT_HORIZON_DAYS = 365


@dataclass
class NIIScenario:
    code: str
    label: str
    parallel_shift_bp: float = 0.0
    short_shift_bp: float = 0.0      # Choc 0–1 an
    long_shift_bp: float = 0.0       # Choc > 5 ans


def nii_scenarios() -> list[NIIScenario]:
    return [
        NIIScenario("base", "Cas de base"),
        NIIScenario("parallel_up_100", "Parallèle +100 bp", parallel_shift_bp=get_assumption_value("nii_parallel_up_100_bp", 100)),
        NIIScenario("parallel_down_100", "Parallèle -100 bp", parallel_shift_bp=get_assumption_value("nii_parallel_down_100_bp", -100)),
        NIIScenario("parallel_up_200", "Parallèle +200 bp", parallel_shift_bp=get_assumption_value("nii_parallel_up_200_bp", 200)),
        NIIScenario("parallel_down_200", "Parallèle -200 bp", parallel_shift_bp=get_assumption_value("nii_parallel_down_200_bp", -200)),
        NIIScenario("short_up", "Court-terme +100 bp", short_shift_bp=get_assumption_value("nii_short_up_bp", 100)),
        NIIScenario("short_down", "Court-terme -100 bp", short_shift_bp=get_assumption_value("nii_short_down_bp", -100)),
        NIIScenario("steepener", "Steepener (CT- / LT+)",
                    short_shift_bp=get_assumption_value("nii_steepener_short_bp", -65),
                    long_shift_bp=get_assumption_value("nii_steepener_long_bp", 90)),
        NIIScenario("flattener", "Flattener (CT+ / LT-)",
                    short_shift_bp=get_assumption_value("nii_flattener_short_bp", 90),
                    long_shift_bp=get_assumption_value("nii_flattener_long_bp", -65)),
    ]


NII_SCENARIOS: list[NIIScenario] = [
    NIIScenario("base", "Cas de base"),
    NIIScenario("parallel_up_100", "Parallèle +100 bp", parallel_shift_bp=100),
    NIIScenario("parallel_down_100", "Parallèle -100 bp", parallel_shift_bp=-100),
    NIIScenario("parallel_up_200", "Parallèle +200 bp", parallel_shift_bp=200),
    NIIScenario("parallel_down_200", "Parallèle -200 bp", parallel_shift_bp=-200),
    NIIScenario("short_up", "Court-terme +100 bp", short_shift_bp=100),
    NIIScenario("short_down", "Court-terme -100 bp", short_shift_bp=-100),
    NIIScenario("steepener", "Steepener (CT- / LT+)", short_shift_bp=-65, long_shift_bp=90),
    NIIScenario("flattener", "Flattener (CT+ / LT-)", short_shift_bp=90, long_shift_bp=-65),
]


def _reference_date():
    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)
    return ref


def _aware_datetime(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


def _classify_horizon(date, ref) -> str:
    """Classe une date dans court / moyen / long terme depuis la date d'arrêté."""
    if date is None:
        return "long"
    diff = (pd.Timestamp(_aware_datetime(date)) - pd.Timestamp(ref)).days
    if diff < 365:
        return "short"
    if diff < 365 * 5:
        return "medium"
    return "long"


def _years_to_maturity(date, ref) -> float:
    if date is None:
        return get_assumption_value("irrbb_default_maturity_years", 5.0)
    return max((pd.Timestamp(_aware_datetime(date)) - pd.Timestamp(ref)).days / 365.0, 0.0)


def _shift_for(scenario: NIIScenario, horizon: str, years: float) -> float:
    """Retourne le choc applicable en bp."""
    if scenario.parallel_shift_bp:
        return scenario.parallel_shift_bp
    if horizon == "short":
        return scenario.short_shift_bp
    if horizon == "long":
        return scenario.long_shift_bp
    if scenario.short_shift_bp or scenario.long_shift_bp:
        weight = max(0.0, min(1.0, (years - 1.0) / 4.0))
        return (1 - weight) * scenario.short_shift_bp + weight * scenario.long_shift_bp
    return 0.0


def _effective_days(maturity, ref, horizon_days: int) -> int:
    if maturity is None:
        return horizon_days
    remaining_days = (pd.Timestamp(_aware_datetime(maturity)) - pd.Timestamp(ref)).days
    return max(0, min(horizon_days, remaining_days))


def _bucket_label(maturity, ref) -> str:
    buckets = build_buckets(ref)
    if maturity is None:
        return "Non maturé"
    maturity_dt = _aware_datetime(maturity)
    for bucket in buckets:
        if bucket.contains(maturity_dt):
            return bucket.label
    return "Au-delà"


def _collect_positions():
    """Charge tous les inputs sensibles aux taux."""
    rows = []
    for model_cls, label, amount_field, rate_field, date_field in ASSETS_RATE_INPUTS:
        for obj in model_cls.objects.all():
            rows.append({
                "side": "asset",
                "label": label,
                "amount": float(getattr(obj, amount_field) or 0),
                "rate": float(getattr(obj, rate_field) or 0) / 100.0,
                "maturity": getattr(obj, date_field),
                "rate_behavior": rate_behavior_for_input(label, obj),
            })
    for model_cls, label, amount_field, rate_field, date_field in LIABILITIES_RATE_INPUTS:
        for obj in model_cls.objects.all():
            rows.append({
                "side": "liability",
                "label": label,
                "amount": float(getattr(obj, amount_field) or 0),
                "rate": float(getattr(obj, rate_field) or 0) / 100.0,
                "maturity": getattr(obj, date_field),
                "rate_behavior": rate_behavior_for_input(label, obj),
            })
    return rows


def _empty_product(label: str, side: str) -> dict:
    return {
        "label": label,
        "side": side,
        "amount": 0.0,
        "exposure": 0.0,
        "weighted_rate_amount": 0.0,
        "interest": 0.0,
        "avg_rate": 0.0,
        "behavior_amount": 0.0,
        "behavior_weighted_lag": 0.0,
        "behavior_weighted_pass_through": 0.0,
        "behavior_sources": set(),
    }


def _finalize_products(products: dict[tuple[str, str], dict]) -> list[dict]:
    rows = []
    for item in products.values():
        avg_rate = item["weighted_rate_amount"] / item["amount"] * 100 if item["amount"] else 0.0
        rows.append({
            "label": item["label"],
            "side": item["side"],
            "amount": round(item["amount"], 2),
            "exposure": round(item["exposure"], 2),
            "avg_rate": round(avg_rate, 2),
            "interest": round(item["interest"], 2),
            "repricing_lag_months": round(item["behavior_weighted_lag"] / item["behavior_amount"], 2) if item["behavior_amount"] else 0.0,
            "pass_through_pct": round(item["behavior_weighted_pass_through"] / item["behavior_amount"], 2) if item["behavior_amount"] else 100.0,
            "behavioral_sources": sorted(item["behavior_sources"]),
        })
    return sorted(rows, key=lambda row: (row["side"], row["label"]))


def _finalize_buckets(buckets: dict[str, dict]) -> list[dict]:
    rows = []
    for label, item in buckets.items():
        revenue = item["interest_revenue"]
        cost = item["interest_cost"]
        rows.append({
            "bucket": label,
            "interest_revenue": round(revenue, 2),
            "interest_cost": round(cost, 2),
            "nii": round(revenue - cost, 2),
        })
    return rows


def _nii_for_scenario(positions, scenario: NIIScenario, horizon_days: int, ref) -> dict:
    """Calcule le NII pour un scénario donné."""
    revenue = 0.0
    cost = 0.0
    products: dict[tuple[str, str], dict] = {}
    bucket_labels = [bucket.label for bucket in build_buckets(ref)] + ["Non maturé"]
    buckets = {label: {"interest_revenue": 0.0, "interest_cost": 0.0} for label in bucket_labels}

    for p in positions:
        days = _effective_days(p["maturity"], ref, horizon_days)
        if days <= 0 or p["amount"] == 0:
            continue
        years = _years_to_maturity(p["maturity"], ref)
        h = _classify_horizon(p["maturity"], ref)
        shift = _shift_for(scenario, h, years) / 10000.0  # bp -> décimal
        behavior = p.get("rate_behavior") or rate_behavior_for_input(p["label"])
        shock_days = shock_days_after_lag(days, behavior)
        effective_shift = shift * behavior.pass_through_factor
        effective_shift_for_weight = effective_shift * (shock_days / days) if days else 0.0
        applied_rate = p["rate"] + effective_shift_for_weight
        amount_yearly = (
            p["amount"] * p["rate"] * (days / 365.0)
            + p["amount"] * effective_shift * (shock_days / 365.0)
        )
        exposure = p["amount"] * (days / 365.0)
        key = (p["side"], p["label"])
        item = products.setdefault(key, _empty_product(p["label"], p["side"]))
        item["amount"] += p["amount"]
        item["exposure"] += exposure
        item["weighted_rate_amount"] += p["amount"] * applied_rate
        item["interest"] += amount_yearly
        item["behavior_amount"] += p["amount"]
        item["behavior_weighted_lag"] += p["amount"] * behavior.repricing_lag_months
        item["behavior_weighted_pass_through"] += p["amount"] * behavior.pass_through_pct
        item["behavior_sources"].add(behavior.source if not behavior.param_code else behavior.param_code)

        bucket = _bucket_label(p["maturity"], ref)
        if p["side"] == "asset":
            revenue += amount_yearly
            buckets.setdefault(bucket, {"interest_revenue": 0.0, "interest_cost": 0.0})
            buckets[bucket]["interest_revenue"] += amount_yearly
        else:
            cost += amount_yearly
            buckets.setdefault(bucket, {"interest_revenue": 0.0, "interest_cost": 0.0})
            buckets[bucket]["interest_cost"] += amount_yearly

    nii = revenue - cost
    return {
        "scenario": scenario.code,
        "label": scenario.label,
        "interest_revenue": round(revenue, 2),
        "interest_cost": round(cost, 2),
        "nii": round(nii, 2),
        "by_product": _finalize_products(products),
        "by_bucket": _finalize_buckets(buckets),
    }


def compute_nii_sensitivity(horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict:
    """Calcule le NII de base et la sensibilité aux scénarios."""
    ref = _reference_date()
    positions = _collect_positions()

    scenarios_config = nii_scenarios()
    base_result = _nii_for_scenario(positions, scenarios_config[0], horizon_days, ref)
    base_nii = base_result["nii"]

    scenarios = []
    for sc in scenarios_config:
        r = _nii_for_scenario(positions, sc, horizon_days, ref)
        delta_nii = r["nii"] - base_nii
        delta_pct = (delta_nii / base_nii * 100) if base_nii else 0.0
        scenarios.append({
            **r,
            "delta_nii": round(delta_nii, 2),
            "delta_pct": round(delta_pct, 2),
        })

    return {
        "reference_date": ref.isoformat(),
        "lineage": report_lineage("nii", horizon_days=horizon_days),
        "horizon_days": horizon_days,
        "base_nii": base_nii,
        "base_interest_revenue": base_result["interest_revenue"],
        "base_interest_cost": base_result["interest_cost"],
        "base_by_product": base_result["by_product"],
        "base_by_bucket": base_result["by_bucket"],
        "rate_behavior_summary": summarize_rate_behaviors(positions),
        "scenarios": scenarios,
    }
