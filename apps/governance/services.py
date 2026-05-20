"""Services d'accès aux hypothèses gouvernées.

Les calculs ALM doivent lire les hypothèses actives ici plutôt que garder des
constantes cachées dans les moteurs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from apps.parameters.models import Parameter
from .models import Assumption, AssumptionVersion

_STANDARD_ASSUMPTIONS_ENSURED = False


@dataclass(frozen=True)
class StandardAssumption:
    code: str
    label: str
    category: str
    default: float
    description: str
    methodology: str = ""
    sources: str = "Catalogue standard MoranjEALM"
    payload: dict[str, Any] = field(default_factory=dict)


def _parameter_defaults() -> dict[str, float]:
    param = Parameter.get_solo()
    return {
        "stress_credit_modere_pct": float(param.credMod),
        "stress_credit_severe_pct": float(param.credSev),
        "stress_bank_modere_pct": float(param.banMod),
        "stress_bank_severe_pct": float(param.banSev),
        "stress_retail_withdrawal_modere_pct": float(param.retMod),
        "stress_retail_withdrawal_severe_pct": float(param.retSev),
        "stress_term_deposit_modere_pct": float(param.guiMod),
        "stress_term_deposit_severe_pct": float(param.guiSev),
    }


def standard_assumptions() -> list[StandardAssumption]:
    p = _parameter_defaults()
    return [
        StandardAssumption("stress_credit_modere_pct", "Stress crédit modéré", "stress_scenario", p["stress_credit_modere_pct"], "Décote appliquée aux crédits en scénario modéré."),
        StandardAssumption("stress_credit_severe_pct", "Stress crédit sévère", "stress_scenario", p["stress_credit_severe_pct"], "Décote appliquée aux crédits en scénario sévère."),
        StandardAssumption("stress_bank_modere_pct", "Stress banques modéré", "stress_scenario", p["stress_bank_modere_pct"], "Décote appliquée aux positions banques, BEAC et découverts en scénario modéré."),
        StandardAssumption("stress_bank_severe_pct", "Stress banques sévère", "stress_scenario", p["stress_bank_severe_pct"], "Décote appliquée aux positions banques, BEAC et découverts en scénario sévère."),
        StandardAssumption("stress_retail_withdrawal_modere_pct", "Retrait dépôts modéré", "withdrawal", p["stress_retail_withdrawal_modere_pct"], "Majoration des sorties comportementales des comptes 371/372/373/vue correspondants en scénario modéré."),
        StandardAssumption("stress_retail_withdrawal_severe_pct", "Retrait dépôts sévère", "withdrawal", p["stress_retail_withdrawal_severe_pct"], "Majoration des sorties comportementales des comptes 371/372/373/vue correspondants en scénario sévère."),
        StandardAssumption("stress_term_deposit_modere_pct", "Guichet DAT modéré", "withdrawal", p["stress_term_deposit_modere_pct"], "Majoration des sorties dépôts à terme en scénario modéré."),
        StandardAssumption("stress_term_deposit_severe_pct", "Guichet DAT sévère", "withdrawal", p["stress_term_deposit_severe_pct"], "Majoration des sorties dépôts à terme en scénario sévère."),
        StandardAssumption("lcr_level2_haircut_pct", "Haircut LCR actifs niveau 2", "stress_scenario", 15.0, "Décote appliquée aux actifs liquides de niveau 2, notamment OPCVM/SICAV."),
        StandardAssumption("lcr_level1_weight_pct", "Pondération LCR actifs niveau 1", "stress_scenario", 100.0, "Pondération appliquée aux actifs liquides de niveau 1."),
        StandardAssumption("lcr_retail_inflow_weight_pct", "Pondération entrées clientèle LCR", "stress_scenario", 50.0, "Pondération des entrées de trésorerie des particuliers/personnes morales dans 30 jours."),
        StandardAssumption("lcr_financial_inflow_weight_pct", "Pondération entrées financières LCR", "stress_scenario", 100.0, "Pondération des échéances de créances sur entreprises financières dans 30 jours."),
        StandardAssumption("lcr_sight_financial_claim_weight_pct", "Pondération créances financières à vue LCR", "stress_scenario", 0.0, "Pondération des créances à vue sur entreprises financières."),
        StandardAssumption("lcr_retail_deposit_runoff_pct", "Run-off dépôts particuliers LCR", "withdrawal", 10.0, "Pondération des sorties sur dépôts particuliers à vue ou à terme dans 30 jours."),
        StandardAssumption("lcr_corporate_deposit_runoff_pct", "Run-off dépôts entreprises LCR", "withdrawal", 40.0, "Pondération des sorties sur dépôts entreprises à vue ou à terme dans 30 jours."),
        StandardAssumption("lcr_financial_outflow_runoff_pct", "Run-off entreprises financières LCR", "withdrawal", 100.0, "Pondération des dépôts et emprunts des entreprises financières."),
        StandardAssumption("lcr_other_due_runoff_pct", "Run-off autres passifs exigibles LCR", "withdrawal", 100.0, "Pondération des autres dépôts et emprunts exigibles du passif."),
        StandardAssumption("lcr_guarantee_runoff_pct", "Run-off garanties LCR", "withdrawal", 5.0, "Pondération des sorties relatives aux garanties et obligations conditionnelles."),
        StandardAssumption("lcr_equity_weight_pct", "Pondération LCR actions éligibles", "stress_scenario", 50.0, "Pondération des actions non émises par une entreprise financière."),
        StandardAssumption("lcr_inflow_cap_pct", "Plafond des entrées LCR", "stress_scenario", 75.0, "Part maximale des sorties pondérées pouvant être compensée par les entrées."),
        StandardAssumption("lcr_minimum_ratio_pct", "Minimum réglementaire LCR", "stress_scenario", 100.0, "Seuil de conformité LCR."),
        StandardAssumption("irrbb_default_maturity_years", "Maturité défaut IRRBB", "rate_shock", 5.0, "Maturité utilisée pour les positions sensibles aux taux sans échéance renseignée."),
        StandardAssumption("eve_rate_floor_pct", "Floor taux EVE", "rate_shock", -1.0, "Plancher de taux appliqué après choc dans le calcul EVE."),
        StandardAssumption("nii_parallel_up_100_bp", "NII choc parallèle +100 bp", "rate_shock", 100.0, "Choc parallèle haussier utilisé dans le NII."),
        StandardAssumption("nii_parallel_down_100_bp", "NII choc parallèle -100 bp", "rate_shock", -100.0, "Choc parallèle baissier utilisé dans le NII."),
        StandardAssumption("nii_parallel_up_200_bp", "NII choc parallèle +200 bp", "rate_shock", 200.0, "Choc parallèle haussier fort utilisé dans le NII."),
        StandardAssumption("nii_parallel_down_200_bp", "NII choc parallèle -200 bp", "rate_shock", -200.0, "Choc parallèle baissier fort utilisé dans le NII."),
        StandardAssumption("nii_short_up_bp", "NII court terme +100 bp", "rate_shock", 100.0, "Choc court terme haussier utilisé dans le NII."),
        StandardAssumption("nii_short_down_bp", "NII court terme -100 bp", "rate_shock", -100.0, "Choc court terme baissier utilisé dans le NII."),
        StandardAssumption("nii_steepener_short_bp", "NII steepener court terme", "rate_shock", -65.0, "Jambe courte du scénario steepener NII."),
        StandardAssumption("nii_steepener_long_bp", "NII steepener long terme", "rate_shock", 90.0, "Jambe longue du scénario steepener NII."),
        StandardAssumption("nii_flattener_short_bp", "NII flattener court terme", "rate_shock", 90.0, "Jambe courte du scénario flattener NII."),
        StandardAssumption("nii_flattener_long_bp", "NII flattener long terme", "rate_shock", -65.0, "Jambe longue du scénario flattener NII."),
        StandardAssumption("eve_parallel_up_200_bp", "EVE choc parallèle +200 bp", "rate_shock", 200.0, "Choc parallèle haussier utilisé dans l'EVE."),
        StandardAssumption("eve_parallel_down_200_bp", "EVE choc parallèle -200 bp", "rate_shock", -200.0, "Choc parallèle baissier utilisé dans l'EVE."),
        StandardAssumption("eve_steepener_short_bp", "EVE steepener court terme", "rate_shock", -65.0, "Jambe courte du scénario steepener EVE."),
        StandardAssumption("eve_steepener_long_bp", "EVE steepener long terme", "rate_shock", 90.0, "Jambe longue du scénario steepener EVE."),
        StandardAssumption("eve_flattener_short_bp", "EVE flattener court terme", "rate_shock", 90.0, "Jambe courte du scénario flattener EVE."),
        StandardAssumption("eve_flattener_long_bp", "EVE flattener long terme", "rate_shock", -65.0, "Jambe longue du scénario flattener EVE."),
        StandardAssumption("eve_short_up_bp", "EVE court terme +100 bp", "rate_shock", 100.0, "Choc court terme haussier utilisé dans l'EVE."),
        StandardAssumption("eve_short_down_bp", "EVE court terme -100 bp", "rate_shock", -100.0, "Choc court terme baissier utilisé dans l'EVE."),
    ]


def ensure_standard_assumptions() -> None:
    """Crée les hypothèses standards et une version active initiale si besoin."""
    global _STANDARD_ASSUMPTIONS_ENSURED
    if _STANDARD_ASSUMPTIONS_ENSURED:
        return
    now = timezone.now()
    for item in standard_assumptions():
        assumption, created = Assumption.objects.get_or_create(
            code=item.code,
            defaults={
                "label": item.label,
                "category": item.category,
                "description": item.description,
                "methodology": item.methodology,
                "sources": item.sources,
            },
        )
        changed = False
        for field_name, value in {
            "label": item.label,
            "category": item.category,
            "description": item.description,
            "methodology": item.methodology,
            "sources": item.sources,
        }.items():
            if created:
                break
            if not getattr(assumption, field_name):
                setattr(assumption, field_name, value)
                changed = True
        if changed:
            assumption.save(update_fields=["label", "category", "description", "methodology", "sources", "updated_at"])

        if not assumption.versions.exists():
            AssumptionVersion.objects.create(
                assumption=assumption,
                version_number=1,
                value=item.default,
                payload=item.payload,
                state=AssumptionVersion.STATE_ACTIVE,
                activated_at=now,
                rationale="Version initiale issue des paramètres standards de l'application.",
            )
    _STANDARD_ASSUMPTIONS_ENSURED = True


def get_assumption_value(code: str, default: float = 0.0) -> float:
    """Retourne la valeur active d'une hypothèse scalaire."""
    ensure_standard_assumptions()
    version = (
        AssumptionVersion.objects
        .filter(assumption__code=code, state=AssumptionVersion.STATE_ACTIVE)
        .order_by("-activated_at", "-version_number")
        .first()
    )
    if version and version.value is not None:
        return float(version.value)
    return float(default)
