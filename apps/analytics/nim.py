"""
NIM (Net Interest Margin) et ratios de profitabilité ALM.

NIM = WAR (Weighted Asset Rate) − COF (Cost of Funds)
    = Σ(montant_actif × taux_actif) / Σ(montant_actif)
    - Σ(montant_passif × taux_passif) / Σ(montant_passif)

Calculé sur le bilan moyen (BalanceSheetLine sur une période).

Ratios complémentaires :
- Spread de taux = WAR - COF
- NII approché = NIM × Total actif moyen
- Loan-to-Deposit Ratio (LDR) = Crédits / Dépôts
- NIM par devise (LCY vs FCY)
- NIM par BU
- Évolution NIM vs période précédente (si plusieurs arrêtés disponibles)
"""
from __future__ import annotations

from django.db.models import Sum, Avg, Count
from apps.balance_sheet.models import BalanceSheetLine


def _weighted_rate(qs) -> float:
    """Taux moyen pondéré par le montant LCY."""
    total_montant = 0
    total_pondere = 0.0
    for row in qs.values("montant_lcy", "taux_moyen"):
        m = row["montant_lcy"] or 0
        t = row["taux_moyen"] or 0
        total_montant += m
        total_pondere += m * t
    if total_montant == 0:
        return 0.0
    return total_pondere / total_montant


def compute_nim(date_from: str | None = None, date_to: str | None = None) -> dict:
    """
    Calcule le NIM et les ratios de profitabilité depuis les BalanceSheetLine.

    Si date_from/date_to non fournis, utilise la dernière date d'arrêté disponible.

    Retourne :
    {
      "period": {"from": ..., "to": ..., "nb_arretes": ...},
      "war": 8.5,            # Weighted Asset Rate (%)
      "cof": 4.2,            # Cost of Funds (%)
      "nim": 4.3,            # NIM = WAR - COF (%)
      "spread": 4.3,         # identique au NIM en méthode bilan
      "total_actif_moyen": ...,
      "total_passif_moyen": ...,
      "nii_approche": ...,   # NIM/100 × total_actif_moyen
      "ldr": ...,            # Loan-to-Deposit Ratio (%)
      "by_devise": [
        {"devise": "XAF", "war": ..., "cof": ..., "nim": ..., "actif": ..., "passif": ...},
        {"devise": "EUR", ...}
      ],
      "by_bu": [
        {"business_unit": "Retail", "war": ..., "cof": ..., "nim": ..., "actif": ..., "passif": ...}
      ],
    }
    """
    from datetime import date as date_cls

    # Résoudre la période
    dates_qs = BalanceSheetLine.objects.values_list("date_arrete", flat=True).distinct().order_by("date_arrete")
    all_dates = list(dates_qs)

    if not all_dates:
        return {"error": "Aucune ligne de bilan GL importée. Importez d'abord un bilan via /api/balance-sheet/import/."}

    if date_from and date_to:
        d_from = date_cls.fromisoformat(date_from)
        d_to = date_cls.fromisoformat(date_to)
    else:
        # Utiliser toutes les dates disponibles
        d_from = all_dates[0]
        d_to = all_dates[-1]

    qs_period = BalanceSheetLine.objects.filter(date_arrete__gte=d_from, date_arrete__lte=d_to)
    nb_arretes = qs_period.values("date_arrete").distinct().count()

    qs_actif = qs_period.filter(sens="actif")
    qs_passif = qs_period.filter(sens="passif")

    # WAR et COF globaux
    war = _weighted_rate(qs_actif)
    cof = _weighted_rate(qs_passif)
    nim = war - cof

    # Totaux moyens (somme / nb_arretes)
    total_actif = (qs_actif.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)
    total_passif = (qs_passif.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)

    # NII approché
    nii_approche = nim / 100 * total_actif

    # LDR approché : actifs de crédit / dépôts
    # On identifie crédits et dépôts par les préfixes de compte GL si disponibles
    # Sinon on utilise les ratios globaux actif/passif
    ldr = (total_actif / total_passif * 100) if total_passif > 0 else None

    # Par devise
    by_devise = []
    devises = qs_period.values_list("devise", flat=True).distinct()
    for devise in sorted(devises):
        qa = qs_actif.filter(devise=devise)
        qp = qs_passif.filter(devise=devise)
        a_total = (qa.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)
        p_total = (qp.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)
        war_d = _weighted_rate(qa)
        cof_d = _weighted_rate(qp)
        if a_total > 0 or p_total > 0:
            by_devise.append({
                "devise": devise,
                "war": round(war_d, 4),
                "cof": round(cof_d, 4),
                "nim": round(war_d - cof_d, 4),
                "actif_moyen": round(a_total),
                "passif_moyen": round(p_total),
            })

    # Par BU
    by_bu = []
    bus = qs_period.exclude(business_unit="").values_list("business_unit", flat=True).distinct()
    for bu in sorted(bus):
        qa = qs_actif.filter(business_unit=bu)
        qp = qs_passif.filter(business_unit=bu)
        a_total = (qa.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)
        p_total = (qp.aggregate(t=Sum("montant_lcy"))["t"] or 0) / max(nb_arretes, 1)
        war_b = _weighted_rate(qa)
        cof_b = _weighted_rate(qp)
        if a_total > 0 or p_total > 0:
            by_bu.append({
                "business_unit": bu,
                "war": round(war_b, 4),
                "cof": round(cof_b, 4),
                "nim": round(war_b - cof_b, 4),
                "actif_moyen": round(a_total),
                "passif_moyen": round(p_total),
            })

    return {
        "period": {
            "from": str(d_from),
            "to": str(d_to),
            "nb_arretes": nb_arretes,
        },
        "war": round(war, 4),
        "cof": round(cof, 4),
        "nim": round(nim, 4),
        "spread": round(nim, 4),
        "total_actif_moyen": round(total_actif),
        "total_passif_moyen": round(total_passif),
        "nii_approche": round(nii_approche),
        "ldr": round(ldr, 2) if ldr else None,
        "by_devise": by_devise,
        "by_bu": by_bu,
    }


def compute_profitability_ratios(date_from: str | None = None, date_to: str | None = None) -> dict:
    """
    Calcule les ratios de profitabilité complets pour le rapport ALCO.

    Retourne :
    {
      "nim": 4.3,
      "war": 8.5,
      "cof": 4.2,
      "spread": 4.3,
      "nii_approche": 12500000000,
      "ldr": 78.5,
      "ratios": {
        "nim_pct": 4.3,
        "war_pct": 8.5,
        "cof_pct": 4.2,
        "spread_pct": 4.3,
        "ldr_pct": 78.5,
        "leverage": ...,          # Total actif / Fonds propres (si disponible)
      },
      "interpretation": {
        "nim_status": "GOOD" | "WATCH" | "ALERT",  # GOOD > 3%, WATCH 2-3%, ALERT < 2%
        "ldr_status": "GOOD" | "WATCH" | "ALERT",  # GOOD 70-90%, WATCH 90-100%, ALERT > 100%
        "spread_status": ...,
      }
    }
    """
    nim_data = compute_nim(date_from, date_to)
    if "error" in nim_data:
        return nim_data

    nim = nim_data["nim"]
    war = nim_data["war"]
    cof = nim_data["cof"]
    ldr = nim_data["ldr"]
    total_actif = nim_data["total_actif_moyen"]
    total_passif = nim_data["total_passif_moyen"]
    leverage = round(total_actif / (total_actif - total_passif), 2) if (total_actif - total_passif) > 0 else None

    def nim_status(v):
        if v > 3.0: return "GOOD"
        if v > 2.0: return "WATCH"
        return "ALERT"

    def ldr_status(v):
        if v is None: return "N/A"
        if 70 <= v <= 90: return "GOOD"
        if 90 < v <= 100: return "WATCH"
        return "ALERT"

    def spread_status(v):
        if v > 2.5: return "GOOD"
        if v > 1.0: return "WATCH"
        return "ALERT"

    return {
        **nim_data,
        "ratios": {
            "nim_pct": nim,
            "war_pct": war,
            "cof_pct": cof,
            "spread_pct": nim,
            "ldr_pct": ldr,
            "leverage": leverage,
        },
        "interpretation": {
            "nim_status": nim_status(nim),
            "ldr_status": ldr_status(ldr),
            "spread_status": spread_status(nim),
        },
    }
