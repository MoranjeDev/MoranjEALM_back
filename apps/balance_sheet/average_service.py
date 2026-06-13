"""
Calcul du bilan moyen sur une période.

Utilise les lignes BalanceSheetLine importées à différentes dates d'arrêté
pour calculer les soldes moyens par compte GL et par devise.

Le bilan moyen est utilisé pour :
- Calculer le NIM (Net Interest Margin)
- Calculer le ROA (Return on Assets)
- Comparer les périodes
"""
from __future__ import annotations
from django.db.models import Sum
from .models import BalanceSheetLine


def compute_average_balance_sheet(date_from: str, date_to: str) -> dict:
    """
    Calcule le bilan moyen entre deux dates d'arrêté.

    Retourne :
    - Par sens (actif/passif) : montant LCY moyen, FCY moyen, nombre d'arrêtés
    - Par devise : solde moyen
    - Par BU : solde moyen actif et passif
    - Total actif moyen, total passif moyen
    """
    from datetime import date
    d_from = date.fromisoformat(date_from)
    d_to = date.fromisoformat(date_to)

    qs = BalanceSheetLine.objects.filter(date_arrete__gte=d_from, date_arrete__lte=d_to)

    if not qs.exists():
        return {"error": f"Aucune donnée entre {date_from} et {date_to}.", "result": {}}

    # Nombre de dates d'arrêté distinctes dans la période
    nb_arretes = qs.values("date_arrete").distinct().count()

    # Moyennes globales par sens
    by_sens = {}
    for sens in ["actif", "passif"]:
        agg = qs.filter(sens=sens).aggregate(
            total_lcy=Sum("montant_lcy"),
            total_fcy=Sum("montant_fcy"),
        )
        total_lcy = agg["total_lcy"] or 0
        total_fcy = agg["total_fcy"] or 0
        by_sens[sens] = {
            "total_lcy_cumul": total_lcy,
            "moyenne_lcy": round(total_lcy / nb_arretes) if nb_arretes else 0,
            "moyenne_fcy": round(total_fcy / nb_arretes) if nb_arretes else 0,
        }

    # Moyennes par devise
    by_devise = {}
    for row in qs.values("devise", "sens").annotate(total=Sum("montant_lcy")):
        key = f"{row['devise']}_{row['sens']}"
        by_devise[key] = {
            "devise": row["devise"],
            "sens": row["sens"],
            "moyenne_lcy": round(row["total"] / nb_arretes) if nb_arretes else 0,
        }

    # Moyennes par BU
    by_bu = {}
    for row in qs.exclude(business_unit="").values("business_unit", "sens").annotate(total=Sum("montant_lcy")):
        key = f"{row['business_unit']}_{row['sens']}"
        by_bu[key] = {
            "business_unit": row["business_unit"],
            "sens": row["sens"],
            "moyenne_lcy": round(row["total"] / nb_arretes) if nb_arretes else 0,
        }

    return {
        "date_from": date_from,
        "date_to": date_to,
        "nb_arretes": nb_arretes,
        "by_sens": by_sens,
        "by_devise": list(by_devise.values()),
        "by_bu": list(by_bu.values()),
    }
