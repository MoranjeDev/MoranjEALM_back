"""
Moteur de ventilation FCY / LCY du bilan et du hors-bilan.

Calcule pour une date d'arrêté donnée :
- Bilan par devise (actif LCY, actif FCY, passif LCY, passif FCY)
- Bilan consolidé (tout en LCY via taux de change FxRate)
- Hors-bilan par devise
- Position FX nette = actifs FCY - passifs FCY + hors-bilan FCY pondéré

Utilise :
- BalanceSheetLine (apps.balance_sheet)
- OffBalanceSheetItem (apps.off_balance)
- FxRate (apps.mapping) pour la conversion en LCY
"""
from __future__ import annotations

from django.db.models import Sum
from apps.balance_sheet.models import BalanceSheetLine
from apps.off_balance.models import OffBalanceSheetItem
from apps.mapping.models import FxRate, Currency


def _get_fx_rate(currency_code: str, date_arrete) -> float:
    """Retourne le taux de change vers la devise pivot (LCY).
    Cherche le taux le plus récent disponible <= date_arrete.
    Retourne 1.0 si la devise est la devise pivot ou si aucun taux n'est trouvé.
    """
    if not currency_code or currency_code == "XAF":
        return 1.0
    try:
        pivot = Currency.objects.filter(is_base=True).first()
        if pivot and currency_code == pivot.code:
            return 1.0
        rate = FxRate.objects.filter(
            currency__code=currency_code,
            date__lte=date_arrete
        ).order_by("-date").first()
        return rate.rate if rate else 1.0
    except Exception:
        return 1.0


def compute_balance_sheet_by_currency(date_arrete: str | None = None) -> dict:
    """
    Retourne le bilan ventilé par devise pour une date d'arrêté.

    Structure de retour :
    {
      "date_arrete": "2024-12-31",
      "devises": [
        {
          "devise": "XAF",
          "is_base": true,
          "fx_rate": 1.0,
          "actif_lcy": 150000000000,
          "passif_lcy": 130000000000,
          "actif_fcy": 0,
          "passif_fcy": 0,
          "gap_lcy": 20000000000,
        },
        {
          "devise": "EUR",
          "is_base": false,
          "fx_rate": 655.957,
          "actif_lcy": 3000000000,
          "passif_lcy": 2500000000,
          "actif_fcy": 4573000,
          "passif_fcy": 3810000,
          "gap_lcy": 500000000,
        }
      ],
      "consolidated": {
        "total_actif_lcy": ...,
        "total_passif_lcy": ...,
        "gap_lcy": ...,
      },
      "lcy_only": { "actif": ..., "passif": ..., "gap": ... },
      "fcy_total": { "actif_lcy_equivalent": ..., "passif_lcy_equivalent": ..., "gap_lcy": ... }
    }
    """
    from datetime import date as date_cls

    # Résoudre la date d'arrêté
    if date_arrete:
        arrete = date_cls.fromisoformat(date_arrete)
    else:
        last = BalanceSheetLine.objects.order_by("-date_arrete").values_list("date_arrete", flat=True).first()
        if last is None:
            return {"error": "Aucune ligne de bilan GL importée.", "devises": []}
        arrete = last

    # Agréger par devise et sens
    qs = (
        BalanceSheetLine.objects
        .filter(date_arrete=arrete, sens__in=["actif", "passif"])
        .values("devise", "sens")
        .annotate(
            total_lcy=Sum("montant_lcy"),
            total_fcy=Sum("montant_fcy"),
        )
    )

    # Organiser par devise
    by_devise: dict[str, dict] = {}
    for row in qs:
        dev = row["devise"] or "XAF"
        if dev not in by_devise:
            by_devise[dev] = {"actif_lcy": 0, "passif_lcy": 0, "actif_fcy": 0, "passif_fcy": 0}
        sens = row["sens"]
        by_devise[dev][f"{sens}_lcy"] += row["total_lcy"] or 0
        by_devise[dev][f"{sens}_fcy"] += row["total_fcy"] or 0

    # Base currencies
    base_currency = Currency.objects.filter(is_base=True).values_list("code", flat=True).first() or "XAF"

    devises_result = []
    total_actif_lcy = 0
    total_passif_lcy = 0

    for dev_code, vals in by_devise.items():
        fx = _get_fx_rate(dev_code, arrete)
        # Le bilan GL porte déjà le montant LCY officiel. On l'utilise donc
        # en priorité pour le consolidé, et on ne convertit le montant FCY que
        # si le LCY n'a pas été fourni.
        actif_lcy_equiv = vals["actif_lcy"] or int(vals["actif_fcy"] * fx)
        passif_lcy_equiv = vals["passif_lcy"] or int(vals["passif_fcy"] * fx)
        displayed_fx = fx
        if dev_code != base_currency and fx == 1.0:
            total_fcy_side = vals["actif_fcy"] + vals["passif_fcy"]
            total_lcy_side = vals["actif_lcy"] + vals["passif_lcy"]
            if total_fcy_side:
                displayed_fx = total_lcy_side / total_fcy_side
        total_actif_lcy += actif_lcy_equiv
        total_passif_lcy += passif_lcy_equiv
        devises_result.append({
            "devise": dev_code,
            "is_base": dev_code == base_currency,
            "fx_rate": displayed_fx,
            "actif_lcy": vals["actif_lcy"],
            "passif_lcy": vals["passif_lcy"],
            "actif_fcy": vals["actif_fcy"],
            "passif_fcy": vals["passif_fcy"],
            "actif_lcy_equivalent": actif_lcy_equiv,
            "passif_lcy_equivalent": passif_lcy_equiv,
            "gap_lcy": actif_lcy_equiv - passif_lcy_equiv,
        })

    # LCY only vs FCY total
    lcy_row = next((d for d in devises_result if d["is_base"]), None)
    fcy_rows = [d for d in devises_result if not d["is_base"]]

    return {
        "date_arrete": str(arrete),
        "devises": sorted(devises_result, key=lambda x: (not x["is_base"], x["devise"])),
        "consolidated": {
            "total_actif_lcy": total_actif_lcy,
            "total_passif_lcy": total_passif_lcy,
            "gap_lcy": total_actif_lcy - total_passif_lcy,
        },
        "lcy_only": {
            "actif": lcy_row["actif_lcy"] if lcy_row else 0,
            "passif": lcy_row["passif_lcy"] if lcy_row else 0,
            "gap": (lcy_row["actif_lcy"] - lcy_row["passif_lcy"]) if lcy_row else 0,
        },
        "fcy_total": {
            "actif_lcy_equivalent": sum(d["actif_lcy_equivalent"] for d in fcy_rows),
            "passif_lcy_equivalent": sum(d["passif_lcy_equivalent"] for d in fcy_rows),
            "gap_lcy": sum(d["gap_lcy"] for d in fcy_rows),
        }
    }


def compute_fx_position(date_arrete: str | None = None) -> dict:
    """
    Calcule la position FX nette par devise.

    Position nette devise = actifs FCY - passifs FCY + hors-bilan FCY (pondéré par prob_tirage)

    Identifie :
    - Position longue (actifs > passifs + hors-bilan)  → risque de dépréciation
    - Position courte (actifs < passifs + hors-bilan)  → risque d'appréciation
    - Swapped funds = montant de FCY swappé en LCY (total actif FCY - gap net)

    Retourne par devise :
    {
      "devise": "EUR",
      "actif_fcy": 4573000,
      "passif_fcy": 3810000,
      "hors_bilan_fcy_net": 500000,
      "position_nette_fcy": 263000,
      "position_lcy": 172520631,
      "sens": "longue",
      "swapped_funds_lcy": ...,
    }
    """
    from datetime import date as date_cls

    if date_arrete:
        arrete = date_cls.fromisoformat(date_arrete)
    else:
        last = BalanceSheetLine.objects.order_by("-date_arrete").values_list("date_arrete", flat=True).first()
        if last is None:
            return {"error": "Aucune ligne de bilan GL importée.", "positions": []}
        arrete = last

    base_currency = Currency.objects.filter(is_base=True).values_list("code", flat=True).first() or "XAF"

    # Bilan FCY par devise (exclure la devise pivot)
    bs_qs = (
        BalanceSheetLine.objects
        .filter(date_arrete=arrete, sens__in=["actif", "passif"])
        .exclude(devise=base_currency)
        .values("devise", "sens")
        .annotate(total_fcy=Sum("montant_fcy"))
    )

    by_devise: dict[str, dict] = {}
    for row in bs_qs:
        dev = row["devise"]
        if dev not in by_devise:
            by_devise[dev] = {"actif_fcy": 0, "passif_fcy": 0, "hors_bilan_fcy_net": 0}
        by_devise[dev][f"{row['sens']}_fcy"] += row["total_fcy"] or 0

    # Hors-bilan FCY par devise (pondéré par prob_tirage)
    # Les engagements sont des sorties potentielles (passif) sauf LFP (actif potentiel)
    obs_qs = (
        OffBalanceSheetItem.objects
        .filter(date_arrete=arrete)
        .exclude(devise=base_currency)
        .values("devise", "type_engagement", "notionnel", "prob_tirage_pct")
    )
    for row in obs_qs:
        dev = row["devise"]
        if dev not in by_devise:
            by_devise[dev] = {"actif_fcy": 0, "passif_fcy": 0, "hors_bilan_fcy_net": 0}
        net = int(row["notionnel"] * row["prob_tirage_pct"] / 100)
        # LFP = ligne de financement potentielle → renforce la position actif
        if row["type_engagement"] == "lfp":
            by_devise[dev]["hors_bilan_fcy_net"] += net
        else:
            by_devise[dev]["hors_bilan_fcy_net"] -= net

    positions = []
    for dev_code, vals in by_devise.items():
        fx = _get_fx_rate(dev_code, arrete)
        pos_nette = vals["actif_fcy"] - vals["passif_fcy"] + vals["hors_bilan_fcy_net"]
        pos_lcy = int(pos_nette * fx)
        # Swapped funds = actif FCY qui finance des passifs LCY
        swapped = max(0, vals["actif_fcy"] - max(0, pos_nette))
        positions.append({
            "devise": dev_code,
            "fx_rate": fx,
            "actif_fcy": vals["actif_fcy"],
            "passif_fcy": vals["passif_fcy"],
            "hors_bilan_fcy_net": vals["hors_bilan_fcy_net"],
            "position_nette_fcy": pos_nette,
            "position_nette_lcy": pos_lcy,
            "sens": "longue" if pos_nette > 0 else ("courte" if pos_nette < 0 else "nulle"),
            "swapped_funds_fcy": swapped,
            "swapped_funds_lcy": int(swapped * fx),
        })

    total_pos_lcy = sum(p["position_nette_lcy"] for p in positions)
    return {
        "date_arrete": str(arrete),
        "base_currency": base_currency,
        "positions": sorted(positions, key=lambda x: x["devise"]),
        "total_position_lcy": total_pos_lcy,
        "total_swapped_funds_lcy": sum(p["swapped_funds_lcy"] for p in positions),
    }
