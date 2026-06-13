"""
EVE enrichi — table Bucket × Scénario + hors-bilan + identification des breaches.

Complète le module eve.py existant (qui calcule l'EVE global) avec :
1. La contribution EVE de chaque bucket de maturité (pour identifier les
   buckets sensibles sans attendre un breach global).
2. L'intégration des éléments hors-bilan (dérivés/swaps, LFPs,
   engagements) dans le calcul de PV.
3. L'identification des buckets en breach selon les seuils IRRBB
   (BCBS 368 : |ΔEVE| > 15% du Tier 1 Capital).

Utilise les mêmes données et scénarios que eve.py.
"""
from __future__ import annotations

import math
from datetime import datetime, date

import pandas as pd
from django.utils import timezone

from apps.engine.buckets import build_buckets, Bucket
from apps.engine.rate_behavior import effective_shift_bp, rate_behavior_for_input
from apps.engine.rate_gap import ASSETS_RATE_INPUTS, LIABILITIES_RATE_INPUTS
from apps.off_balance.models import OffBalanceSheetItem
from apps.analytics.nii import _aware_datetime
from apps.analytics.eve import EVE_SCENARIOS, NIIScenario, _reference_date


# Seuil de breach IRRBB par défaut (% du Tier 1 capital)
DEFAULT_BREACH_THRESHOLD_PCT = 15.0
# Tier 1 capital approximatif si non disponible (à paramétrer)
DEFAULT_TIER1_CAPITAL = 10_000_000_000  # 10 Md XAF par défaut


def _years_to_maturity_from_bucket_center(bucket: Bucket, ref: datetime) -> float:
    """Approximation : durée en années au centre du bucket."""
    if bucket.end is None:
        return 7.0  # Au-delà de 5 ans → approximation 7 ans
    mid = bucket.start + (bucket.end - bucket.start) / 2
    days = max((mid - ref).days, 1)
    return days / 365.25


def _pv_factor(rate_pct: float, years: float, shift_bp: float = 0.0) -> float:
    """Facteur d'actualisation continu : exp(-(rate+shift) × years)."""
    rate = max((rate_pct + shift_bp / 100) / 100, 0.0)
    return math.exp(-rate * years)


def _shift_for_bucket(scenario: NIIScenario, years: float) -> float:
    """Détermine le choc en bp pour ce bucket selon sa durée (court < 1 an, long > 5 ans)."""
    if scenario.parallel_shift_bp:
        return scenario.parallel_shift_bp
    if years <= 1.0:
        return scenario.short_shift_bp
    if years >= 5.0:
        return scenario.long_shift_bp
    # Interpolation linéaire entre court et long terme (1-5 ans)
    alpha = (years - 1.0) / 4.0
    return scenario.short_shift_bp + alpha * (scenario.long_shift_bp - scenario.short_shift_bp)


def _collect_inputs_by_bucket(ref: datetime, buckets: list[Bucket]) -> dict[str, list[dict]]:
    """
    Agrège les inputs (actifs + passifs) par bucket.
    Retourne {bucket_code: [{"side": "asset"|"liability", "amount": float, "rate": float}]}
    """
    by_bucket: dict[str, list[dict]] = {b.code: [] for b in buckets}

    for model_cls, label, amount_field, rate_field, date_field in ASSETS_RATE_INPUTS:
        for obj in model_cls.objects.all():
            amount = float(getattr(obj, amount_field, 0) or 0)
            rate = float(getattr(obj, rate_field, 0) or 0)
            mat = getattr(obj, date_field, None)
            if not mat or amount == 0:
                continue
            mat_dt = pd.Timestamp(_aware_datetime(mat))
            for bucket in buckets:
                if bucket.contains(mat_dt):
                    by_bucket[bucket.code].append({
                        "side": "asset",
                        "amount": amount,
                        "rate": rate,
                        "rate_behavior": rate_behavior_for_input(label, obj),
                    })
                    break

    for model_cls, label, amount_field, rate_field, date_field in LIABILITIES_RATE_INPUTS:
        for obj in model_cls.objects.all():
            amount = float(getattr(obj, amount_field, 0) or 0)
            rate = float(getattr(obj, rate_field, 0) or 0)
            mat = getattr(obj, date_field, None)
            if not mat or amount == 0:
                continue
            mat_dt = pd.Timestamp(_aware_datetime(mat))
            for bucket in buckets:
                if bucket.contains(mat_dt):
                    by_bucket[bucket.code].append({
                        "side": "liability",
                        "amount": amount,
                        "rate": rate,
                        "rate_behavior": rate_behavior_for_input(label, obj),
                    })
                    break

    return by_bucket


def _collect_off_balance_by_bucket(ref: datetime, buckets: list[Bucket]) -> dict[str, list[dict]]:
    """
    Agrège les éléments hors-bilan par bucket pour l'EVE.
    Seuls les dérivés (swaps) et LFPs ont un impact de taux sur l'EVE.
    Les engagements de crédit non encore tirés sont inclus avec prob_tirage.
    """
    last_arrete = OffBalanceSheetItem.objects.order_by("-date_arrete").values_list("date_arrete", flat=True).first()
    by_bucket: dict[str, list[dict]] = {b.code: [] for b in buckets}
    if last_arrete is None:
        return by_bucket

    items = OffBalanceSheetItem.objects.filter(date_arrete=last_arrete)
    for item in items:
        amount = float(item.notionnel * item.prob_tirage_pct / 100)
        if amount == 0:
            continue
        rate = float(item.taux or 0)
        mat = item.maturite
        if mat is None:
            # Sans maturité → bucket call (très court terme)
            bc = buckets[0].code if buckets else None
            if bc:
                side = "asset" if item.type_engagement == "lfp" else "liability"
                by_bucket[bc].append({"side": side, "amount": amount, "rate": rate})
            continue
        mat_dt = pd.Timestamp(pd.to_datetime(mat))
        if timezone.is_naive(mat_dt):
            mat_dt = mat_dt.tz_localize("UTC")
        for bucket in buckets:
            if bucket.contains(mat_dt):
                side = "asset" if item.type_engagement == "lfp" else "liability"
                by_bucket[bucket.code].append({"side": side, "amount": amount, "rate": rate})
                break
    return by_bucket


def _eve_for_bucket(items: list[dict], years: float, shift_bp: float) -> dict:
    """Calcule la PV des actifs et passifs d'un bucket sous un scénario."""
    pv_asset = sum(
        item["amount"] * _pv_factor(
            item["rate"],
            years,
            effective_shift_bp(shift_bp, years, item.get("rate_behavior") or rate_behavior_for_input("")),
        )
        for item in items if item["side"] == "asset"
    )
    pv_liab = sum(
        item["amount"] * _pv_factor(
            item["rate"],
            years,
            effective_shift_bp(shift_bp, years, item.get("rate_behavior") or rate_behavior_for_input("")),
        )
        for item in items if item["side"] == "liability"
    )
    return {
        "pv_asset": pv_asset,
        "pv_liability": pv_liab,
        "eve": pv_asset - pv_liab,
    }


def compute_eve_enriched(
    tier1_capital: float = DEFAULT_TIER1_CAPITAL,
    breach_threshold_pct: float = DEFAULT_BREACH_THRESHOLD_PCT,
    include_off_balance: bool = True,
) -> dict:
    """
    Calcule l'EVE enrichi : table Bucket × Scénario + breaches.

    Retourne :
    {
      "reference_date": "...",
      "tier1_capital": ...,
      "breach_threshold_pct": 15.0,
      "scenarios": {
        "base": {
          "eve_total": ...,
          "buckets": [
            {"bucket_code": "call_over", "label": "...", "years": 0.003,
             "pv_asset": ..., "pv_liability": ..., "eve": ..., "delta_eve": ...}
          ]
        },
        "parallel_up_200": { ... }
      },
      "bucket_summary": [
        {"bucket_code": "...", "label": "...", "delta_eve_by_scenario": {...}, "max_delta_eve": ..., "breach": true/false}
      ],
      "breaches": [
        {"bucket_code": "...", "label": "...", "scenario": "...", "delta_eve": ..., "pct_tier1": ..., "severity": "HIGH"|"MEDIUM"}
      ],
      "off_balance_included": true/false
    }
    """
    ref = _reference_date()
    buckets = build_buckets(ref)
    by_bucket = _collect_inputs_by_bucket(ref, buckets)

    if include_off_balance:
        ob_by_bucket = _collect_off_balance_by_bucket(ref, buckets)
        # Fusionner avec les inputs
        for bc in by_bucket:
            by_bucket[bc].extend(ob_by_bucket.get(bc, []))

    # Calculer l'EVE base d'abord
    base_scenario = EVE_SCENARIOS[0]  # "base" — pas de choc
    base_by_bucket = {}
    for bucket in buckets:
        years = _years_to_maturity_from_bucket_center(bucket, ref)
        result = _eve_for_bucket(by_bucket[bucket.code], years, 0.0)
        base_by_bucket[bucket.code] = result["eve"]

    # Calculer pour chaque scénario
    scenarios_result = {}
    for scenario in EVE_SCENARIOS:
        bucket_rows = []
        eve_total = 0.0
        for bucket in buckets:
            years = _years_to_maturity_from_bucket_center(bucket, ref)
            shift = _shift_for_bucket(scenario, years)
            result = _eve_for_bucket(by_bucket[bucket.code], years, shift)
            delta = result["eve"] - base_by_bucket[bucket.code]
            eve_total += result["eve"]
            bucket_rows.append({
                "bucket_code": bucket.code,
                "label": bucket.label,
                "years": round(years, 3),
                "pv_asset": round(result["pv_asset"]),
                "pv_liability": round(result["pv_liability"]),
                "eve": round(result["eve"]),
                "delta_eve": round(delta),
                "delta_eve_pct_tier1": round(delta / tier1_capital * 100, 2) if tier1_capital else 0,
            })
        scenarios_result[scenario.code] = {
            "label": scenario.label,
            "eve_total": round(eve_total),
            "buckets": bucket_rows,
        }

    # Bucket summary + breaches
    bucket_summary = []
    breaches = []
    for bucket in buckets:
        delta_by_scenario = {}
        max_delta = 0.0
        for sc_code, sc_data in scenarios_result.items():
            if sc_code == "base":
                continue
            row = next((r for r in sc_data["buckets"] if r["bucket_code"] == bucket.code), None)
            if row:
                delta_by_scenario[sc_code] = row["delta_eve"]
                if abs(row["delta_eve"]) > abs(max_delta):
                    max_delta = row["delta_eve"]
                # Breach check
                pct = row["delta_eve_pct_tier1"]
                if abs(pct) > breach_threshold_pct:
                    breaches.append({
                        "bucket_code": bucket.code,
                        "label": bucket.label,
                        "scenario": sc_code,
                        "scenario_label": scenarios_result[sc_code]["label"],
                        "delta_eve": row["delta_eve"],
                        "pct_tier1": pct,
                        "severity": "HIGH" if abs(pct) > breach_threshold_pct * 1.5 else "MEDIUM",
                    })
        bucket_summary.append({
            "bucket_code": bucket.code,
            "label": bucket.label,
            "delta_eve_by_scenario": delta_by_scenario,
            "max_delta_eve": round(max_delta),
            "breach": any(abs(d) / tier1_capital * 100 > breach_threshold_pct for d in delta_by_scenario.values()) if tier1_capital else False,
        })

    return {
        "reference_date": ref.date().isoformat(),
        "tier1_capital": tier1_capital,
        "breach_threshold_pct": breach_threshold_pct,
        "off_balance_included": include_off_balance,
        "scenarios": scenarios_result,
        "bucket_summary": bucket_summary,
        "breaches": breaches,
        "nb_breaches": len(breaches),
    }
