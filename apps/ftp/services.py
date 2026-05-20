"""
Service FTP : décompose la marge entre composantes commerciale,
transformation, liquidité et options.

Méthode matched maturity :
    FTP_rate = taux_marché_pour_maturité (lu sur la courbe FTP)
    Marge_commerciale_actif = customer_rate - ftp_rate
    Marge_commerciale_passif = ftp_rate - customer_rate
    Marge_transformation = optionnel (à enrichir)
    Marge_liquidité = spread additionnel (configurable par maturité)
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd
from django.utils import timezone

from apps.engine.rate_gap import ASSETS_RATE_INPUTS, LIABILITIES_RATE_INPUTS
from .models import FtpCurve


def _days_to(date_obj, ref: datetime) -> int:
    if not date_obj:
        return 0
    return max(int((pd.Timestamp(date_obj) - pd.Timestamp(ref)).days), 0)


def compute_margin_breakdown(currency_code: str = "XAF") -> dict:
    """Décompose la marge sur l'ensemble du bilan."""
    ref = timezone.now()
    curve = FtpCurve.objects.filter(
        currency__code=currency_code, is_active=True
    ).order_by("-effective_from").first()

    if curve is None:
        return {
            "currency": currency_code,
            "warning": "Aucune courbe FTP active pour cette devise.",
            "lines": [],
        }

    lines = []
    total_commercial = 0.0
    total_volume = 0.0

    def _process(group, side: str):
        nonlocal total_commercial, total_volume
        for model_cls, label, amount_field, rate_field, date_field in group:
            for obj in model_cls.objects.all():
                amount = float(getattr(obj, amount_field) or 0)
                rate = float(getattr(obj, rate_field) or 0)
                days = _days_to(getattr(obj, date_field), ref)
                ftp = curve.rate_at(days)
                if ftp is None or amount == 0:
                    continue
                commercial = (rate - ftp) if side == "asset" else (ftp - rate)
                lines.append({
                    "side": side,
                    "label": label,
                    "id": obj.pk,
                    "amount": round(amount, 2),
                    "amount_m": round(amount / 1_000_000, 2),
                    "customer_rate": round(rate, 4),
                    "ftp_rate": round(ftp, 4),
                    "commercial_margin_pct": round(commercial, 4),
                    "annual_commercial_margin": round(amount * commercial / 100, 2),
                })
                total_commercial += amount * commercial / 100
                total_volume += amount

    _process(ASSETS_RATE_INPUTS, "asset")
    _process(LIABILITIES_RATE_INPUTS, "liability")

    return {
        "currency": currency_code,
        "curve": curve.code,
        "reference_date": ref.isoformat(),
        "total_volume": round(total_volume, 2),
        "total_commercial_margin": round(total_commercial, 2),
        "weighted_avg_commercial_pct": round(
            total_commercial / total_volume * 100, 4
        ) if total_volume else 0.0,
        "lines": lines,
    }
