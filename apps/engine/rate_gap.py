"""Gap de taux d'intérêt, aligné sur la route Symfony `/alm/rapports/taux`.

La version validée calcule, pour chaque bucket, un taux moyen pondéré :

    taux = somme(montant * taux / 100) * 100 / somme(montant)

Puis elle calcule une moyenne simple des taux non nuls côté actifs et côté
passifs, et enfin le spread de taux actifs - passifs.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from django.utils import timezone

from apps.inputs import models as M
from apps.parameters.models import Parameter
from .buckets import build_buckets, NB_BUCKETS

# Mapping (modèle d'input, label, champ_montant, champ_taux, champ_date_maturite)
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


def _input_to_dataframe(group):
    rows = []
    for model_cls, label, amount_field, rate_field, date_field in group:
        for obj in model_cls.objects.all():
            amount = getattr(obj, amount_field, 0) or 0
            rate = getattr(obj, rate_field, 0) or 0
            date = getattr(obj, date_field, None)
            if not date or amount == 0:
                continue
            rows.append({
                "label": label,
                "amount": float(amount),
                "rate": float(rate),
                "date": pd.Timestamp(date),
            })
    return pd.DataFrame(rows)


def _bucketize_rates(df: pd.DataFrame, ref: dt.datetime) -> dict[str, list[float]]:
    buckets = build_buckets(ref)
    if df.empty:
        return {}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    out: dict[str, list[float]] = {}
    for label, group in df.groupby("label"):
        rates = [0.0] * NB_BUCKETS
        for i, b in enumerate(buckets):
            start = pd.Timestamp(b.start).tz_convert("UTC")
            end = pd.Timestamp(b.end).tz_convert("UTC") if b.end else None
            mask = group["date"] >= start
            if end is not None:
                mask &= group["date"] < end
            bucket_rows = group.loc[mask]
            denominator = float(bucket_rows["amount"].sum())
            if denominator:
                numerator = float((bucket_rows["amount"] * bucket_rows["rate"] / 100).sum())
                rates[i] = round(numerator * 100 / denominator, 2)
        out[label] = rates
    return out


def _avg_non_zero(values: list[float]) -> float:
    non_zero = [v for v in values if v != 0]
    if not non_zero:
        return 0.0
    return round(sum(non_zero) / len(non_zero), 2)


def _avg_rates_by_bucket(table: dict[str, list[float]]) -> list[float]:
    totals: list[float] = []
    for i in range(NB_BUCKETS):
        bucket_rates = [values[i] for values in table.values() if values[i] != 0]
        totals.append(round(sum(bucket_rates) / len(bucket_rates), 2) if bucket_rates else 0.0)
    return totals


def compute_rate_gap() -> dict:
    """Calcule le gap de taux comme la page Symfony `taux`."""
    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)

    assets_df = _input_to_dataframe(ASSETS_RATE_INPUTS)
    liab_df = _input_to_dataframe(LIABILITIES_RATE_INPUTS)

    assets = _bucketize_rates(assets_df, ref)
    liabilities = _bucketize_rates(liab_df, ref)
    for _, label, *_ in ASSETS_RATE_INPUTS:
        assets.setdefault(label, [0.0] * NB_BUCKETS)
    for _, label, *_ in LIABILITIES_RATE_INPUTS:
        liabilities.setdefault(label, [0.0] * NB_BUCKETS)

    total_assets = _avg_rates_by_bucket(assets)
    total_liab = _avg_rates_by_bucket(liabilities)
    gap = [round(a - l, 2) for a, l in zip(total_assets, total_liab)]

    cum = []
    s = 0.0
    for g in gap:
        s += g
        cum.append(round(s, 2))

    return {
        "reference_date": ref.isoformat(),
        "buckets": [b.label for b in build_buckets(ref)],
        "assets": assets,
        "liabilities": liabilities,
        "asset_averages": {label: _avg_non_zero(values) for label, values in assets.items()},
        "liability_averages": {label: _avg_non_zero(values) for label, values in liabilities.items()},
        "total_assets": total_assets,
        "total_liabilities": total_liab,
        "gap": gap,
        "average_assets": _avg_non_zero(total_assets),
        "average_liabilities": _avg_non_zero(total_liab),
        "average_gap": _avg_non_zero(gap),
        "cumulative_gap": cum,
    }
