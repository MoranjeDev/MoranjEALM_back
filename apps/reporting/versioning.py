"""Snapshot de version modèle/hypothèses pour les exports de rapports."""
from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.governance.models import AssumptionVersion, ScenarioLibrary
from apps.governance.services import ensure_standard_assumptions, ensure_standard_scenarios


def _username(user) -> str:
    if not user:
        return ""
    return user.get_full_name() or user.get_username()


def _safe_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def report_version_snapshot(report_type: str = "", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retourne une empreinte lisible de la configuration utilisée par un rapport.

    Le but est de garder les exports auditables : version applicative, scénario
    demandé, hypothèses actives et bibliothèque de scénarios disponibles.
    """
    params = params or {}
    try:
        ensure_standard_assumptions()
        ensure_standard_scenarios()
    except Exception:
        # Un export ne doit pas échouer uniquement parce que l'initialisation des
        # hypothèses de référence rencontre une contrainte de données.
        pass

    active_versions = list(
        AssumptionVersion.objects.select_related("assumption", "approver")
        .filter(state=AssumptionVersion.STATE_ACTIVE)
        .order_by("assumption__category", "assumption__code")
    )
    active_scenarios = list(
        ScenarioLibrary.objects.filter(is_active=True).order_by("scope", "code")
    )
    assumption_rows = [
        {
            "code": version.assumption.code,
            "label": version.assumption.label,
            "category": version.assumption.get_category_display(),
            "version": version.version_number,
            "value": _safe_value(version.value),
            "approver": _username(version.approver),
            "activated_at": timezone.localtime(version.activated_at).strftime("%d/%m/%Y %H:%M")
            if version.activated_at
            else "-",
        }
        for version in active_versions
    ]
    digest_source = "|".join(
        f"{row['code']}:v{row['version']}:{row['value']}:{row['activated_at']}"
        for row in assumption_rows
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12] if digest_source else "aucune"

    return {
        "app_version": getattr(settings, "APP_VERSION", "1.0.0"),
        "report_type": report_type,
        "requested_scenario": params.get("scenario") or params.get("balance_sheet_mode") or "standard",
        "assumptions_count": len(assumption_rows),
        "assumptions_digest": digest,
        "assumptions": assumption_rows,
        "scenarios_count": len(active_scenarios),
        "scenarios": [
            {
                "code": scenario.code,
                "label": scenario.label,
                "scope": scenario.get_scope_display(),
                "approved": bool(scenario.approved_by_id),
            }
            for scenario in active_scenarios
        ],
    }
