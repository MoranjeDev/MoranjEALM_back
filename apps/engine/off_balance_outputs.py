"""
Intégration du hors-bilan dans le gap de liquidité.

Les engagements hors-bilan sont convertis en flux de liquidité potentiels
pondérés par leur probabilité de tirage et leur maturité.

Types d'impact sur le gap :
- Engagements (lignes de crédit, garanties, LCs) → sorties potentielles (passif)
- LFPs (Liquid Funding Positions) → entrées potentielles (actif)
- Swaps → impact net selon le sens

Chaque item est affecté au bucket correspondant à sa maturité.
"""
from __future__ import annotations

import datetime as dt
from typing import NamedTuple

from apps.off_balance.models import OffBalanceSheetItem
from .buckets import build_buckets, Bucket


class OffBalanceFlow(NamedTuple):
    bucket_code: str
    montant: int        # positif = entrée (actif), négatif = sortie (passif)
    type_engagement: str
    devise: str


def compute_off_balance_flows(reference_date: dt.datetime | None = None) -> list[OffBalanceFlow]:
    """
    Calcule les flux hors-bilan pondérés pour le gap de liquidité.

    - reference_date : date de référence (date du jour si None)
    - Pour chaque OffBalanceSheetItem actif (date_arrete la plus récente) :
      - flux = notionnel × prob_tirage / 100
      - bucket = bucket dont la borne inf ≤ maturite < borne sup
      - LFP → flux positif (entrée)
      - autres → flux négatif (sortie)
    - Items sans maturité → bucket "call_over" (sortie immédiate)
    """
    if reference_date is None:
        from django.utils import timezone
        reference_date = timezone.now()

    buckets = build_buckets(reference_date)

    # Prendre les items de la date d'arrêté la plus récente
    last_arrete = (
        OffBalanceSheetItem.objects
        .order_by("-date_arrete")
        .values_list("date_arrete", flat=True)
        .first()
    )
    if last_arrete is None:
        return []

    items = OffBalanceSheetItem.objects.filter(date_arrete=last_arrete)
    flows: list[OffBalanceFlow] = []

    for item in items:
        weighted_amount = int(item.notionnel * item.prob_tirage_pct / 100)
        if weighted_amount == 0:
            continue

        # Déterminer le bucket
        bucket_code = _assign_bucket(item.maturite, reference_date, buckets)

        # Sens : LFP = entrée (+), tout le reste = sortie (-)
        if item.type_engagement == "lfp":
            amount = weighted_amount
        else:
            amount = -weighted_amount

        flows.append(OffBalanceFlow(
            bucket_code=bucket_code,
            montant=amount,
            type_engagement=item.type_engagement,
            devise=item.devise or "XAF",
        ))

    return flows


def _assign_bucket(maturite, reference_date: dt.datetime, buckets: list[Bucket]) -> str:
    """Assigne un item à son bucket selon sa date de maturité."""
    if maturite is None:
        # Sans maturité → call (sortie immédiate)
        return buckets[0].code if buckets else "call_over"

    # Convertir date → datetime si nécessaire
    if hasattr(maturite, "hour"):
        # déjà un datetime
        mat_dt = maturite
    else:
        mat_dt = dt.datetime.combine(maturite, dt.time.min)
        from django.utils import timezone as tz
        if tz.is_naive(mat_dt):
            import pytz
            mat_dt = pytz.UTC.localize(mat_dt)

    for bucket in buckets:
        if bucket.contains(mat_dt):
            return bucket.code

    # Au-delà du dernier bucket
    return buckets[-1].code if buckets else "inf"


def get_off_balance_by_bucket(reference_date: dt.datetime | None = None) -> dict[str, int]:
    """
    Retourne un dict {bucket_code: montant_net} pour intégration dans la synthèse.
    Montant positif = entrée nette, négatif = sortie nette.
    """
    flows = compute_off_balance_flows(reference_date)
    result: dict[str, int] = {}
    for flow in flows:
        result[flow.bucket_code] = result.get(flow.bucket_code, 0) + flow.montant
    return result
