"""
Service multi-devises : positions et gaps par devise (LCY/FCY).

Lit les inputs déclarés en devises (BTA, OTA, emprunts obligataires,
prêts interbancaires, tableau d'amortissement) plus les engagements
hors-bilan, agrège par devise et par bucket de maturité.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import pandas as pd
from django.utils import timezone

from apps.engine.buckets import build_buckets, NB_BUCKETS
from apps.inputs import models as M
from apps.mapping.models import Currency, FxRate, OffBalanceCommitment
from apps.parameters.models import Parameter


# Champs (modèle, attribut devise, attribut montant, attribut date) pour les inputs
# où la devise est explicite.
CURRENCY_INPUTS = [
    (M.InputBta,            None,       "solde",            "maturite",          "actif"),
    (M.InputOta,            None,       "solde",            "maturite",          "actif"),
    (M.InputEmpruntObl,     "devise",   "solde",            "maturite",          "actif"),
    (M.InputPretInterBanc,  "devise",   "solde",            "maturite",          "actif"),
    (M.InputTabAmort,       "devise",   "montant_echeance", "date_echeance",     "actif"),
]


def _normalize_ccy(raw: str | None) -> str:
    if not raw:
        return "XAF"
    raw = raw.strip().upper()
    if not raw or raw in ("FCFA", "F CFA", "CFA"):
        return "XAF"
    return raw[:3]


def _fx_rate(ccy: str, ref: date) -> tuple[float, bool]:
    """Convertit un montant dans la devise pivot."""
    if ccy == "XAF":
        return 1.0, False
    qs = FxRate.objects.filter(currency__code=ccy, date__lte=ref).order_by("-date").first()
    if qs is None:
        return 1.0, True
    return qs.rate, False


def _fx_to_base(amount: float, ccy: str, ref: date) -> tuple[float, bool, float]:
    rate, missing = _fx_rate(ccy, ref)
    return amount * rate, missing, rate


def _empty_side() -> dict[str, list[float]]:
    return {"actif": [0.0] * NB_BUCKETS, "passif": [0.0] * NB_BUCKETS}


def _round_sides(sides: dict[str, list[float]]) -> dict[str, list[float]]:
    return {
        "actif": [round(v, 2) for v in sides["actif"]],
        "passif": [round(v, 2) for v in sides["passif"]],
    }


def _sum(values: list[float]) -> float:
    return round(sum(values), 2)


def compute_positions_by_currency() -> dict:
    """Calcule les positions et gaps par devise."""
    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)
    ref_date = ref.date()
    buckets = build_buckets(ref)

    # Structure : {ccy: {actif|passif: [bucket1, ...]}}
    by_ccy: dict[str, dict[str, list[float]]] = defaultdict(_empty_side)
    source_breakdown: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for model_cls, ccy_attr, amount_attr, date_attr, side in CURRENCY_INPUTS:
        for obj in model_cls.objects.all():
            ccy = _normalize_ccy(getattr(obj, ccy_attr) if ccy_attr else "XAF")
            amount = getattr(obj, amount_attr) or 0
            d = getattr(obj, date_attr)
            if not d:
                continue
            ts = pd.Timestamp(d)
            for i, b in enumerate(buckets):
                if ts >= pd.Timestamp(b.start) and (b.end is None or ts < pd.Timestamp(b.end)):
                    by_ccy[ccy][side][i] += float(amount)
                    source_breakdown[ccy][model_cls._meta.verbose_name] += float(amount)
                    break

    # Ajouter les engagements hors-bilan
    for cmt in OffBalanceCommitment.objects.filter(is_active=True):
        if not cmt.maturity_date:
            continue
        ccy = cmt.currency.code if cmt.currency else "XAF"
        ts = pd.Timestamp(cmt.maturity_date)
        side = "passif" if cmt.type in ("credit_line", "undrawn_facility", "loc", "guarantee") else "actif"
        for i, b in enumerate(buckets):
            if ts >= pd.Timestamp(b.start) and (b.end is None or ts < pd.Timestamp(b.end)):
                amount = float(cmt.notional) * (cmt.drawdown_pct / 100.0 if cmt.drawdown_pct else 0)
                by_ccy[ccy][side][i] += amount
                source_breakdown[ccy]["Engagement hors-bilan"] += amount
                break

    # Sortie : LCY (XAF) + FCY (toutes les autres) + total agrégé
    result = []
    total_lcy = _empty_side()
    total_fcy = _empty_side()
    total_all = _empty_side()
    missing_fx: list[str] = []

    for ccy, sides in sorted(by_ccy.items()):
        is_lcy = ccy == "XAF"
        # En millions FCFA
        fx_rate, fx_missing = _fx_rate(ccy, ref_date)
        if fx_missing:
            missing_fx.append(ccy)
        actifs_m = [round(_fx_to_base(v, ccy, ref_date)[0] / 1_000_000, 2) for v in sides["actif"]]
        passifs_m = [round(_fx_to_base(v, ccy, ref_date)[0] / 1_000_000, 2) for v in sides["passif"]]
        gap = [round(a - p, 2) for a, p in zip(actifs_m, passifs_m)]
        actif_total = _sum(actifs_m)
        passif_total = _sum(passifs_m)
        net_total = round(actif_total - passif_total, 2)
        worst_gap = min(gap, key=lambda x: x) if gap else 0.0
        worst_gap_index = gap.index(worst_gap) if gap else 0

        result.append({
            "currency": ccy,
            "is_lcy": is_lcy,
            "fx_rate": round(fx_rate, 6),
            "fx_missing": fx_missing,
            "actifs": actifs_m,
            "passifs": passifs_m,
            "gap": gap,
            "actif_total": actif_total,
            "passif_total": passif_total,
            "net_total": net_total,
            "absolute_net_total": round(abs(net_total), 2),
            "worst_gap": round(worst_gap, 2),
            "worst_bucket": buckets[worst_gap_index].label if buckets else "",
            "source_breakdown": [
                {
                    "source": source,
                    "amount": round(amount, 2),
                    "amount_m_base": round(amount * fx_rate / 1_000_000, 2),
                }
                for source, amount in sorted(source_breakdown[ccy].items(), key=lambda item: -item[1])
            ],
        })

        target = total_lcy if is_lcy else total_fcy
        for i in range(NB_BUCKETS):
            target["actif"][i] += actifs_m[i]
            target["passif"][i] += passifs_m[i]
            total_all["actif"][i] += actifs_m[i]
            total_all["passif"][i] += passifs_m[i]

    result = sorted(result, key=lambda row: row["absolute_net_total"], reverse=True)
    total_lcy = _round_sides(total_lcy)
    total_fcy = _round_sides(total_fcy)
    total_all = _round_sides(total_all)
    lcy_assets = _sum(total_lcy["actif"])
    lcy_liabilities = _sum(total_lcy["passif"])
    fcy_assets = _sum(total_fcy["actif"])
    fcy_liabilities = _sum(total_fcy["passif"])
    total_assets = _sum(total_all["actif"])
    total_liabilities = _sum(total_all["passif"])
    total_balance = total_assets + total_liabilities
    fcy_balance = fcy_assets + fcy_liabilities
    fcy_gap = [round(a - p, 2) for a, p in zip(total_fcy["actif"], total_fcy["passif"])]
    total_gap = [round(a - p, 2) for a, p in zip(total_all["actif"], total_all["passif"])]
    worst_currency = result[0] if result else None
    worst_bucket_value = min(total_gap, key=lambda x: x) if total_gap else 0.0
    worst_bucket_index = total_gap.index(worst_bucket_value) if total_gap else 0

    return {
        "reference_date": ref.isoformat(),
        "buckets": [b.label for b in buckets],
        "by_currency": result,
        "lcy": total_lcy,
        "fcy": total_fcy,
        "total": total_all,
        "summary": {
            "lcy_assets": lcy_assets,
            "lcy_liabilities": lcy_liabilities,
            "lcy_net": round(lcy_assets - lcy_liabilities, 2),
            "fcy_assets": fcy_assets,
            "fcy_liabilities": fcy_liabilities,
            "fcy_net": round(fcy_assets - fcy_liabilities, 2),
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_net": round(total_assets - total_liabilities, 2),
            "fcy_share_pct": round(fcy_balance / total_balance * 100, 2) if total_balance else 0.0,
            "currency_count": len(result),
            "fcy_currency_count": len([row for row in result if not row["is_lcy"]]),
            "worst_currency": worst_currency,
            "worst_bucket": buckets[worst_bucket_index].label if buckets else "",
            "worst_bucket_gap": round(worst_bucket_value, 2),
            "fcy_gap": fcy_gap,
            "total_gap": total_gap,
        },
        "alerts": [
            f"Taux de change manquant pour {ccy}: les montants sont repris sans conversion."
            for ccy in sorted(set(missing_fx))
        ],
    }
