"""Blocs de data lineage exposés dans les rapports ALM."""
from __future__ import annotations

from typing import Any


def report_lineage(report: str, *, scenario: str | None = None, horizon_days: int | None = None) -> list[dict[str, Any]]:
    """Retourne une lecture courte du chemin de calcul d'un rapport.

    Le but est d'expliquer chaque agrégat devant ALCO ou audit sans noyer
    l'utilisateur dans le détail technique. Le drill-down source reste porté
    par la page de rapprochement source vs moteur.
    """
    common_sources = {
        "source": {
            "label": "Source",
            "value": "Fichiers importés dans les registres ALM, bilan GL et hors-bilan lorsque disponible.",
            "detail_url": "/outputs-control",
        },
        "mapping": {
            "label": "Mapping",
            "value": "Familles produit normalisées vers les types moteur ALM et buckets de maturité.",
            "detail_url": "/mappings",
        },
        "audit": {
            "label": "Contrôle",
            "value": "Les écarts source vs moteur sont consultables dans le rapprochement et les détails par famille.",
            "detail_url": "/outputs-control",
        },
    }

    if report == "synthesis":
        return [
            common_sources["source"],
            common_sources["mapping"],
            {
                "label": "Hypothèses",
                "value": f"Scénario {scenario or 'base'} : chocs de liquidité, paramètres comportementaux actifs, retrait anticipé, rollover et hors-bilan pondéré.",
                "detail_url": "/behavioral",
            },
            {
                "label": "Transformation",
                "value": "Outputs ventilés par bucket, ajustés par hypothèses comportementales applicables, puis agrégés en gap net et gap cumulé.",
                "detail_url": "/outputs-control",
            },
            common_sources["audit"],
        ]

    if report == "lcr":
        return [
            common_sources["source"],
            common_sources["mapping"],
            {
                "label": "Hypothèses",
                "value": "Pondérations HQLA, run-off, inflows et plafond réglementaire des entrées.",
                "detail_url": "/governance",
            },
            {
                "label": "Transformation",
                "value": "HQLA pondéré moins sorties nettes de trésorerie après plafonnement des entrées.",
                "detail_url": "/lcr",
            },
            common_sources["audit"],
        ]

    if report == "rate_gap":
        return [
            common_sources["source"],
            {
                "label": "Mapping taux",
                "value": "Produits sensibles aux taux classés par bucket, sens actif/passif et type de taux.",
                "detail_url": "/mappings",
            },
            {
                "label": "Hypothèses",
                "value": "Taux contractuels, type de taux, pass-through et délai de repricing comportemental lorsque paramétrés.",
                "detail_url": "/behavioral",
            },
            {
                "label": "Transformation",
                "value": "Positions reclassées par date de repricing ajustée, taux moyens pondérés, spread actif-passif et basis risk.",
                "detail_url": "/rate-gap",
            },
            common_sources["audit"],
        ]

    if report == "nii":
        return [
            common_sources["source"],
            {
                "label": "Mapping taux",
                "value": "Positions sensibles aux taux issues des registres actifs/passifs et classées par maturité.",
                "detail_url": "/rate-gap",
            },
            {
                "label": "Hypothèses",
                "value": f"Horizon {horizon_days or 365} jours, scénarios de chocs NII, pass-through et délai de repricing comportemental.",
                "detail_url": "/behavioral",
            },
            {
                "label": "Transformation",
                "value": "Encours proratisé, taux de base plus choc effectif après lag, revenu/charge puis delta NII.",
                "detail_url": "/nii",
            },
            common_sources["audit"],
        ]

    if report == "eve":
        return [
            common_sources["source"],
            {
                "label": "Mapping taux",
                "value": "Positions sensibles aux taux classées par maturité, sens actif/passif et bucket IRRBB.",
                "detail_url": "/rate-gap",
            },
            {
                "label": "Hypothèses",
                "value": "Scénarios EVE, floor de taux, maturité par défaut, pass-through et délai de repricing.",
                "detail_url": "/behavioral",
            },
            {
                "label": "Transformation",
                "value": "Actualisation par taux choqué effectif, PV actifs-passifs, delta EVE et breaches par bucket.",
                "detail_url": "/eve",
            },
            common_sources["audit"],
        ]

    return [common_sources["source"], common_sources["mapping"], common_sources["audit"]]
