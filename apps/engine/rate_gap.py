"""
Gap de taux d'intérêt enrichi.

Version 2 : ventilation par type de taux pour l'analyse du basis risk.

Le basis risk survient quand les actifs et passifs d'un même bucket
ne repricent pas sur la même base (ex : actifs indexés EURIBOR vs passifs
à taux fixe → risque si EURIBOR monte).

Structure de retour :
- by_bucket : gap agrégé par bucket (rétrocompatible v1)
- by_bucket_and_type : matrice {bucket: {type_taux: {actif, passif, gap, taux_actif, taux_passif}}}
- basis_risk : par bucket, écart de taux entre types (fixed vs variable, etc.)
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from django.utils import timezone

from apps.inputs import models as M
from .buckets import build_buckets
from .lineage import report_lineage
from .rate_behavior import rate_behavior_for_input

# Même mapping que la v1 + ajout du champ type_taux si disponible
ASSETS_RATE_INPUTS = [
    (M.InputCredit,        "credit",        "capital_restant",  "taux_interet", "date_deu_echeance"),
    (M.InputBta,           "bta",           "solde",            "taux_int",     "maturite"),
    (M.InputOta,           "ota",           "solde",            "taux_int",     "maturite"),
    (M.InputEmpruntObl,    "emprunt_obl",   "solde",            "taux_int",     "maturite"),
    (M.InputTerme,         "pret_ter_cor",  "montant",          "taux_int",     "maturite"),
    (M.InputPretCor,       "pret_cor",      "capital_restant",  "taux_interet", "date_dern_echeance"),
    (M.InputPretTitre,     "pret_titre",    "montant",          "taux_integer", "date_echeance"),
    (M.InputPretInterBanc, "inter_blanc",   "solde",            "taux_int",     "maturite"),
    (M.InputDecouvert,     "decouvert",     "montant",          "taux_auto",    "date_fin"),
]

LIABILITIES_RATE_INPUTS = [
    (M.InputPensionLivree,    "pension_livree",     "montant",                  "taux_interet", "echeance"),
    (M.InputEmpruntInter,     "emprunt_inter_banc", "montant",                  "taux_interet", "echance"),
    (M.InputDepotTerme,       "depot_terme",        "montant",                  "taux_interet", "maturite"),
    (M.InputBonCaisse,        "bon",                "montant",                  "taux",         "maturite"),
    (M.InputAvanceBeac,       "avance_beac",        "montant_total_rembourse",  "taux",         "echeance"),
    (M.InputEmpruntTitre,     "emprunt_titre",      "montant_total_rembourse",  "taux",         "echeance"),
]

TYPE_TAUX_LABELS = {
    "fixe":       "Taux fixe",
    "variable":   "Taux variable",
    "administre": "Taux administré (BEAC/TIAO)",
    "indexe":     "Taux indexé (EURIBOR/SOFR)",
    "revisable":  "Taux révisable",
}


def _input_to_dataframe(group):
    rows = []
    current_tz = timezone.get_current_timezone()
    for model_cls, label, amount_field, rate_field, date_field in group:
        for obj in model_cls.objects.all():
            amount = getattr(obj, amount_field, 0) or 0
            rate = getattr(obj, rate_field, 0) or 0
            date = getattr(obj, date_field, None)
            type_taux = getattr(obj, "type_taux", "fixe") or "fixe"
            if not date or amount == 0:
                continue
            timestamp = pd.Timestamp(date)
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize(current_tz)
            else:
                timestamp = timestamp.tz_convert(current_tz)
            behavior = rate_behavior_for_input(label, obj)
            repricing_timestamp = timestamp + pd.DateOffset(months=behavior.repricing_lag_months)
            rows.append({
                "label": label,
                "amount": float(amount),
                "rate": float(rate),
                "date": repricing_timestamp,
                "contractual_date": timestamp,
                "type_taux": type_taux,
                "repricing_lag_months": behavior.repricing_lag_months,
                "pass_through_pct": behavior.pass_through_pct,
                "behavioral_source": behavior.source,
                "behavioral_param_code": behavior.param_code,
            })
    return pd.DataFrame(rows)


def _average_non_zero(values: list[float]) -> float:
    non_zero = [float(v) for v in values if float(v or 0) != 0]
    if not non_zero:
        return 0.0
    return sum(non_zero) / len(non_zero)


def _rate_series_by_label(df: pd.DataFrame, label: str, buckets) -> list[float]:
    if df.empty:
        return [0.0 for _ in buckets]
    subset = df[df["label"] == label]
    return [round(_weighted_rate(subset, bucket), 4) for bucket in buckets]


def compute_rate_gap_enriched() -> dict:
    """
    Calcule le gap de taux enrichi avec ventilation par type de taux.
    Compatible avec la v1 pour le champ by_bucket.
    """
    reference_date = timezone.now()
    buckets = build_buckets(reference_date)

    df_assets = _input_to_dataframe(ASSETS_RATE_INPUTS)
    df_liab = _input_to_dataframe(LIABILITIES_RATE_INPUTS)

    # --- Structure par bucket ---
    by_bucket = []
    for bucket in buckets:
        a_row = _bucket_stats(df_assets, bucket)
        l_row = _bucket_stats(df_liab, bucket)
        taux_a = _weighted_rate(df_assets, bucket)
        taux_l = _weighted_rate(df_liab, bucket)
        by_bucket.append({
            "bucket_code": bucket.code,
            "label": bucket.label,
            "actif_amount": a_row["amount"],
            "passif_amount": l_row["amount"],
            "gap": a_row["amount"] - l_row["amount"],
            "taux_actif": round(taux_a, 4),
            "taux_passif": round(taux_l, 4),
            "spread": round(taux_a - taux_l, 4),
        })

    # --- Matrice by_bucket_and_type ---
    by_bucket_and_type: dict[str, dict] = {}
    all_types = list(TYPE_TAUX_LABELS.keys())

    for bucket in buckets:
        bc = bucket.code
        by_bucket_and_type[bc] = {"label": bucket.label, "types": {}}
        for ttype in all_types:
            a_amt = _bucket_amount_by_type(df_assets, bucket, ttype)
            l_amt = _bucket_amount_by_type(df_liab, bucket, ttype)
            a_rate = _weighted_rate_by_type(df_assets, bucket, ttype)
            l_rate = _weighted_rate_by_type(df_liab, bucket, ttype)
            if a_amt > 0 or l_amt > 0:
                by_bucket_and_type[bc]["types"][ttype] = {
                    "label": TYPE_TAUX_LABELS[ttype],
                    "actif": a_amt,
                    "passif": l_amt,
                    "gap": a_amt - l_amt,
                    "taux_actif": round(a_rate, 4),
                    "taux_passif": round(l_rate, 4),
                    "basis_risk": round(a_rate - l_rate, 4),
                }

    # --- Basis risk summary ---
    basis_risk_summary = _compute_basis_risk(by_bucket_and_type)
    rate_behavior_summary = _rate_behavior_summary(df_assets, df_liab)

    return {
        "reference_date": reference_date.date().isoformat(),
        "lineage": report_lineage("rate_gap"),
        "by_bucket": by_bucket,
        "by_bucket_and_type": by_bucket_and_type,
        "basis_risk_summary": basis_risk_summary,
        "rate_behavior_summary": rate_behavior_summary,
    }


def _rate_behavior_summary(df_assets: pd.DataFrame, df_liab: pd.DataFrame) -> list[dict]:
    rows = []
    for side, df in [("asset", df_assets), ("liability", df_liab)]:
        if df.empty or "repricing_lag_months" not in df.columns:
            continue
        grouped = df.groupby(["label", "behavioral_source", "behavioral_param_code"], dropna=False)
        for (label, source, param_code), subset in grouped:
            amount = float(subset["amount"].sum())
            if amount == 0:
                continue
            rows.append({
                "label": label,
                "side": side,
                "amount": round(amount, 2),
                "repricing_lag_months": round(float((subset["amount"] * subset["repricing_lag_months"]).sum() / amount), 2),
                "pass_through_pct": round(float((subset["amount"] * subset["pass_through_pct"]).sum() / amount), 2),
                "source": source or "not_applicable",
                "param_code": param_code or "",
            })
    return sorted(rows, key=lambda row: (row["side"], row["label"], row["source"]))


def _bucket_stats(df: pd.DataFrame, bucket) -> dict:
    if df.empty:
        return {"amount": 0}
    mask = df["date"].apply(bucket.contains)
    subset = df[mask]
    return {"amount": int(subset["amount"].sum()) if not subset.empty else 0}


def _weighted_rate(df: pd.DataFrame, bucket) -> float:
    if df.empty:
        return 0.0
    mask = df["date"].apply(bucket.contains)
    subset = df[mask]
    if subset.empty or subset["amount"].sum() == 0:
        return 0.0
    return float((subset["amount"] * subset["rate"]).sum() / subset["amount"].sum())


def _bucket_amount_by_type(df: pd.DataFrame, bucket, ttype: str) -> int:
    if df.empty:
        return 0
    mask = df["date"].apply(bucket.contains) & (df["type_taux"] == ttype)
    subset = df[mask]
    return int(subset["amount"].sum()) if not subset.empty else 0


def _weighted_rate_by_type(df: pd.DataFrame, bucket, ttype: str) -> float:
    if df.empty:
        return 0.0
    mask = df["date"].apply(bucket.contains) & (df["type_taux"] == ttype)
    subset = df[mask]
    if subset.empty or subset["amount"].sum() == 0:
        return 0.0
    return float((subset["amount"] * subset["rate"]).sum() / subset["amount"].sum())


def _compute_basis_risk(by_bucket_and_type: dict) -> list[dict]:
    """Identifie les buckets avec un basis risk significatif (> 0.5%)."""
    alerts = []
    for bc, data in by_bucket_and_type.items():
        types = data.get("types", {})
        rates = [(t, v["taux_actif"], v["taux_passif"]) for t, v in types.items()]
        if len(rates) > 1:
            actif_rates = [r for _, r, _ in rates if r > 0]
            passif_rates = [p for _, _, p in rates if p > 0]
            if actif_rates and passif_rates:
                max_spread = max(actif_rates) - min(passif_rates)
                if abs(max_spread) > 0.5:
                    alerts.append({
                        "bucket_code": bc,
                        "label": data["label"],
                        "max_basis_spread": round(max_spread, 4),
                        "severity": "HIGH" if abs(max_spread) > 2 else "MEDIUM",
                        "types_present": list(types.keys()),
                    })
    return alerts


def compute_rate_gap():
    """Retourne le format historique attendu par la page/PDF + les champs enrichis.

    La page Gap de taux et les exports consomment des séries de taux moyens
    par famille de produit. Le calcul enrichi garde en plus la ventilation par
    type de taux pour le basis risk.
    """
    enriched = compute_rate_gap_enriched()
    reference_date = timezone.now()
    buckets = build_buckets(reference_date)
    bucket_labels = [bucket.label for bucket in buckets]

    df_assets = _input_to_dataframe(ASSETS_RATE_INPUTS)
    df_liabilities = _input_to_dataframe(LIABILITIES_RATE_INPUTS)

    assets: dict[str, list[float]] = {}
    liabilities: dict[str, list[float]] = {}
    asset_averages: dict[str, float] = {}
    liability_averages: dict[str, float] = {}

    for _, label, *_ in ASSETS_RATE_INPUTS:
        series = _rate_series_by_label(df_assets, label, buckets)
        assets[label] = series
        asset_averages[label] = round(_average_non_zero(series), 4)

    for _, label, *_ in LIABILITIES_RATE_INPUTS:
        series = _rate_series_by_label(df_liabilities, label, buckets)
        liabilities[label] = series
        liability_averages[label] = round(_average_non_zero(series), 4)

    total_assets = [float(row["taux_actif"]) for row in enriched["by_bucket"]]
    total_liabilities = [float(row["taux_passif"]) for row in enriched["by_bucket"]]
    gap = [round(a - l, 4) for a, l in zip(total_assets, total_liabilities)]
    average_assets = round(_average_non_zero(total_assets), 4)
    average_liabilities = round(_average_non_zero(total_liabilities), 4)
    average_gap = round(average_assets - average_liabilities, 4)

    cumulative_gap = []
    running = 0.0
    for value in gap:
        running += value
        cumulative_gap.append(round(running, 4))

    return {
        "reference_date": enriched["reference_date"],
        "lineage": enriched["lineage"],
        "buckets": bucket_labels,
        "assets": assets,
        "liabilities": liabilities,
        "asset_averages": asset_averages,
        "liability_averages": liability_averages,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "gap": gap,
        "average_assets": average_assets,
        "average_liabilities": average_liabilities,
        "average_gap": average_gap,
        "cumulative_gap": cumulative_gap,
        "by_bucket": enriched["by_bucket"],
        "by_bucket_and_type": enriched["by_bucket_and_type"],
        "basis_risk_summary": enriched["basis_risk_summary"],
        "rate_behavior_summary": enriched["rate_behavior_summary"],
    }
