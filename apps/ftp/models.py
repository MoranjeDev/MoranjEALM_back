"""
Funds Transfer Pricing — module de tarification interne.

Approche retenue : matched maturity FTP.
- Une courbe FTP par devise (et optionnellement par segment).
- Un point de courbe par maturité (jours).
- À chaque ligne d'input correspond un FTP rate calculé par interpolation.
- Décomposition de la marge : commerciale + transformation + liquidité + options.

La courbe peut être versionnée via une AssumptionVersion (gouvernance).
"""
from __future__ import annotations

import bisect

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.governance.models import AssumptionVersion
from apps.mapping.models import Currency


class FtpCurve(models.Model):
    """Courbe FTP : ensemble de points (maturité jours, taux)."""

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    segment = models.CharField(max_length=64, blank=True, default="all")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ftp_curves",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Courbe FTP"
        verbose_name_plural = "Courbes FTP"
        ordering = ["currency", "code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.currency.code})"

    def rate_at(self, days: int) -> float | None:
        """Interpole le taux pour une maturité en jours."""
        points = list(self.points.order_by("days").values_list("days", "rate"))
        if not points:
            return None
        days_arr = [p[0] for p in points]
        rates = [p[1] for p in points]
        if days <= days_arr[0]:
            return rates[0]
        if days >= days_arr[-1]:
            return rates[-1]
        idx = bisect.bisect_left(days_arr, days)
        d0, d1 = days_arr[idx - 1], days_arr[idx]
        r0, r1 = rates[idx - 1], rates[idx]
        weight = (days - d0) / (d1 - d0)
        return r0 + weight * (r1 - r0)


class FtpPoint(models.Model):
    """Point de la courbe FTP."""
    curve = models.ForeignKey(FtpCurve, on_delete=models.CASCADE, related_name="points")
    days = models.IntegerField()
    rate = models.FloatField(help_text="Taux annuel (%)")

    class Meta:
        unique_together = [("curve", "days")]
        ordering = ["curve", "days"]


class FtpAllocation(models.Model):
    """Décomposition de marge calculée pour une ligne (snapshot)."""

    label = models.CharField(max_length=255)
    line_of_business = models.CharField(max_length=64, blank=True, default="")
    notional = models.BigIntegerField()
    customer_rate = models.FloatField()
    ftp_rate = models.FloatField()
    commercial_margin = models.FloatField()
    transformation_margin = models.FloatField()
    liquidity_margin = models.FloatField()
    option_margin = models.FloatField(default=0.0)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at"]
