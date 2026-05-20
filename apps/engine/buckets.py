"""
Configuration des buckets de maturité ALM.

Reproduit fidèlement la grille temporelle de la version Symfony :
    [hier, dateMajCore, +7j, +15j, +1m, +2m, +3m, +6m, +1a, +3a, +5a, +∞]

Soit 11 buckets bornés entre ces 12 points.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from dateutil.relativedelta import relativedelta


@dataclass(frozen=True)
class Bucket:
    """Un bucket de maturité (intervalle de dates ouvert à droite)."""
    code: str            # ex: "1m_2m"
    label: str           # ex: "1 mois - 2 mois"
    start: dt.datetime
    end: Optional[dt.datetime]   # None = ouvert (∞)

    def contains(self, date: dt.datetime) -> bool:
        if self.end is None:
            return date >= self.start
        return self.start <= date < self.end


# Définition normalisée des bornes (offset par rapport à la date d'arrêté)
_OFFSETS: list[tuple[str, str, dict | None]] = [
    ("j-1",      "Hier",                  {"days": -1}),
    ("ref",      "Aujourd'hui",           {"days": 0}),
    ("7j",       "+ 7 jours",             {"days": 7}),
    ("15j",      "+ 15 jours",            {"days": 15}),
    ("1m",       "+ 1 mois",              {"months": 1}),
    ("2m",       "+ 2 mois",              {"months": 2}),
    ("3m",       "+ 3 mois",              {"months": 3}),
    ("6m",       "+ 6 mois",              {"months": 6}),
    ("1a",       "+ 1 an",                {"years": 1}),
    ("3a",       "+ 3 ans",               {"years": 3}),
    ("5a",       "+ 5 ans",               {"years": 5}),
    ("inf",      "Au-delà",               None),
]


def _apply_offset(base: dt.datetime, offset: dict | None) -> dt.datetime | None:
    if offset is None:
        return None
    return base + relativedelta(**offset)


def build_timeline(reference_date: dt.datetime) -> list[dt.datetime | None]:
    """Construit les 12 points de la timeline."""
    return [_apply_offset(reference_date, off) for _, _, off in _OFFSETS]


def build_buckets(reference_date: dt.datetime) -> list[Bucket]:
    """Retourne les 11 buckets bornés par la timeline."""
    timeline = build_timeline(reference_date)
    buckets: list[Bucket] = []
    for i in range(len(timeline) - 1):
        code_a, _, _ = _OFFSETS[i]
        code_b, _, _ = _OFFSETS[i + 1]
        label = f"{_OFFSETS[i+1][1]}"
        # Le label représente la borne supérieure (ex: "+ 1 mois")
        # car on lit le bucket comme « jusqu'à + 1 mois ».
        buckets.append(Bucket(
            code=f"{code_a}_{code_b}",
            label=label,
            start=timeline[i],
            end=timeline[i + 1],
        ))
    return buckets


# Codes de buckets utilisés dans les ratios (LCR : 30 jours)
LCR_BUCKETS = ["j-1_ref", "ref_7j", "7j_15j", "15j_1m"]  # ≤ 30 jours

NB_BUCKETS = 11
