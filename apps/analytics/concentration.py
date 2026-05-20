"""
Analyse de concentration — dépôts et actifs.

- Top N : N plus grosses positions par déposant ou par contrepartie.
- Indice de Herfindahl-Hirschman (HHI) : Σ (part_i)^2.
  HHI < 1500 : marché peu concentré.
  HHI 1500-2500 : modérément concentré.
  HHI > 2500 : très concentré.
"""
from __future__ import annotations

from collections import defaultdict

from apps.inputs import models as M
from apps.parameters.models import Parameter


# Mapping (modèle, attribut clé, attribut montant, label)
DEPOSIT_SOURCES = [
    (M.InputDepotTerme,    "compte_client", "montant",     "Dépôt à terme"),
    (M.InputBonCaisse,     "compte_client", "montant",     "Bon de caisse"),
    (M.InputCompteCourant, None,            "cumul",       "Compte 371"),
    (M.InputCompteCheque,  None,            "cumul",       "Compte 372"),
    (M.InputCompteLivret,  None,            "cumul",       "Compte 373"),
]

ASSET_SOURCES = [
    (M.InputCredit,           "num_dossier",   "capital_restant", "Crédit"),
    (M.InputBta,              "nom_client",    "solde",           "BTA"),
    (M.InputOta,              "code_emission", "solde",           "OTA"),
    (M.InputEmpruntObl,       "nom_client",    "solde",           "Emp. obl."),
    (M.InputPretInterBanc,    "contrepartie",  "solde",           "Prêt interbanc."),
    (M.InputPretCor,          "num_dossier",   "capital_restant", "Prêt corresp."),
]


def _aggregate(sources: list[tuple]) -> list[tuple[str, float, str]]:
    """Retourne une liste (clé, montant, type) agrégée."""
    bucket: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "labels": set()})
    for model_cls, key_attr, amount_attr, label in sources:
        queryset = model_cls.objects.all()
        if key_attr is None:
            latest = queryset.first()
            queryset = [latest] if latest else []
        for obj in queryset:
            key = getattr(obj, key_attr) if key_attr else label
            amount = getattr(obj, amount_attr)
            try:
                amount = float(amount or 0)
            except (TypeError, ValueError):
                amount = 0.0
            if amount <= 0:
                continue
            bucket[str(key)]["amount"] += amount
            bucket[str(key)]["labels"].add(label)
    return [(k, v["amount"], ", ".join(sorted(v["labels"]))) for k, v in bucket.items()]


def _herfindahl(values: list[float]) -> float:
    total = sum(values)
    if total <= 0:
        return 0.0
    return round(sum((v / total * 100) ** 2 for v in values), 2)


def _top_n(items: list, n: int = 20) -> list[dict]:
    sorted_items = sorted(items, key=lambda x: -x[1])[:n]
    total = sum(x[1] for x in items)
    return [
        {
            "rank": i + 1,
            "key": k,
            "type": t,
            "amount": round(amount, 2),
            "amount_m": round(amount / 1_000_000, 2),
            "share_pct": round(amount / total * 100, 2) if total else 0.0,
        }
        for i, (k, amount, t) in enumerate(sorted_items)
    ]


def _hhi_level(hhi: float) -> str:
    if hhi < 1500:
        return "Peu concentré"
    if hhi < 2500:
        return "Modérément concentré"
    return "Très concentré"


def _share_for_top(items: list, size: int) -> float:
    total = sum(x[1] for x in items)
    if not total:
        return 0.0
    return round(sum(x[1] for x in sorted(items, key=lambda x: -x[1])[:size]) / total * 100, 2)


def _type_breakdown(items: list[tuple[str, float, str]]) -> list[dict]:
    totals: dict[str, float] = defaultdict(float)
    total = sum(amount for _, amount, _ in items)
    for _, amount, label in items:
        for part in [p.strip() for p in label.split(",") if p.strip()]:
            totals[part] += amount
    return [
        {
            "type": key,
            "amount": round(amount, 2),
            "amount_m": round(amount / 1_000_000, 2),
            "share_pct": round(amount / total * 100, 2) if total else 0.0,
        }
        for key, amount in sorted(totals.items(), key=lambda item: -item[1])
    ]


def _block(items: list[tuple[str, float, str]], n: int) -> dict:
    total = sum(x[1] for x in items)
    hhi = _herfindahl([x[1] for x in items])
    top = _top_n(items, n)
    return {
        "count": len(items),
        "total": round(total, 2),
        "total_m": round(total / 1_000_000, 2),
        "hhi": hhi,
        "hhi_level": _hhi_level(hhi),
        "top_1_pct": _share_for_top(items, 1),
        "top_5_pct": _share_for_top(items, 5),
        "top_10_pct": _share_for_top(items, 10),
        "top_n": top,
        "top_n_pct": _share_for_top(items, n),
        "max_exposure": top[0] if top else None,
        "type_breakdown": _type_breakdown(items),
    }


def compute_concentration(n: int = 20) -> dict:
    param = Parameter.get_solo()
    reference_date = param.dateMajCore
    deposits = _aggregate(DEPOSIT_SOURCES)
    assets = _aggregate(ASSET_SOURCES)

    return {
        "reference_date": reference_date.isoformat() if reference_date else None,
        "n": n,
        "notes": [
            "Les comptes 371/372/373 sont disponibles comme soldes agrégés, pas par déposant individuel.",
            "Le HHI est calculé sur les clés disponibles : compte client, contrepartie, émission ou dossier selon la source.",
        ],
        "deposits": _block(deposits, n),
        "assets": _block(assets, n),
    }
