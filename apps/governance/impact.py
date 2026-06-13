"""Lecture d'impact des versions d'hypothèses.

Cette couche reste volontairement explicative : elle ne remplace pas un
recalcul moteur complet, mais donne au checker une lecture claire de ce qui va
changer avant activation.
"""
from __future__ import annotations

from typing import Any

from .models import Assumption, AssumptionVersion


def _as_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta_pct(delta: float | None, base: float | None) -> float | None:
    if delta is None or base in (None, 0):
        return None
    return round((delta / abs(base)) * 100, 2)


def _infer_modules(assumption: Assumption) -> list[str]:
    if assumption.impacted_modules:
        return list(assumption.impacted_modules)

    code = assumption.code.lower()
    category = assumption.category.lower()
    modules: list[str] = []

    if "lcr" in code or "liquid" in code or category in {"nmd_stability", "withdrawal"}:
        modules.extend(["LCR", "Gap de liquidité"])
    if "nii" in code or "rate" in code or category in {"rate_shock", "ftp_curve"}:
        modules.append("NII Sensitivity")
    if "eve" in code or "duration" in code or category in {"rate_shock", "embedded_option"}:
        modules.append("EVE Sensitivity")
    if "stress" in code or category == "stress_scenario":
        modules.append("Stress tests")
    if category in {"prepayment", "rollover", "nmd_stability", "withdrawal"}:
        modules.append("Hypothèses comportementales")

    return list(dict.fromkeys(modules)) or ["Calculs ALM"]


def _module_reading(module: str, assumption: Assumption, delta: float | None) -> str:
    direction = "augmente" if (delta or 0) > 0 else "diminue" if (delta or 0) < 0 else "reste stable"
    module_l = module.lower()
    code_l = assumption.code.lower()

    if "lcr" in module_l:
        return (
            f"La pondération ou le comportement lié à {assumption.label} {direction}. "
            "Le ratio LCR sera recalculé avec cette valeur après activation."
        )
    if "gap" in module_l or "liquid" in module_l:
        return (
            f"La distribution de liquidité liée à {assumption.label} {direction}. "
            "Les buckets concernés seront actualisés au prochain recalcul moteur."
        )
    if "nii" in module_l:
        return (
            f"La sensibilité NII intégrera cette hypothèse {direction}. "
            "L'effet apparaîtra dans les scénarios de marge d'intérêt après activation."
        )
    if "eve" in module_l:
        return (
            f"L'EVE utilisera cette valeur dans la lecture de duration/sensibilité. "
            "Les impacts économiques seront visibles après activation."
        )
    if "stress" in module_l or "stress" in code_l:
        return (
            f"Le scénario de stress associé {direction}. "
            "Les sorties, haircuts ou retraits simulés seront recalculés après activation."
        )
    if "comport" in module_l:
        return (
            f"Le comportement client modélisé {direction}. "
            "Les postes non contractuels seront redistribués selon la version active."
        )
    return (
        f"La valeur utilisée par {module} {direction}. "
        "Cette lecture est une prévisualisation avant activation opérationnelle."
    )


def assumption_impact_preview(version: AssumptionVersion) -> dict[str, Any]:
    """Retourne une prévisualisation lisible de l'impact d'une version."""

    assumption = version.assumption
    active = assumption.active_version
    active_value = _as_float(active.value if active else None)
    proposed_value = _as_float(version.value)
    delta = None if active_value is None or proposed_value is None else round(proposed_value - active_value, 6)
    modules = _infer_modules(assumption)

    return {
        "status": "preview_only",
        "active_version_id": active.id if active else None,
        "active_value": active_value,
        "proposed_value": proposed_value,
        "delta": delta,
        "delta_pct": _delta_pct(delta, active_value),
        "can_activate": version.state == AssumptionVersion.STATE_APPROVED,
        "module_impacts": [
            {
                "module": module,
                "current_value": active_value,
                "proposed_value": proposed_value,
                "delta": delta,
                "delta_pct": _delta_pct(delta, active_value),
                "reading": _module_reading(module, assumption, delta),
            }
            for module in modules
        ],
    }
