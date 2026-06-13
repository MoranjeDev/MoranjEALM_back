"""
Résolveur de paramètres comportementaux pour le moteur de calcul.

Remplace l'utilisation des scalaires globaux du Parameter singleton
(stable_courant, stable_cheque, etc.) par les BehavioralDistributionParam
par segment.

Logique de fallback :
1. BehavioralDistributionParam actif le plus spécifique (product × segment × BU)
2. BehavioralDistributionParam par défaut (is_default=True)
3. Scalaires du Parameter singleton (compatibilité ascendante)
"""
from __future__ import annotations

from apps.behavioral.models import BehavioralDistributionParam
from apps.parameters.models import Parameter


# Mapping produit ALM → product_type BehavioralDistributionParam
PRODUCT_MAP = {
    "compte_371": "compte_courant",
    "compte_372": "compte_cheque",
    "compte_373": "compte_livret",
    "compte_vue_cor": "cpte_corr",
    "credit": "credit_corporate",
    "depot_terme": "depot_terme",
    "bon": "bon_caisse",
}


def resolve_behavioral_params(
    product_kind: str,
    segment: str = "all",
    business_unit: str = "",
    secteur: str = "",
    devise: str = "",
) -> dict:
    """
    Retourne un dict de paramètres comportementaux pour un produit/segment.

    Toujours retourne un dict valide (fallback sur Parameter singleton si besoin).

    Champs retournés :
    - stable_core_pct, stable_non_core_pct, volatile_pct
    - runoff_core_months, runoff_non_core_months
    - repricing_lag_months, pass_through_pct
    - cpr_annual_pct, early_withdrawal_pct, rollover_rate_pct
    - source: "behavioral_param" | "parameter_singleton" | "hardcoded_default"
    """
    product_type = PRODUCT_MAP.get(product_kind, product_kind)

    # Essayer BehavioralDistributionParam
    param = BehavioralDistributionParam.resolve(
        product_type=product_type,
        segment=segment,
        business_unit=business_unit,
        secteur=secteur,
        devise=devise,
    )
    if param:
        return {
            "stable_core_pct": param.stable_core_pct,
            "stable_non_core_pct": param.stable_non_core_pct,
            "volatile_pct": param.volatile_pct,
            "runoff_core_months": param.runoff_core_months,
            "runoff_non_core_months": param.runoff_non_core_months,
            "repricing_lag_months": param.repricing_lag_months,
            "pass_through_pct": param.pass_through_pct,
            "cpr_annual_pct": param.cpr_annual_pct,
            "early_withdrawal_pct": param.early_withdrawal_pct,
            "rollover_rate_pct": param.rollover_rate_pct,
            "source": "behavioral_param",
            "param_code": param.code,
        }

    # Fallback : Parameter singleton
    try:
        p = Parameter.objects.first()
        if p:
            stable_map = {
                "compte_courant": getattr(p, "stable_courant", 50.0) or 50.0,
                "compte_cheque":  getattr(p, "stable_cheque", 50.0) or 50.0,
                "compte_livret":  getattr(p, "stable_livret", 50.0) or 50.0,
                "cpte_corr":      getattr(p, "stable_corr", 50.0) or 50.0,
                "beac":           getattr(p, "stable_beac", 50.0) or 50.0,
            }
            stable = stable_map.get(product_type, 50.0)
            return {
                "stable_core_pct": stable * 0.7,
                "stable_non_core_pct": stable * 0.3,
                "volatile_pct": 100.0 - stable,
                "runoff_core_months": 60,
                "runoff_non_core_months": 24,
                "repricing_lag_months": 1,
                "pass_through_pct": 50.0,
                "cpr_annual_pct": 0.0,
                "early_withdrawal_pct": 0.0,
                "rollover_rate_pct": 0.0,
                "source": "parameter_singleton",
            }
    except Exception:
        pass

    # Fallback ultime
    return {
        "stable_core_pct": 50.0,
        "stable_non_core_pct": 15.0,
        "volatile_pct": 35.0,
        "runoff_core_months": 36,
        "runoff_non_core_months": 12,
        "repricing_lag_months": 1,
        "pass_through_pct": 50.0,
        "cpr_annual_pct": 0.0,
        "early_withdrawal_pct": 0.0,
        "rollover_rate_pct": 0.0,
        "source": "hardcoded_default",
    }
