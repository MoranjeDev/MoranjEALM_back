"""
Concentration enrichie — analyse par secteur, segment client et BU.

Complète le module concentration.py existant (top N + HHI global) avec :
1. Concentration par secteur économique (NACE ou classification locale)
2. Concentration par segment client (retail, SME, corporate, public, financial)
3. Concentration par Business Unit
4. Concentration incluant le hors-bilan (engagements + notionnels pondérés)
5. Alertes de concentration (HHI > 2500 ou top 3 > 50%)

Source de données : BalanceSheetLine (données GL) + OffBalanceSheetItem
(pour une concentration totale bilan + hors-bilan).
"""
from __future__ import annotations

from django.db.models import Sum
from apps.balance_sheet.models import BalanceSheetLine
from apps.off_balance.models import OffBalanceSheetItem


def _hhi(parts: list[float]) -> float:
    """Indice de Herfindahl-Hirschman : Σ (share_i × 100)^2."""
    total = sum(parts)
    if total == 0:
        return 0.0
    return sum((p / total * 100) ** 2 for p in parts)


def _hhi_status(hhi: float) -> str:
    if hhi < 1500:
        return "LOW"
    if hhi < 2500:
        return "MEDIUM"
    return "HIGH"


def _concentration_by_dimension(
    dimension: str,
    sens: str = "both",
    include_off_balance: bool = True,
    date_arrete: str | None = None,
    n_top: int = 10,
) -> dict:
    """
    Calcule la concentration selon une dimension (secteur, segment, business_unit).

    dimension : "secteur" | "segment" | "business_unit"
    sens : "actif" | "passif" | "both"
    """
    from datetime import date as date_cls

    # Date d'arrêté
    if date_arrete:
        arrete = date_cls.fromisoformat(date_arrete)
    else:
        arrete = (
            BalanceSheetLine.objects.order_by("-date_arrete")
            .values_list("date_arrete", flat=True)
            .first()
        )
        if arrete is None:
            return {"error": "Aucune donnée de bilan GL disponible.", "rows": []}

    # Filtres
    qs = BalanceSheetLine.objects.filter(date_arrete=arrete).exclude(**{dimension: ""})
    if sens != "both":
        qs = qs.filter(sens=sens)
    else:
        qs = qs.filter(sens__in=["actif", "passif"])

    # Agrégation par dimension
    rows_qs = qs.values(dimension).annotate(total=Sum("montant_lcy")).order_by("-total")
    rows = list(rows_qs)

    # Ajouter hors-bilan
    if include_off_balance:
        ob_qs = OffBalanceSheetItem.objects.filter(date_arrete=arrete).exclude(
            **{dimension: ""}
        )
        ob_by_dim: dict[str, int] = {}
        for item in ob_qs:
            key = getattr(item, dimension, "") or ""
            if not key:
                continue
            net = int(item.notionnel * item.prob_tirage_pct / 100)
            ob_by_dim[key] = ob_by_dim.get(key, 0) + net

        # Enrichir les rows avec hors-bilan
        existing_keys = {r[dimension] for r in rows}
        for key, ob_total in ob_by_dim.items():
            if key in existing_keys:
                for r in rows:
                    if r[dimension] == key:
                        r["off_balance"] = ob_total
                        r["total_with_ob"] = r["total"] + ob_total
                        break
            else:
                rows.append(
                    {
                        dimension: key,
                        "total": 0,
                        "off_balance": ob_total,
                        "total_with_ob": ob_total,
                    }
                )

    # Compléter les rows sans hors-bilan
    for r in rows:
        if "off_balance" not in r:
            r["off_balance"] = 0
            r["total_with_ob"] = r.get("total", 0)

    # Trier par total_with_ob décroissant
    rows.sort(key=lambda x: x.get("total_with_ob", 0), reverse=True)

    # Calculs HHI
    amounts = [r.get("total_with_ob", 0) for r in rows]
    total_global = sum(amounts)
    hhi = _hhi(amounts)

    # Top N
    top_n = rows[:n_top]
    top_n_total = sum(r.get("total_with_ob", 0) for r in top_n)
    top_n_share = round(top_n_total / total_global * 100, 2) if total_global > 0 else 0

    # Enrichir avec parts et rangs
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["share_pct"] = (
            round(r.get("total_with_ob", 0) / total_global * 100, 2)
            if total_global > 0
            else 0
        )

    # Alertes
    alerts = []
    top3_share = sum(r["share_pct"] for r in rows[:3])
    if hhi > 2500:
        alerts.append(
            {
                "type": "HHI_HIGH",
                "message": f"HHI={hhi:.0f} — concentration très élevée.",
                "severity": "HIGH",
            }
        )
    elif hhi > 1500:
        alerts.append(
            {
                "type": "HHI_MEDIUM",
                "message": f"HHI={hhi:.0f} — concentration modérée.",
                "severity": "MEDIUM",
            }
        )
    if top3_share > 50:
        top3_labels = [r[dimension] for r in rows[:3]]
        alerts.append(
            {
                "type": "TOP3_DOMINANT",
                "message": f"Top 3 ({', '.join(top3_labels)}) = {top3_share:.1f}% du total.",
                "severity": "HIGH" if top3_share > 70 else "MEDIUM",
            }
        )

    return {
        "dimension": dimension,
        "sens": sens,
        "date_arrete": str(arrete),
        "include_off_balance": include_off_balance,
        "total_global": total_global,
        "hhi": round(hhi, 1),
        "hhi_status": _hhi_status(hhi),
        "top3_share_pct": round(top3_share, 2),
        "top_n": top_n,
        "all_rows": rows,
        "alerts": alerts,
        "nb_categories": len(rows),
    }


def compute_concentration_enriched(
    date_arrete: str | None = None,
    n_top: int = 10,
    include_off_balance: bool = True,
) -> dict:
    """
    Calcule la concentration selon les 3 dimensions : secteur, segment, BU.
    Retourne un rapport consolidé.
    """
    return {
        "date_arrete": date_arrete,
        "by_secteur": _concentration_by_dimension(
            "secteur",
            sens="both",
            include_off_balance=include_off_balance,
            date_arrete=date_arrete,
            n_top=n_top,
        ),
        "by_segment": _concentration_by_dimension(
            "segment",
            sens="both",
            include_off_balance=include_off_balance,
            date_arrete=date_arrete,
            n_top=n_top,
        ),
        "by_business_unit": _concentration_by_dimension(
            "business_unit",
            sens="both",
            include_off_balance=include_off_balance,
            date_arrete=date_arrete,
            n_top=n_top,
        ),
    }
