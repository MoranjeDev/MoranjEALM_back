"""
EVE Sensitivity — Economic Value of Equity sensibilité aux chocs de taux.

Méthode :
    EVE = Σ (PV des actifs) - Σ (PV des passifs)
    où PV = montant × exp(-rate × time_to_maturity_years)

Pour chaque scénario Bâle (parallel up/down, short up/down, steepener,
flattener), on recalcule les PV avec la courbe choquée et on compare
à l'EVE de base.

Référence : BCBS 368 (Standards for IRRBB), avril 2016.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
from django.utils import timezone

from apps.engine.buckets import build_buckets
from apps.governance.services import get_assumption_value
from apps.parameters.models import Parameter
from .nii import (
    ASSETS_RATE_INPUTS,
    LIABILITIES_RATE_INPUTS,
    NIIScenario,
    _aware_datetime,
)


def eve_scenarios() -> list[NIIScenario]:
    return [
        NIIScenario("base", "Cas de base"),
        NIIScenario("parallel_up_200", "Parallèle +200 bp", parallel_shift_bp=get_assumption_value("eve_parallel_up_200_bp", 200)),
        NIIScenario("parallel_down_200", "Parallèle -200 bp", parallel_shift_bp=get_assumption_value("eve_parallel_down_200_bp", -200)),
        NIIScenario("steepener", "Steepener",
                    short_shift_bp=get_assumption_value("eve_steepener_short_bp", -65),
                    long_shift_bp=get_assumption_value("eve_steepener_long_bp", 90)),
        NIIScenario("flattener", "Flattener",
                    short_shift_bp=get_assumption_value("eve_flattener_short_bp", 90),
                    long_shift_bp=get_assumption_value("eve_flattener_long_bp", -65)),
        NIIScenario("short_up", "Court-terme +100 bp", short_shift_bp=get_assumption_value("eve_short_up_bp", 100)),
        NIIScenario("short_down", "Court-terme -100 bp", short_shift_bp=get_assumption_value("eve_short_down_bp", -100)),
    ]


EVE_SCENARIOS = [
    NIIScenario("base", "Cas de base"),
    NIIScenario("parallel_up_200", "Parallèle +200 bp", parallel_shift_bp=200),
    NIIScenario("parallel_down_200", "Parallèle -200 bp", parallel_shift_bp=-200),
    NIIScenario("steepener", "Steepener", short_shift_bp=-65, long_shift_bp=90),
    NIIScenario("flattener", "Flattener", short_shift_bp=90, long_shift_bp=-65),
    NIIScenario("short_up", "Court-terme +100 bp", short_shift_bp=100),
    NIIScenario("short_down", "Court-terme -100 bp", short_shift_bp=-100),
]


def _years_to_maturity(maturity, ref: datetime) -> float:
    if not maturity:
        return get_assumption_value("irrbb_default_maturity_years", 5.0)
    days = (pd.Timestamp(_aware_datetime(maturity)) - pd.Timestamp(ref)).days
    return max(days / 365.25, 0.0)


def _reference_date():
    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)
    return ref


def _collect():
    rows = []
    for model_cls, label, amount_field, rate_field, date_field in ASSETS_RATE_INPUTS:
        for obj in model_cls.objects.all():
            rows.append({
                "side": "asset", "label": label,
                "amount": float(getattr(obj, amount_field) or 0),
                "rate": float(getattr(obj, rate_field) or 0) / 100.0,
                "maturity": getattr(obj, date_field),
            })
    for model_cls, label, amount_field, rate_field, date_field in LIABILITIES_RATE_INPUTS:
        for obj in model_cls.objects.all():
            rows.append({
                "side": "liability", "label": label,
                "amount": float(getattr(obj, amount_field) or 0),
                "rate": float(getattr(obj, rate_field) or 0) / 100.0,
                "maturity": getattr(obj, date_field),
            })
    return rows


def _bucket_label(maturity, ref) -> str:
    buckets = build_buckets(ref)
    if maturity is None:
        return "Non maturé"
    maturity_dt = _aware_datetime(maturity)
    for bucket in buckets:
        if bucket.contains(maturity_dt):
            return bucket.label
    return "Au-delà"


def _scenario_shift(scenario: NIIScenario, t: float) -> float:
    """Choc en décimal (0.01 = 1 %)."""
    if scenario.parallel_shift_bp:
        return scenario.parallel_shift_bp / 10000.0
    if t <= 1:
        return scenario.short_shift_bp / 10000.0
    if t > 5:
        return scenario.long_shift_bp / 10000.0
    # Interpolation linéaire entre 1 et 5 ans
    if scenario.short_shift_bp or scenario.long_shift_bp:
        weight = (t - 1) / 4
        return ((1 - weight) * scenario.short_shift_bp + weight * scenario.long_shift_bp) / 10000.0
    return 0.0


def _eve_for_scenario(positions, scenario: NIIScenario, ref: datetime) -> dict:
    pv_assets = 0.0
    pv_liabs = 0.0
    product_rows: dict[tuple[str, str], dict] = {}
    bucket_labels = [bucket.label for bucket in build_buckets(ref)] + ["Non maturé", "Au-delà"]
    bucket_rows = {
        label: {"bucket": label, "pv_assets": 0.0, "pv_liabilities": 0.0, "eve": 0.0}
        for label in bucket_labels
    }

    for p in positions:
        if p["amount"] == 0:
            continue
        t = _years_to_maturity(p["maturity"], ref)
        if p["maturity"] is not None and t <= 0:
            continue
        shift = _scenario_shift(scenario, t)
        rate_floor = get_assumption_value("eve_rate_floor_pct", -1.0) / 100.0
        rate = max(p["rate"] + shift, rate_floor)
        df = math.exp(-rate * t)
        pv = p["amount"] * df
        duration = t * pv
        key = (p["side"], p["label"])
        product = product_rows.setdefault(key, {
            "label": p["label"],
            "side": p["side"],
            "amount": 0.0,
            "pv": 0.0,
            "avg_rate_amount": 0.0,
            "weighted_duration": 0.0,
        })
        product["amount"] += p["amount"]
        product["pv"] += pv
        product["avg_rate_amount"] += p["amount"] * rate
        product["weighted_duration"] += duration

        bucket = bucket_rows.setdefault(
            _bucket_label(p["maturity"], ref),
            {"bucket": _bucket_label(p["maturity"], ref), "pv_assets": 0.0, "pv_liabilities": 0.0, "eve": 0.0},
        )
        if p["side"] == "asset":
            pv_assets += pv
            bucket["pv_assets"] += pv
        else:
            pv_liabs += pv
            bucket["pv_liabilities"] += pv
    eve = pv_assets - pv_liabs
    by_product = []
    for item in product_rows.values():
        avg_rate = item["avg_rate_amount"] / item["amount"] * 100 if item["amount"] else 0.0
        duration = item["weighted_duration"] / item["pv"] if item["pv"] else 0.0
        by_product.append({
            "label": item["label"],
            "side": item["side"],
            "amount": round(item["amount"], 2),
            "pv": round(item["pv"], 2),
            "avg_rate": round(avg_rate, 2),
            "duration_years": round(duration, 2),
        })

    by_bucket = []
    for item in bucket_rows.values():
        bucket_eve = item["pv_assets"] - item["pv_liabilities"]
        by_bucket.append({
            "bucket": item["bucket"],
            "pv_assets": round(item["pv_assets"], 2),
            "pv_liabilities": round(item["pv_liabilities"], 2),
            "eve": round(bucket_eve, 2),
        })

    return {
        "scenario": scenario.code,
        "label": scenario.label,
        "pv_assets": round(pv_assets, 2),
        "pv_liabilities": round(pv_liabs, 2),
        "eve": round(eve, 2),
        "by_product": sorted(by_product, key=lambda row: (row["side"], row["label"])),
        "by_bucket": by_bucket,
    }


def compute_eve_sensitivity() -> dict:
    """Calcule l'EVE de base et la sensibilité aux 6 scénarios IRRBB."""
    ref = _reference_date()
    positions = _collect()
    scenarios_config = eve_scenarios()

    base = _eve_for_scenario(positions, scenarios_config[0], ref)
    base_eve = base["eve"]

    scenarios = []
    for sc in scenarios_config:
        r = _eve_for_scenario(positions, sc, ref)
        delta = r["eve"] - base_eve
        delta_pct = (delta / base_eve * 100) if base_eve else 0.0
        scenarios.append({**r, "delta_eve": round(delta, 2), "delta_pct": round(delta_pct, 2)})

    stressed = scenarios[1:]
    worst_loss = min(stressed, key=lambda x: x["delta_eve"]) if stressed else None
    worst_abs = max(stressed, key=lambda x: abs(x["delta_eve"])) if stressed else None

    return {
        "reference_date": ref.isoformat(),
        "base_eve": base_eve,
        "base_pv_assets": base["pv_assets"],
        "base_pv_liabilities": base["pv_liabilities"],
        "base_by_product": base["by_product"],
        "base_by_bucket": base["by_bucket"],
        "scenarios": scenarios,
        "worst_case": worst_loss,
        "worst_abs_case": worst_abs,
    }
