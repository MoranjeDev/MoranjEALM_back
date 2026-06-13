"""
Maximum Cumulative Outflow (MCO).

Le MCO est le déficit de liquidité cumulé maximum observé sur la courbe
des gaps cumulés. Il représente le besoin de financement pic à couvrir.

Calcul :
1. Pour chaque bucket : gap net = entrées - sorties (depuis la synthèse)
2. Gap cumulé = somme des gaps depuis le bucket Call jusqu'au bucket courant
3. MCO = minimum des gaps cumulés (valeur la plus négative = pic de besoin)
4. Bucket MCO = bucket où le gap cumulé est minimal

Calculé pour les 3 scénarios : base, modéré, sévère.

Note : compute_synthesis() retourne net_funding (list, en millions)
indexé dans le même ordre que build_buckets(). On convertit en entiers
(MFCFA) pour la cohérence avec le hors-bilan (en XAF brut).
"""
from __future__ import annotations

import datetime as dt
from django.utils import timezone

from .synthesis import compute_synthesis, SCENARIOS
from .off_balance_outputs import get_off_balance_by_bucket
from .buckets import build_buckets


def compute_mco(include_off_balance: bool = True) -> dict:
    """
    Calcule le MCO pour les 3 scénarios.

    Retourne :
    {
      "reference_date": "...",
      "include_off_balance": true,
      "scenarios": {
        "base": {
          "buckets": [
            {
              "bucket_code": "call_over",
              "label": "Overnight (1 jour)",
              "actif": 0.0,
              "passif": 0.0,
              "gap_net": 0.0,       # en millions XAF
              "off_balance": 0,     # en XAF brut (converti en M pour le cumul)
              "gap_net_total": 0.0, # en millions XAF
              "gap_cumul": 0.0,     # en millions XAF
            },
            ...
          ],
          "mco": -25000.0,          # valeur la plus négative (en M XAF)
          "mco_bucket": "1m_2m",    # bucket où survient le MCO
          "mco_label": "+ 2 mois",
        },
        "modere": { ... },
        "severe": { ... },
      }
    }
    """
    reference_date = timezone.now()
    buckets = build_buckets(reference_date)

    # Hors-bilan par bucket (commun à tous les scénarios, en XAF brut)
    ob_by_bucket_raw: dict[str, int] = {}
    if include_off_balance:
        ob_by_bucket_raw = get_off_balance_by_bucket(reference_date)

    # Convertir le hors-bilan en millions pour homogénéité avec la synthèse
    ob_by_bucket_m: dict[str, float] = {
        k: round(v / 1_000_000, 2) for k, v in ob_by_bucket_raw.items()
    }

    result = {
        "reference_date": reference_date.date().isoformat(),
        "include_off_balance": include_off_balance,
        "scenarios": {},
    }

    for scenario in SCENARIOS:
        synthesis = compute_synthesis(scenario)

        # net_funding est une liste de NB_BUCKETS valeurs en millions
        net_funding: list[float] = synthesis.get("net_funding", [])
        bucket_labels: list[str] = synthesis.get("buckets", [])
        total_assets: list[float] = synthesis.get("total_assets", [])
        total_depense: list[float] = synthesis.get("total_depense", [])

        gap_rows: list[dict] = []
        for i, bucket in enumerate(buckets):
            gap_net = net_funding[i] if i < len(net_funding) else 0.0
            actif = total_assets[i] if i < len(total_assets) else 0.0
            passif = total_depense[i] if i < len(total_depense) else 0.0
            label = bucket_labels[i] if i < len(bucket_labels) else bucket.label
            ob_m = ob_by_bucket_m.get(bucket.code, 0.0)

            gap_rows.append({
                "bucket_code": bucket.code,
                "label": label,
                "actif": actif,
                "passif": passif,
                "gap_net": gap_net,
                "off_balance": ob_m,
                "gap_net_total": round(gap_net + ob_m, 2),
            })

        # Calculer le gap cumulé et trouver le MCO
        cumul = 0.0
        mco = 0.0
        mco_bucket: str | None = None
        mco_label: str | None = None

        for row in gap_rows:
            cumul = round(cumul + row["gap_net_total"], 2)
            row["gap_cumul"] = cumul
            if cumul < mco:
                mco = cumul
                mco_bucket = row["bucket_code"]
                mco_label = row["label"]

        result["scenarios"][scenario] = {
            "buckets": gap_rows,
            "mco": mco,
            "mco_bucket": mco_bucket,
            "mco_label": mco_label,
        }

    return result
