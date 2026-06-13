"""Behavioral rate helpers for NII, EVE and interest-rate gap calculations."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from apps.behavioral.models import BehavioralDistributionParam
from .behavioral_resolver import PRODUCT_MAP


RATE_BEHAVIOR_LABELS = {
    "credit",
    "depot_terme",
    "bon",
    "compte_371",
    "compte_372",
    "compte_373",
    "compte_vue_cor",
}


@dataclass(frozen=True)
class RateBehavior:
    product_kind: str
    product_type: str
    repricing_lag_months: int = 0
    pass_through_pct: float = 100.0
    source: str = "not_applicable"
    param_code: str = ""

    @property
    def pass_through_factor(self) -> float:
        return max(0.0, float(self.pass_through_pct or 0.0)) / 100.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_kind": self.product_kind,
            "product_type": self.product_type,
            "repricing_lag_months": self.repricing_lag_months,
            "pass_through_pct": self.pass_through_pct,
            "source": self.source,
            "param_code": self.param_code,
        }


def _dimension(obj: Any, *names: str) -> str:
    for name in names:
        value = getattr(obj, name, "")
        if value:
            return str(value)
    return ""


def neutral_rate_behavior(product_kind: str) -> RateBehavior:
    return RateBehavior(
        product_kind=product_kind,
        product_type=PRODUCT_MAP.get(product_kind, product_kind),
    )


def rate_behavior_for_input(product_kind: str, obj: Any | None = None) -> RateBehavior:
    """Return the approved behavioral repricing rule for a rate-sensitive row.

    Unknown products stay neutral. This avoids hidden model effects when no
    bank-approved behavioral assumption exists for the product.
    """
    if product_kind not in RATE_BEHAVIOR_LABELS:
        return neutral_rate_behavior(product_kind)

    product_type = PRODUCT_MAP.get(product_kind, product_kind)
    segment = _dimension(obj, "segment", "segment_client", "categorie_client") if obj else "all"
    business_unit = _dimension(obj, "business_unit", "bu", "agence") if obj else ""
    secteur = _dimension(obj, "secteur", "sector") if obj else ""
    devise = _dimension(obj, "devise", "currency") if obj else ""
    return _rate_behavior_for_dimensions(
        product_kind,
        product_type,
        segment or "all",
        business_unit,
        secteur,
        devise,
    )


@lru_cache(maxsize=512)
def _rate_behavior_for_dimensions(
    product_kind: str,
    product_type: str,
    segment: str,
    business_unit: str,
    secteur: str,
    devise: str,
) -> RateBehavior:
    param = BehavioralDistributionParam.resolve(
        product_type=product_type,
        segment=segment,
        business_unit=business_unit,
        secteur=secteur,
        devise=devise,
    )
    if not param:
        return neutral_rate_behavior(product_kind)

    return RateBehavior(
        product_kind=product_kind,
        product_type=product_type,
        repricing_lag_months=max(int(param.repricing_lag_months or 0), 0),
        pass_through_pct=float(param.pass_through_pct if param.pass_through_pct is not None else 100.0),
        source="behavioral_param",
        param_code=param.code,
    )


def shock_days_after_lag(days: int, behavior: RateBehavior) -> int:
    lag_days = max(int(behavior.repricing_lag_months or 0), 0) * 30
    return max(int(days or 0) - lag_days, 0)


def effective_shift_decimal(shift_decimal: float, years: float, behavior: RateBehavior) -> float:
    """Return a pass-through and lag-adjusted shock for economic value views."""
    if shift_decimal == 0:
        return 0.0
    lag_years = max(float(behavior.repricing_lag_months or 0), 0.0) / 12.0
    if years <= 0:
        lag_factor = 0.0
    elif years <= lag_years:
        lag_factor = 0.0
    else:
        lag_factor = (years - lag_years) / years
    return shift_decimal * behavior.pass_through_factor * lag_factor


def effective_shift_bp(shift_bp: float, years: float, behavior: RateBehavior) -> float:
    return effective_shift_decimal(shift_bp / 10000.0, years, behavior) * 10000.0


def summarize_rate_behaviors(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for position in positions:
        behavior = position.get("rate_behavior") or neutral_rate_behavior(position.get("label", ""))
        key = f"{position.get('side')}::{position.get('label')}::{behavior.param_code or behavior.source}"
        item = grouped.setdefault(key, {
            "label": position.get("label"),
            "side": position.get("side"),
            "product_type": behavior.product_type,
            "repricing_lag_months": behavior.repricing_lag_months,
            "pass_through_pct": behavior.pass_through_pct,
            "source": behavior.source,
            "param_code": behavior.param_code,
            "amount": 0.0,
        })
        item["amount"] += float(position.get("amount") or 0.0)
    return sorted(grouped.values(), key=lambda row: (row["side"], row["label"], row["source"]))
