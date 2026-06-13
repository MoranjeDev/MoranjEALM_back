"""Generic PDF exports for analytical reports.

The ALCO report keeps its dedicated, editorial PDF. This module provides a
consistent PDF shell for the other analytical screens so every report can be
downloaded and traced.
"""
from __future__ import annotations

import base64
import html
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from weasyprint import HTML

from apps.analytics.concentration import compute_concentration
from apps.analytics.eve import compute_eve_sensitivity
from apps.analytics.eve_enriched import compute_eve_enriched
from apps.analytics.nii import compute_nii_sensitivity
from apps.engine.lcr import compute_lcr_all
from apps.engine.rate_gap import compute_rate_gap
from apps.engine.scenario_analysis import compute_scenario_analysis
from apps.engine.synthesis import build_charts_payload, compute_synthesis
from apps.multicurrency.services import compute_positions_by_currency
from apps.parameters.models import Parameter

from .models import ReportAnnotation
from .versioning import report_version_snapshot


REPORTS: dict[str, dict[str, str]] = {
    "synthesis": {"title": "Synthese ALM", "permission": "Résultats"},
    "lcr": {"title": "Liquidity Coverage Ratio", "permission": "Ratio de liquidité"},
    "rate_gap": {"title": "Gap de taux", "permission": "Gap de taux"},
    "charts": {"title": "Graphes ALM", "permission": "Graphes"},
    "nii": {"title": "NII Sensitivity", "permission": "NII Sensitivity"},
    "eve": {"title": "EVE Sensitivity", "permission": "EVE Sensitivity"},
    "scenario_analysis": {"title": "Scenario Analysis", "permission": "Résultats"},
    "concentration": {"title": "Concentration", "permission": "Concentration"},
    "multicurrency": {"title": "Multi-devises", "permission": "Multi-devises"},
}

REPORT_ANNOTATION_SCOPES: dict[str, tuple[str, str]] = {
    "synthesis": ("synthesis", "scenario"),
    "lcr": ("lcr", ""),
    "rate_gap": ("rate_gap", ""),
    "nii": ("nii", ""),
    "eve": ("eve", ""),
    "scenario_analysis": ("scenario_analysis", ""),
    "concentration": ("concentration", ""),
    "multicurrency": ("multicurrency", ""),
}

SYNTHESIS_ROW_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Actifs contractuels",
        "asset",
        ("credit", "bta", "ota", "emprunt_obl", "pret_ter_cor", "pret_cor", "pret_titre", "inter_blanc"),
    ),
    ("Actifs comportementaux", "asset", ("decouvert", "beac", "billet")),
    (
        "Depenses contractuelles",
        "liability",
        ("pension_livree", "emprunt_inter_banc", "depot_terme", "emprunt_instit_etran", "bon", "avance_beac", "emprunt_titre"),
    ),
    ("Depenses comportementales", "liability", ("compte_371", "compte_372", "compte_373", "compte_vue_cor")),
)

SYNTHESIS_TYPE_LABELS: dict[str, str] = {
    "credit": "Credits",
    "bta": "BTA",
    "ota": "OTA",
    "emprunt_obl": "Emprunts obligataires",
    "pret_ter_cor": "Prets a terme des correspondants",
    "pret_cor": "Prets aux correspondants",
    "pret_titre": "Prets de titres",
    "inter_blanc": "Prets interbancaires a blanc",
    "decouvert": "Decouverts",
    "beac": "BEAC",
    "billet": "Billets",
    "pension_livree": "Pensions livrees",
    "emprunt_inter_banc": "Emprunts interbancaires",
    "depot_terme": "Depots a terme",
    "emprunt_instit_etran": "Emprunts institutions etrangeres",
    "bon": "Bons de caisse",
    "avance_beac": "Avances BEAC",
    "emprunt_titre": "Emprunts de titres",
    "compte_371": "Comptes 371",
    "compte_372": "Comptes 372",
    "compte_373": "Comptes 373",
    "compte_vue_cor": "Comptes vue correspondants",
}

SCENARIO_LABELS: dict[str, str] = {
    "base": "Cas de base",
    "modere": "Stress modere",
    "severe": "Stress severe",
}

CHART_SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("base", "Profil de GAP : CAS DE BASE", "Cas de base : Profil temporel Actif et Passif"),
    ("modere", "Profil de GAP : CAS MODERE", "Cas modere : Profil temporel Actif et Passif"),
    ("severe", "Profil de GAP : CAS SEVERE", "Cas severe : Profil temporel Actif et Passif"),
)

LCR_SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("current", "Situation actuelle", "base"),
    ("base", "Scenario de base", "base"),
    ("modere", "Scenario modere", "modere"),
    ("severe", "Scenario severe", "severe"),
)

LCR_ROWS: tuple[tuple[str, bool, bool, bool], ...] = (
    ("level_1", True, False, False),
    ("cash", False, False, False),
    ("central_bank", False, False, False),
    ("sovereign", False, False, False),
    ("level_2", True, False, False),
    ("state_bonds", False, False, False),
    ("central_multilateral_bonds", False, False, False),
    ("opcvm", False, False, False),
    ("equities", False, False, False),
    ("hqla", True, False, False),
    ("inflows", True, False, False),
    ("financial_inflows", False, False, False),
    ("sight_financial_claims", False, False, False),
    ("retail_inflows", False, False, False),
    ("outflows", True, False, False),
    ("retail_deposits", False, False, False),
    ("corporate_deposits", False, False, False),
    ("financial_outflows", False, False, False),
    ("other_due", False, False, False),
    ("guarantees", False, False, False),
    ("net_outflows", True, True, False),
    ("lcr", True, True, True),
)

RATE_DEBITOR_ROWS: tuple[tuple[str, str], ...] = (
    ("credit", "Credits CT MT LT"),
    ("bta", "BTA"),
    ("ota", "OTA"),
    ("emprunt_obl", "Emprunts obligataires"),
    ("pret_ter_cor", "Prets a terme des correspondants"),
    ("inter_blanc", "Prets interbancaires a blanc"),
    ("pret_cor", "Prets aux correspondants"),
    ("pret_titre", "Prets des titres"),
    ("decouvert", "Decouverts"),
)

RATE_CREDITOR_ROWS: tuple[tuple[str, str], ...] = (
    ("pension_livree", "Pensions livrees"),
    ("emprunt_inter_banc", "Emprunts interbancaires a terme"),
    ("depot_terme", "Depot a terme"),
    ("bon", "Bons de caisse"),
    ("avance_beac", "Avance BEAC"),
    ("emprunt_titre", "Emprunts des titres"),
)

PRODUCT_LABELS: dict[str, str] = {
    "credit": "Credits CT / MT / LT",
    "decouvert": "Decouverts",
    "emprunt_obl": "Emprunts obligataires",
    "ota": "OTA",
    "bta": "BTA",
    "pret_cor": "Prets aux correspondants",
    "pret_ter_cor": "Prets a terme des correspondants",
    "pret_titre": "Prets de titres",
    "inter_blanc": "Prets interbancaires a blanc",
    "bon": "Bons de caisse",
    "depot_terme": "Depots a terme",
    "emprunt_inter_banc": "Emprunts interbancaires a terme",
    "pension_livree": "Pensions livrees",
    "avance_beac": "Avances BEAC",
    "emprunt_titre": "Emprunts de titres",
    "emprunt_instit_etran": "Emprunts institutions etrangeres",
}


def _logo_watermark_data_uri() -> str:
    """Embed the MoranjEALM mark so PDF generation does not depend on static URLs."""
    root_dir = Path(__file__).resolve().parents[3]
    candidates = (
        root_dir / "frontend" / "public" / "moranjealm-mark.png",
        root_dir / "frontend" / "src" / "assets" / "moranjealm-mark.png",
        root_dir / "logo_MoranjEALM_trans.png",
        root_dir / "logo_MoranjEALM.png",
    )
    for path in candidates:
        if path.exists():
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    return ""


def _file_data_uri(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _bank_branding() -> tuple[str, str]:
    try:
        param = Parameter.get_solo()
    except Exception:
        return "", ""

    bank_name = (param.bankName or "").strip()
    bank_logo = ""
    if param.bankLogo:
        try:
            bank_logo = _file_data_uri(param.bankLogo.path)
        except Exception:
            bank_logo = ""
    return bank_name, bank_logo


def _client_brand_html(bank_name: str, bank_logo: str) -> str:
    if not bank_name and not bank_logo:
        return ""
    logo = f'<img src="{bank_logo}" alt="" />' if bank_logo else ""
    name = f'<span>{html.escape(bank_name)}</span>' if bank_name else ""
    return f'<div class="client-brand">{logo}{name}</div>'


def _public_user_label(user_label: str) -> str:
    """Nettoie le libellé utilisateur affiché dans les PDF client."""
    cleaned = (user_label or "").replace("MoranjEALM", "").strip(" -—")
    return cleaned or "Utilisateur"


def get_report_payload(report_type: str, params: dict[str, Any]) -> tuple[str, Any]:
    scenario = params.get("scenario", "base")
    if scenario not in ("base", "modere", "severe"):
        scenario = "base"

    if report_type == "synthesis":
        return f"{REPORTS[report_type]['title']} - {scenario}", compute_synthesis(scenario)
    if report_type == "lcr":
        return f"{REPORTS[report_type]['title']} - {scenario}", compute_lcr_all()[scenario]
    if report_type == "rate_gap":
        return REPORTS[report_type]["title"], compute_rate_gap()
    if report_type == "charts":
        return REPORTS[report_type]["title"], build_charts_payload()
    if report_type == "nii":
        horizon = int(params.get("horizon_days", 365))
        return f"{REPORTS[report_type]['title']} - {horizon} jours", compute_nii_sensitivity(horizon_days=horizon)
    if report_type == "eve":
        payload = compute_eve_sensitivity()
        try:
            payload["enriched"] = compute_eve_enriched()
        except Exception as exc:  # noqa: BLE001
            payload["enriched_error"] = str(exc)
        return REPORTS[report_type]["title"], payload
    if report_type == "scenario_analysis":
        mode = str(params.get("balance_sheet_mode") or "static").lower()
        if mode not in ("static", "dynamic"):
            mode = "static"
        return f"{REPORTS[report_type]['title']} - {mode}", compute_scenario_analysis(mode)
    if report_type == "concentration":
        n = int(params.get("n", 20))
        return f"{REPORTS[report_type]['title']} - top {n}", compute_concentration(n=n)
    if report_type == "multicurrency":
        return REPORTS[report_type]["title"], compute_positions_by_currency()

    raise ValueError(f"Type de rapport inconnu : {report_type}")


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return html.escape(str(value))


def _fmt_money(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if abs(number) < 0.005:
        return "-"
    return f"{number:,.{digits}f}".replace(",", " ").replace(".", ",")


def _fmt_mfcfa(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if abs(number) < 0.5:
        return "-"
    return f"{number / 1_000_000:,.{digits}f}".replace(",", " ").replace(".", ",")


def _fmt_pdf_value(value: Any, percent: bool = False, digits: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if abs(number) < 0.005:
        return "-"
    formatted = f"{number:,.{0 if percent else digits}f}".replace(",", " ").replace(".", ",")
    return f"{formatted}%" if percent else formatted


def _fmt_short(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M".replace(",", " ").replace(".", ",")
    if abs_value >= 1_000:
        return f"{value / 1_000:,.1f}k".replace(",", " ").replace(".", ",")
    return _fmt_money(value, 0)


def _sum(values: list[float]) -> float:
    return round(sum(float(v or 0) for v in values), 2)


def _svg_num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _chart_bounds(series: list[list[float]]) -> tuple[float, float]:
    values = [float(v or 0) for row in series for v in row]
    if not values:
        return -1.0, 1.0
    minimum = min(values + [0.0])
    maximum = max(values + [0.0])
    if minimum == maximum:
        pad = abs(maximum) * 0.2 or 1.0
        return minimum - pad, maximum + pad
    pad = (maximum - minimum) * 0.12
    return minimum - pad, maximum + pad


def _chart_y(value: float, minimum: float, maximum: float, top: float, plot_h: float) -> float:
    return top + ((maximum - value) / (maximum - minimum)) * plot_h


def _chart_ticks(minimum: float, maximum: float) -> list[float]:
    step = (maximum - minimum) / 4
    return [minimum + step * i for i in range(5)]


def _svg_label(value: float) -> str:
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1_000_000:
        return f"{sign}{abs_value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{sign}{abs_value / 1_000:.1f}k"
    return f"{value:.0f}"


def _fmt_rate(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    if abs(number) < 0.005:
        return "-"
    return f"{number:,.2f}".replace(",", " ").replace(".", ",") + " %"


def _fmt_point(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    if abs(number) < 0.005:
        return "-"
    return f"{number:,.2f}".replace(",", " ").replace(".", ",") + " pts"


def _fmt_rate_value(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    if abs(number) < 0.005:
        return "-"
    return f"{number:,.2f}".replace(",", " ").replace(".", ",") + "%"


def _product_label(label: Any) -> str:
    raw = str(label or "-")
    return PRODUCT_LABELS.get(raw, raw.replace("_", " ").capitalize())


def _hhi_class(level: str) -> str:
    normalized = level.lower()
    if "tres" in normalized or "très" in normalized:
        return "ko"
    if "moder" in normalized or "modér" in normalized:
        return "warn"
    return "ok"


def _rate_gap_interpretation(gap: float) -> tuple[str, str]:
    if gap < 0:
        return "Situation contraignante", "Taux crediteur superieur au taux debiteur."
    if gap < 2.5:
        return "Gap moyen faible", "Marge de taux limitee, vigilance recommandee."
    return "Situation confortable", "Ecart moyen positif entre taux debiteurs et crediteurs."


def _render_rate_gap_svg(data: dict[str, Any]) -> str:
    buckets = [str(v) for v in data.get("buckets", [])]
    gap = [float(v or 0) for v in data.get("gap", [])]
    assets = [float(v or 0) for v in data.get("total_assets", [])]
    liabilities = [float(v or 0) for v in data.get("total_liabilities", [])]
    width, height = 1040, 300
    left, right, top, bottom = 70, 28, 24, 72
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = gap + assets + liabilities + [0.0]
    minimum, maximum = _chart_bounds([values])
    count = max(len(buckets), 1)
    slot = plot_w / count
    bar_w = min(34, slot * 0.56)

    def y_pos(value: float) -> float:
        return _chart_y(value, minimum, maximum, top, plot_h)

    zero_y = y_pos(0)
    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = y_pos(tick)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 10}" y="{_svg_num(y + 4)}" text-anchor="end" class="axis-label">{html.escape(f"{tick:.1f}")}</text>'
        )

    bars = []
    for index, value in enumerate(gap):
        x = left + slot * index + (slot - bar_w) / 2
        y = y_pos(value)
        rect_y = min(y, zero_y)
        rect_h = max(abs(zero_y - y), 1)
        color = "#B42318" if value < 0 else "#002E5F"
        bars.append(
            f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.78"/>'
        )

    def line_for(series: list[float], color: str) -> str:
        points = []
        dots = []
        for index, value in enumerate(series):
            x = left + slot * index + slot / 2
            y = y_pos(value)
            points.append(f"{_svg_num(x)},{_svg_num(y)}")
            dots.append(f'<circle cx="{_svg_num(x)}" cy="{_svg_num(y)}" r="3" fill="{color}" stroke="#FFFFFF" stroke-width="1.1"/>')
        return (
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
            + "".join(dots)
        )

    labels = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 24}" text-anchor="end" transform="rotate(-22 {_svg_num(left + slot * i + slot / 2)} {height - 24})" class="bucket-label">{html.escape(bucket)}</text>'
        for i, bucket in enumerate(buckets)
    )

    return f"""
    <svg class="rate-chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      {line_for(assets, "#FF4B18")}
      {line_for(liabilities, "#735247")}
      <g>{labels}</g>
    </svg>
    """


def _nii_scenario_short_label(item: dict[str, Any]) -> str:
    code = str(item.get("scenario") or "")
    mapping = {
        "base": "Base",
        "parallel_up_100": "+100 bp",
        "parallel_down_100": "-100 bp",
        "parallel_up_200": "+200 bp",
        "parallel_down_200": "-200 bp",
        "short_up": "CT +100",
        "short_down": "CT -100",
        "steepener": "Steepener",
        "flattener": "Flattener",
    }
    if code in mapping:
        return mapping[code]
    label = str(item.get("label") or code or "-")
    return label.replace("Parallele ", "").replace("Court-terme ", "CT ")


def _eve_scenario_short_label(item: dict[str, Any]) -> str:
    code = str(item.get("scenario") or "")
    mapping = {
        "base": "Base",
        "parallel_up_200": "+200 bp",
        "parallel_down_200": "-200 bp",
        "steepener": "Steepener",
        "flattener": "Flattener",
        "short_up": "CT +100",
        "short_down": "CT -100",
    }
    if code in mapping:
        return mapping[code]
    label = str(item.get("label") or code or "-")
    return label.replace("Parallele ", "").replace("Court-terme ", "CT ")


def _render_nii_delta_svg(data: dict[str, Any]) -> str:
    scenarios = list(data.get("scenarios", []))
    labels = [_nii_scenario_short_label(item) for item in scenarios]
    deltas = [float(item.get("delta_nii") or 0) for item in scenarios]
    width, height = 1040, 245
    left, right, top, bottom = 76, 28, 28, 48
    plot_w = width - left - right
    plot_h = height - top - bottom
    minimum, maximum = _chart_bounds([deltas, [0.0]])
    count = max(len(labels), 1)
    slot = plot_w / count
    bar_w = min(36, slot * 0.44)

    def y_pos(value: float) -> float:
        return _chart_y(value, minimum, maximum, top, plot_h)

    zero_y = y_pos(0)
    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = y_pos(tick)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 10}" y="{_svg_num(y + 4)}" text-anchor="end" class="axis-label">{html.escape(_svg_label(tick))}</text>'
        )

    bars = []
    value_labels = []
    for index, value in enumerate(deltas):
        x = left + slot * index + (slot - bar_w) / 2
        y = y_pos(value)
        rect_y = min(y, zero_y)
        rect_h = max(abs(zero_y - y), 1)
        color = "#B42318" if value < 0 else "#166534"
        bars.append(
            f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.82"/>'
        )
        if abs(value) >= 0.005:
            label_y = rect_y - 5 if value >= 0 else rect_y + rect_h + 11
            value_labels.append(
                f'<text x="{_svg_num(x + bar_w / 2)}" y="{_svg_num(label_y)}" text-anchor="middle" class="nii-value-label">{html.escape(_fmt_short(value))}</text>'
            )

    labels_svg = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 17}" text-anchor="middle" class="bucket-label">{html.escape(label)}</text>'
        for i, label in enumerate(labels)
    )

    return f"""
    <svg class="nii-chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      <g>{''.join(value_labels)}</g>
      <g>{labels_svg}</g>
    </svg>
    """


def _render_eve_delta_svg(data: dict[str, Any]) -> str:
    scenarios = list(data.get("scenarios", []))
    labels = [_eve_scenario_short_label(item) for item in scenarios]
    deltas = [float(item.get("delta_eve") or 0) for item in scenarios]
    width, height = 1040, 320
    left, right, top, bottom = 86, 34, 48, 66
    plot_w = width - left - right
    plot_h = height - top - bottom
    minimum, maximum = _chart_bounds([deltas, [0.0]])
    count = max(len(labels), 1)
    slot = plot_w / count
    bar_w = min(46, slot * 0.42)

    def y_pos(value: float) -> float:
        return _chart_y(value, minimum, maximum, top, plot_h)

    zero_y = y_pos(0)
    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = y_pos(tick)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 10}" y="{_svg_num(y + 4)}" text-anchor="end" class="axis-label">{html.escape(_svg_label(tick))}</text>'
        )

    bars = []
    value_labels = []
    for index, value in enumerate(deltas):
        x = left + slot * index + (slot - bar_w) / 2
        y = y_pos(value)
        rect_y = min(y, zero_y)
        rect_h = max(abs(zero_y - y), 1)
        color = "#B42318" if value < 0 else "#166534"
        bars.append(
            f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.82"/>'
        )
        if abs(value) >= 0.005:
            label_y = rect_y - 8 if value >= 0 else rect_y + rect_h + 16
            value_labels.append(
                f'<text x="{_svg_num(x + bar_w / 2)}" y="{_svg_num(label_y)}" text-anchor="middle" class="nii-value-label">{html.escape(_fmt_short(value))}</text>'
            )

    labels_svg = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 25}" text-anchor="middle" class="bucket-label eve-bucket-label">{html.escape(label)}</text>'
        for i, label in enumerate(labels)
    )

    return f"""
    <svg class="nii-chart-svg eve-chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      <g>{''.join(value_labels)}</g>
      <g>{labels_svg}</g>
    </svg>
    """


def _render_eve_enriched_pdf(enriched: dict[str, Any] | None, error: str | None = None) -> str:
    if error:
        return f"""
        <section class="nii-table-stack">
          <div class="nii-table-block">
            <div class="section-title"><h2>EVE enrichi — IRRBB</h2><span>Lecture par bucket non disponible</span></div>
            <p>{html.escape(error)}</p>
          </div>
        </section>
        """
    if not enriched:
        return ""

    scenarios = [
        (code, item.get("label") or code)
        for code, item in (enriched.get("scenarios") or {}).items()
        if code != "base"
    ]
    scenario_headers = "".join(f"<th>{html.escape(str(label))}</th>" for _code, label in scenarios)
    col_count = len(scenarios) + 3

    matrix_rows = []
    for row in enriched.get("bucket_summary") or []:
        max_delta = float(row.get("max_delta_eve") or 0)
        cells = [
            f'<td class="label">{html.escape(str(row.get("label") or "-"))}</td>',
            f'<td class="num strong {"neg" if max_delta < 0 else "pos"}>{html.escape(_fmt_mfcfa(max_delta))}</td>',
        ]
        deltas = row.get("delta_eve_by_scenario") or {}
        for code, _label in scenarios:
            value = float(deltas.get(code) or 0)
            cells.append(f'<td class="num {"neg" if value < 0 else "pos"}>{html.escape(_fmt_mfcfa(value))}</td>')
        status = "Breach" if row.get("breach") else "OK"
        cells.append(f'<td class="num strong {"neg" if row.get("breach") else "pos"}>{html.escape(status)}</td>')
        matrix_rows.append(f"<tr>{''.join(cells)}</tr>")

    breach_rows = []
    for row in enriched.get("breaches") or []:
        breach_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(row.get("label") or "-"))}</td>'
            f'<td>{html.escape(str(row.get("scenario_label") or row.get("scenario") or "-"))}</td>'
            f'<td class="num strong neg">{html.escape(_fmt_mfcfa(row.get("delta_eve")))}</td>'
            f'<td class="num strong neg">{html.escape(_fmt_rate_value(row.get("pct_tier1")))}</td>'
            f'<td>{html.escape(str(row.get("severity") or "-"))}</td>'
            "</tr>"
        )

    breaches_html = (
        f"""
        <table class="nii-table compact">
          <thead><tr><th class="label-col">Bucket</th><th>Scenario</th><th>Delta EVE</th><th>% Tier 1</th><th>Severite</th></tr></thead>
          <tbody>{''.join(breach_rows)}</tbody>
        </table>
        """
        if breach_rows
        else '<p class="pos"><b>Aucun bucket ne dépasse le seuil IRRBB paramétré.</b></p>'
    )

    return f"""
    <section class="nii-table-stack">
      <div class="nii-table-block">
        <div class="section-title">
          <h2>Matrice EVE Bucket × Scenario</h2>
          <span>Hors-bilan {'inclus' if enriched.get('off_balance_included') else 'exclu'} — seuil {html.escape(_fmt_rate_value(enriched.get('breach_threshold_pct')))} Tier 1</span>
        </div>
        <table class="nii-table compact">
          <thead><tr><th class="label-col">Bucket</th><th>Pire Delta EVE</th>{scenario_headers}<th>Statut</th></tr></thead>
          <tbody>{''.join(matrix_rows) if matrix_rows else f'<tr><td colspan="{col_count}">Aucune donnée EVE enrichie.</td></tr>'}</tbody>
        </table>
      </div>
      <div class="nii-table-block">
        <div class="section-title"><h2>Breaches IRRBB</h2><span>{int(enriched.get('nb_breaches') or 0)} dépassement(s)</span></div>
        {breaches_html}
      </div>
    </section>
    """


def _render_gap_svg(title: str, buckets: list[str], net: list[float], cumulative: list[float]) -> str:
    width, height = 1040, 315
    left, right, top, bottom = 68, 18, 58, 82
    plot_w = width - left - right
    plot_h = height - top - bottom
    minimum, maximum = _chart_bounds([net, cumulative])
    count = max(len(buckets), 1)
    slot = plot_w / count
    bar_w = min(34, slot * 0.56)
    zero_y = _chart_y(0, minimum, maximum, top, plot_h)

    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = _chart_y(tick, minimum, maximum, top, plot_h)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{_svg_num(y + 3)}" text-anchor="end" class="axis-label">{html.escape(_svg_label(tick))}</text>'
        )

    bars = []
    points = []
    for index, value in enumerate(net):
        x = left + slot * index + (slot - bar_w) / 2
        y = _chart_y(value, minimum, maximum, top, plot_h)
        rect_y = min(y, zero_y)
        rect_h = max(abs(zero_y - y), 1)
        color = "#002E5F" if value >= 0 else "#B42318"
        bars.append(
            f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.76"/>'
        )
    for index, value in enumerate(cumulative):
        x = left + slot * index + slot / 2
        y = _chart_y(value, minimum, maximum, top, plot_h)
        points.append((x, y))

    line_points = " ".join(f"{_svg_num(x)},{_svg_num(y)}" for x, y in points)
    line = f'<polyline points="{line_points}" fill="none" stroke="#FF4B18" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
    dots = "".join(
        f'<circle cx="{_svg_num(x)}" cy="{_svg_num(y)}" r="3.2" fill="#FF4B18" stroke="#FFFFFF" stroke-width="1.2"/>'
        for x, y in points
    )
    labels = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 32}" text-anchor="end" transform="rotate(-24 {_svg_num(left + slot * i + slot / 2)} {height - 32})" class="bucket-label">{html.escape(str(bucket))}</text>'
        for i, bucket in enumerate(buckets)
    )

    return f"""
    <svg class="chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <text x="{left}" y="22" class="chart-title">{html.escape(title)}</text>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      {line}
      <g>{dots}</g>
      <g>{labels}</g>
      <rect x="{left}" y="36" width="12" height="8" rx="2" fill="#002E5F" opacity="0.76"/>
      <text x="{left + 18}" y="43" class="legend">Net Gap</text>
      <line x1="{left + 92}" y1="40" x2="{left + 112}" y2="40" stroke="#FF4B18" stroke-width="2.4"/>
      <circle cx="{left + 102}" cy="40" r="3" fill="#FF4B18"/>
      <text x="{left + 122}" y="43" class="legend">Cum Gap</text>
    </svg>
    """


def _render_assets_liabilities_svg(title: str, buckets: list[str], assets: list[float], depense: list[float]) -> str:
    depense_negative = [-abs(float(v or 0)) for v in depense]
    width, height = 1040, 315
    left, right, top, bottom = 68, 18, 58, 82
    plot_w = width - left - right
    plot_h = height - top - bottom
    minimum, maximum = _chart_bounds([assets, depense_negative])
    count = max(len(buckets), 1)
    slot = plot_w / count
    bar_w = min(26, slot * 0.30)
    zero_y = _chart_y(0, minimum, maximum, top, plot_h)

    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = _chart_y(tick, minimum, maximum, top, plot_h)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{_svg_num(y + 3)}" text-anchor="end" class="axis-label">{html.escape(_svg_label(tick))}</text>'
        )

    bars = []
    for index, (dep, asset) in enumerate(zip(depense_negative, assets)):
        center = left + slot * index + slot / 2
        for offset, value, color in ((-bar_w * 0.58, dep, "#D32F2F"), (bar_w * 0.58, asset, "#2E7D32")):
            x = center + offset - bar_w / 2
            y = _chart_y(value, minimum, maximum, top, plot_h)
            rect_y = min(y, zero_y)
            rect_h = max(abs(zero_y - y), 1)
            bars.append(
                f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.82"/>'
            )

    labels = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 32}" text-anchor="end" transform="rotate(-24 {_svg_num(left + slot * i + slot / 2)} {height - 32})" class="bucket-label">{html.escape(str(bucket))}</text>'
        for i, bucket in enumerate(buckets)
    )

    return f"""
    <svg class="chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <text x="{left}" y="22" class="chart-title">{html.escape(title)}</text>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      <g>{labels}</g>
      <rect x="{left}" y="36" width="12" height="8" rx="2" fill="#D32F2F"/>
      <text x="{left + 20}" y="43" class="legend">Depenses negatives</text>
      <rect x="{left + 210}" y="36" width="12" height="8" rx="2" fill="#2E7D32"/>
      <text x="{left + 230}" y="43" class="legend">Actifs</text>
    </svg>
    """


def _synthesis_cell(value: Any, extra_class: str = "") -> str:
    cls = ["num"]
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    if number < 0:
        cls.append("neg")
    elif number > 0:
        cls.append("pos")
    if extra_class:
        cls.append(extra_class)
    return f"<td class=\"{' '.join(cls)}\">{_fmt_money(number)}</td>"


def _render_synthesis_pdf(data: dict[str, Any]) -> str:
    buckets = data.get("buckets") or []
    rows = data.get("lignes") or {}
    scenario = str(data.get("scenario") or "base")
    reference_date = str(data.get("reference_date") or "")[:10]
    total_assets = [float(v or 0) for v in data.get("total_assets", [])]
    total_depense = [float(v or 0) for v in data.get("total_depense", [])]
    net_funding = [float(v or 0) for v in data.get("net_funding", [])]
    cumulative = [float(v or 0) for v in data.get("cumulative_net_funding", [])]
    min_cumulative = min(cumulative) if cumulative else 0.0
    worst_index = cumulative.index(min_cumulative) if cumulative else -1
    worst_bucket = buckets[worst_index] if 0 <= worst_index < len(buckets) else "-"
    negative_buckets = len([v for v in net_funding if v < 0])

    kpis = (
        ("Scenario", SCENARIO_LABELS.get(scenario, scenario), "Lecture courante"),
        ("Total actifs", _fmt_short(_sum(total_assets)), "M FCFA"),
        ("Total depenses", _fmt_short(_sum(total_depense)), "M FCFA"),
        ("Net funding", _fmt_short(_sum(net_funding)), "M FCFA"),
        ("Point bas cumule", _fmt_short(min_cumulative), worst_bucket),
        ("Buckets negatifs", str(negative_buckets), f"sur {len(buckets)}"),
    )

    header_cells = [
        "<th class=\"label-col\">Ligne (M FCFA)</th>",
        "<th class=\"total-col\">Total</th>",
    ]
    header_cells.extend(f"<th class=\"bucket\">{html.escape(str(bucket))}</th>" for bucket in buckets)

    body_rows: list[str] = []
    for group_title, tone, type_names in SYNTHESIS_ROW_GROUPS:
        body_rows.append(
            f"<tr class=\"group group-{tone}\"><th colspan=\"{len(buckets) + 2}\">{html.escape(group_title)}</th></tr>"
        )
        for type_name in type_names:
            values = rows.get(type_name)
            if not values:
                continue
            label = SYNTHESIS_TYPE_LABELS.get(type_name, type_name)
            cells = [f"<td class=\"label\">{html.escape(label)}</td>"]
            cells.append(_synthesis_cell(values[0], "total-col"))
            cells.extend(_synthesis_cell(v) for v in values[1:])
            body_rows.append(f"<tr>{''.join(cells)}</tr>")

    total_rows = (
        ("total-assets", "Total Actifs", _sum(total_assets), total_assets),
        ("total-liabilities", "Total Depenses", _sum(total_depense), total_depense),
        ("total-net", "Net Funding", _sum(net_funding), net_funding),
        ("total-cumulative", "Cumul Net Funding", None, cumulative),
    )
    for cls, label, total, values in total_rows:
        cells = [f"<td class=\"label\">{html.escape(label)}</td>"]
        cells.append("<td class=\"num total-col muted\">-</td>" if total is None else _synthesis_cell(total, "total-col"))
        cells.extend(_synthesis_cell(v) for v in values)
        body_rows.append(f"<tr class=\"summary-row {cls}\">{''.join(cells)}</tr>")

    kpi_html = "".join(
        f"""
        <div class="kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    return f"""
    <section class="synthesis-hero">
      <div>
        <div class="eyebrow">Liquidite</div>
        <h1>Synthese ALM</h1>
        <p>Lecture executive des actifs, depenses et positions nettes de funding par bucket de maturite.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(SCENARIO_LABELS.get(scenario, scenario))}</div>
        <small>Date d'arrete : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="kpi-grid">{kpi_html}</section>
    <section class="matrix-block">
      <div class="section-title">
        <h2>Matrice detaillee</h2>
        <span>Montants exprimes en millions de FCFA</span>
      </div>
      <table class="synthesis-table">
        <thead><tr>{''.join(header_cells)}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </section>
    """


def _render_charts_pdf(data: dict[str, Any]) -> str:
    scenario_blocks: list[str] = []
    overview_items: list[str] = []

    for scenario, gap_title, profile_title in CHART_SCENARIOS:
        scenario_data = data.get(scenario) or {}
        buckets = [str(v) for v in scenario_data.get("buckets", [])]
        net = [float(v or 0) for v in scenario_data.get("net_funding", [])]
        cumulative = [float(v or 0) for v in scenario_data.get("cumulative_net_funding", [])]
        assets = [float(v or 0) for v in scenario_data.get("total_assets", [])]
        depense = [float(v or 0) for v in scenario_data.get("total_depense", [])]
        min_cum = min(cumulative) if cumulative else 0.0
        max_gap = max(net, key=lambda v: abs(v)) if net else 0.0
        negative_buckets = len([v for v in net if v < 0])

        overview_items.append(
            f"""
            <div class="chart-kpi">
              <div class="kpi-label">{html.escape(SCENARIO_LABELS.get(scenario, scenario))}</div>
              <div class="kpi-value">{html.escape(_fmt_short(_sum(net)))}</div>
              <div class="kpi-helper">Net total | Point bas {html.escape(_fmt_short(min_cum))}</div>
            </div>
            """
        )

        scenario_blocks.append(
            f"""
            <section class="chart-scenario">
              <div class="scenario-heading">
                <div>
                  <div class="eyebrow">Scenario</div>
                  <h2>{html.escape(SCENARIO_LABELS.get(scenario, scenario))}</h2>
                </div>
                <div class="scenario-stats">
                  <span>Max gap: <b>{html.escape(_fmt_short(max_gap))}</b></span>
                  <span>Buckets negatifs: <b>{negative_buckets}/{len(buckets)}</b></span>
                </div>
              </div>
              <div class="chart-grid">
                <div class="chart-card">{_render_gap_svg(gap_title, buckets, net, cumulative)}</div>
                <div class="chart-card">{_render_assets_liabilities_svg(profile_title, buckets, assets, depense)}</div>
              </div>
            </section>
            """
        )

    return f"""
    <section class="charts-hero">
      <div>
        <div class="eyebrow">Visualisation</div>
        <h1>Graphes ALM</h1>
        <p>Profils de GAP, actifs et passifs par maturite pour les scenarios base, modere et severe.</p>
      </div>
      <div class="hero-meta">
        <div>6 graphes</div>
        <small>Gap net, gap cumule, actifs et passifs</small>
      </div>
    </section>
    <section class="chart-kpi-grid">{''.join(overview_items)}</section>
    {''.join(scenario_blocks)}
    """


def _render_lcr_pdf(data: dict[str, Any]) -> str:
    all_data = compute_lcr_all()
    base = all_data.get("base", data)
    worst_key, worst_data = min(
        all_data.items(),
        key=lambda item: item[1].get("lcr_pct") if item[1].get("lcr_pct") is not None else -1,
    )
    reference_date = str(base.get("reference_date") or "")[:10]
    base_lcr = base.get("lcr_pct")
    status = "Non significatif" if base_lcr is None else "Conforme" if base.get("compliant") else "Sous seuil"
    status_class = "warn" if base_lcr is None else "ok" if base.get("compliant") else "ko"

    kpis = (
        ("LCR Base", "N/D" if base_lcr is None else _fmt_pdf_value(base_lcr, percent=True, digits=1), status),
        ("HQLA pondere", _fmt_short(float(base.get("hqla", {}).get("total_weighted", 0) or 0)), "M FCFA"),
        ("Sortie nette", _fmt_short(float(base.get("net_outflows") or 0)), "M FCFA"),
        ("Entrees retenues", _fmt_short(float(base.get("retained_inflows") or 0)), "Plafond 75%"),
        ("Scenario tendu", SCENARIO_LABELS.get(worst_key, worst_key), _fmt_pdf_value(worst_data.get("lcr_pct"), percent=True, digits=1)),
    )
    kpi_html = "".join(
        f"""
        <div class="lcr-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    first_header = [
        '<th class="lcr-label" rowspan="2">Libelles</th>',
        '<th class="lcr-weight" rowspan="2">Pond.</th>',
    ]
    for key, label, _source in LCR_SCENARIOS:
        first_header.append(f'<th class="scenario scenario-{key}" colspan="2">{html.escape(label)}</th>')

    second_header: list[str] = []
    for _key, _label, _source in LCR_SCENARIOS:
        second_header.append('<th class="amount gross">Brut</th>')
        second_header.append('<th class="amount weighted">Pondere</th>')

    body_rows: list[str] = []
    for row_key, is_group, weighted_only, percent in LCR_ROWS:
        base_component = base.get("components", {}).get(row_key)
        if not base_component:
            continue
        cells = [
            f'<td class="label">{"<b>" if is_group else ""}{html.escape(base_component.get("label", row_key))}{"</b>" if is_group else ""}</td>',
            f'<td class="weight">{html.escape(str(base_component.get("weight") or ""))}</td>',
        ]
        for _scenario_key, _scenario_label, source in LCR_SCENARIOS:
            component = all_data.get(source, {}).get("components", {}).get(row_key, {})
            gross = "" if weighted_only else _fmt_pdf_value(component.get("gross"), percent=percent)
            source_data = all_data.get(source, {})
            if row_key == "lcr" and source_data.get("lcr_pct") is None:
                weighted = "Non significatif"
            else:
                weighted = _fmt_pdf_value(component.get("weighted"), percent=percent)
            lcr_class = ""
            if row_key == "lcr":
                try:
                    lcr_class = " warn" if source_data.get("lcr_pct") is None else " ok" if float(source_data.get("lcr_pct") or 0) >= 100 else " ko"
                except (TypeError, ValueError):
                    lcr_class = " ko"
            cells.append(f'<td class="num gross">{gross}</td>')
            cells.append(f'<td class="num weighted{lcr_class}">{weighted}</td>')
        group_class = " group-row" if is_group else ""
        body_rows.append(f'<tr class="{group_class.strip()}">{"".join(cells)}</tr>')

    return f"""
    <section class="lcr-hero">
      <div>
        <div class="eyebrow">Liquidite reglementaire</div>
        <h1>Liquidity Coverage Ratio</h1>
        <p>HQLA, entrees, sorties, sortie nette et ratio par scenario selon la table LCR de l'application.</p>
      </div>
      <div class="hero-meta {status_class}">
        <div>{html.escape(status)}</div>
        <small>Date d'arrete : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="lcr-kpi-grid">{kpi_html}</section>
    <section class="lcr-table-block">
      <div class="section-title">
        <h2>Table LCR reglementaire</h2>
        <span>Montants exprimes en millions de FCFA</span>
      </div>
      <table class="lcr-table">
        <thead>
          <tr>{''.join(first_header)}</tr>
          <tr>{''.join(second_header)}</tr>
        </thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </section>
    """


def _rate_row(label: str, values: list[float], average: float, buckets: list[str]) -> str:
    cells = [
        f'<td class="label">{html.escape(label)}</td>',
        f'<td class="num average">{html.escape(_fmt_rate(average))}</td>',
    ]
    cells.extend(f'<td class="num">{html.escape(_fmt_rate(values[i] if i < len(values) else 0))}</td>' for i, _ in enumerate(buckets))
    return f"<tr>{''.join(cells)}</tr>"


def _render_rate_gap_pdf(data: dict[str, Any]) -> str:
    buckets = [str(v) for v in data.get("buckets", [])]
    reference_date = str(data.get("reference_date") or "")[:10]
    average_assets = float(data.get("average_assets") or 0)
    average_liabilities = float(data.get("average_liabilities") or 0)
    average_gap = float(data.get("average_gap") or 0)
    gap = [float(v or 0) for v in data.get("gap", [])]
    min_gap = min(gap) if gap else 0.0
    worst_bucket = buckets[gap.index(min_gap)] if gap and buckets else "-"
    max_abs = max(gap, key=lambda v: abs(v)) if gap else 0.0
    max_abs_bucket = buckets[gap.index(max_abs)] if gap and buckets else "-"
    status, explanation = _rate_gap_interpretation(average_gap)

    kpis = (
        ("Actif taux moyen", _fmt_rate(average_assets), "Buckets non nuls"),
        ("Passif taux moyen", _fmt_rate(average_liabilities), "Buckets non nuls"),
        ("GAP moyen", _fmt_point(average_gap), "Debiteur - crediteur"),
        ("Bucket defavorable", worst_bucket, _fmt_point(min_gap)),
        ("Ecart absolu max", max_abs_bucket, _fmt_point(max_abs)),
    )
    kpi_html = "".join(
        f"""
        <div class="rate-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    header = (
        '<th class="rate-label">Ligne</th><th class="rate-average">Moyenne</th>'
        + ''.join(f'<th class="bucket">{html.escape(bucket)}</th>' for bucket in buckets)
    )

    asset_rows = []
    for key, label in RATE_DEBITOR_ROWS:
        values = data.get("assets", {}).get(key, [])
        avg = float(data.get("asset_averages", {}).get(key, 0) or 0)
        asset_rows.append(_rate_row(label, values, avg, buckets))

    liability_rows = []
    for key, label in RATE_CREDITOR_ROWS:
        values = data.get("liabilities", {}).get(key, [])
        avg = float(data.get("liability_averages", {}).get(key, 0) or 0)
        liability_rows.append(_rate_row(label, values, avg, buckets))

    total_assets = _rate_row("Moyenne Taux Debiteurs", data.get("total_assets", []), average_assets, buckets)
    total_liabilities = _rate_row("Moyenne Taux Crediteurs", data.get("total_liabilities", []), average_liabilities, buckets)
    gap_cells = [
        '<td class="label">Net GAP Moyen</td>',
        f'<td class="num average {"neg" if average_gap < 0 else "pos"}">{html.escape(_fmt_point(average_gap))}</td>',
    ]
    for value in gap:
        gap_cells.append(f'<td class="num {"neg" if value < 0 else "pos"}">{html.escape(_fmt_point(value))}</td>')

    return f"""
    <section class="rate-hero">
      <div>
        <div class="eyebrow">Taux d'interet</div>
        <h1>Gap de taux</h1>
        <p>Analyse des taux moyens ponderes par bucket, selon la logique validee de la version Symfony.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(status)}</div>
        <small>Date donnees : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="rate-kpi-grid">{kpi_html}</section>
    <section class="rate-chart-card">
      <div class="rate-chart-head">
        <div>
          <h2>Profil du gap par bucket</h2>
          <p>Barres : spread actifs - passifs (pts) | Lignes : taux moyens (%)</p>
        </div>
        <div class="rate-chart-legend">
          <span><i class="spread"></i>Spread actifs - passifs</span>
          <span><i class="debit"></i>Taux debiteurs</span>
          <span><i class="credit"></i>Taux crediteurs</span>
        </div>
      </div>
      {_render_rate_gap_svg(data)}
    </section>
    <section class="rate-table-block">
      <div class="section-title">
        <h2>Interest Rate Gap Analysis</h2>
        <span>{html.escape(explanation)}</span>
      </div>
      <table class="rate-table">
        <thead><tr>{header}</tr></thead>
        <tbody>
          <tr class="group-row asset"><td colspan="{len(buckets) + 2}">Taux Debiteurs</td></tr>
          {''.join(asset_rows)}
          <tr class="total-row asset-total">{total_assets}</tr>
          <tr class="group-row liability"><td colspan="{len(buckets) + 2}">Taux Crediteurs</td></tr>
          {''.join(liability_rows)}
          <tr class="total-row liability-total">{total_liabilities}</tr>
          <tr class="total-row gap-row">{''.join(gap_cells)}</tr>
        </tbody>
      </table>
    </section>
    """


def _render_nii_pdf(data: dict[str, Any]) -> str:
    base_nii = float(data.get("base_nii") or 0)
    base_revenue = float(data.get("base_interest_revenue") or 0)
    base_cost = float(data.get("base_interest_cost") or 0)
    horizon = int(data.get("horizon_days") or 365)
    reference_date = str(data.get("reference_date") or "")[:10]
    scenarios = list(data.get("scenarios", []))
    products = list(data.get("base_by_product", []))
    buckets = list(data.get("base_by_bucket", []))
    worst = min(scenarios, key=lambda item: float(item.get("delta_nii") or 0), default={})
    margin = (base_nii / base_revenue * 100) if base_revenue else 0
    asset_count = sum(1 for item in products if item.get("side") == "asset")
    liability_count = sum(1 for item in products if item.get("side") != "asset")

    kpis = [
        ("NII de base", _fmt_money(base_nii), f"{horizon} jours - FCFA"),
        ("Revenus actifs", _fmt_money(base_revenue), "Interets projetes"),
        ("Charges passifs", _fmt_money(base_cost), "Interets projetes"),
        ("Pire delta", _fmt_money(worst.get("delta_nii")), str(worst.get("label") or "-")),
    ]
    kpi_html = "".join(
        f"""
        <div class="nii-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    product_rows = []
    for item in products:
        side = "Actif" if item.get("side") == "asset" else "Passif"
        side_class = "asset" if item.get("side") == "asset" else "liability"
        product_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(_product_label(item.get("label")))}</td>'
            f'<td class="side {side_class}">{side}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("amount")))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("exposure")))}</td>'
            f'<td class="num">{html.escape(_fmt_rate_value(item.get("avg_rate")))}</td>'
            "</tr>"
        )

    scenario_rows = []
    for item in scenarios:
        delta = float(item.get("delta_nii") or 0)
        scenario_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("label") or item.get("scenario") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("interest_revenue")))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("interest_cost")))}</td>'
            f'<td class="num strong">{html.escape(_fmt_mfcfa(item.get("nii")))}</td>'
            f'<td class="num strong {"neg" if delta < 0 else "pos"}">{html.escape(_fmt_mfcfa(delta))}</td>'
            "</tr>"
        )

    bucket_rows = []
    for item in buckets:
        nii = float(item.get("nii") or 0)
        bucket_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("bucket") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("interest_revenue")))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("interest_cost")))}</td>'
            f'<td class="num strong {"neg" if nii < 0 else "pos"}">{html.escape(_fmt_mfcfa(nii))}</td>'
            "</tr>"
        )

    return f"""
    <section class="nii-hero">
      <div>
        <div class="eyebrow">Taux d'interet</div>
        <h1>NII Sensitivity</h1>
        <p>Sensibilite du resultat net d'interets aux chocs de taux paralleles et non paralleles.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(_fmt_money(base_nii, digits=0))}</div>
        <small>Horizon : {horizon} jours - Date donnees : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="nii-summary">
      <div>
        <span>Marge nette d'interets projetee</span>
        <strong>{html.escape(_fmt_money(base_nii))}</strong>
        <small>Revenus actifs - charges passifs</small>
      </div>
      <div>
        <span>Marge sur revenus actifs</span>
        <strong>{html.escape(_fmt_rate_value(margin))}</strong>
        <small>{asset_count} actifs / {liability_count} passifs</small>
      </div>
      <div>
        <span>Scenario le plus defavorable</span>
        <strong class="neg">{html.escape(_fmt_money(worst.get("delta_nii")))}</strong>
        <small>{html.escape(str(worst.get("label") or "-"))}</small>
      </div>
    </section>
    <section class="nii-kpi-grid">{kpi_html}</section>
    <section class="nii-chart-card">
      <div class="rate-chart-head">
        <div>
          <h2>Variation du NII par scenario</h2>
          <p>Barres positives en vert, impacts negatifs en rouge. Montants en FCFA.</p>
        </div>
        <div class="rate-chart-legend">
          <span><i class="nii-pos"></i>Gain NII</span>
          <span><i class="nii-neg"></i>Perte NII</span>
        </div>
      </div>
      {_render_nii_delta_svg(data)}
    </section>
    <section class="nii-grid">
      <div class="nii-table-block">
        <div class="section-title"><h2>NII de base par produit</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table nii-product-table">
          <colgroup>
            <col style="width: 30%" />
            <col style="width: 12%" />
            <col style="width: 22%" />
            <col style="width: 24%" />
            <col style="width: 12%" />
          </colgroup>
          <thead><tr><th class="label-col">Produit</th><th>Sens</th><th>Encours<br><small>M FCFA</small></th><th>Exposition proratee<br><small>M FCFA</small></th><th>Taux moyen</th></tr></thead>
          <tbody>{''.join(product_rows)}</tbody>
        </table>
      </div>
    </section>
    <section class="nii-table-stack">
      <div class="nii-table-block">
        <div class="section-title"><h2>Sensibilites par scenario</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table compact nii-scenario-table">
          <colgroup>
            <col style="width: 30%" />
            <col style="width: 18%" />
            <col style="width: 18%" />
            <col style="width: 17%" />
            <col style="width: 17%" />
          </colgroup>
          <thead><tr><th class="label-col">Scenario</th><th>Revenus actifs</th><th>Charges passifs</th><th>NII net</th><th>Delta NII</th></tr></thead>
          <tbody>{''.join(scenario_rows)}</tbody>
        </table>
      </div>
      <div class="nii-table-block">
        <div class="section-title"><h2>NII de base par bucket</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table compact nii-bucket-table">
          <colgroup>
            <col style="width: 31%" />
            <col style="width: 23%" />
            <col style="width: 23%" />
            <col style="width: 23%" />
          </colgroup>
          <thead><tr><th class="label-col">Bucket</th><th>Revenus actifs</th><th>Charges passifs</th><th>NII net</th></tr></thead>
          <tbody>{''.join(bucket_rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _render_eve_pdf(data: dict[str, Any]) -> str:
    base_eve = float(data.get("base_eve") or 0)
    base_pv_assets = float(data.get("base_pv_assets") or 0)
    base_pv_liabilities = float(data.get("base_pv_liabilities") or 0)
    reference_date = str(data.get("reference_date") or "")[:10]
    scenarios = list(data.get("scenarios", []))
    products = list(data.get("base_by_product", []))
    buckets = list(data.get("base_by_bucket", []))
    enriched_html = _render_eve_enriched_pdf(data.get("enriched"), data.get("enriched_error"))
    worst = data.get("worst_case") or min(scenarios, key=lambda item: float(item.get("delta_eve") or 0), default={})
    eve_ratio = (base_eve / base_pv_assets * 100) if base_pv_assets else 0
    asset_count = sum(1 for item in products if item.get("side") == "asset")
    liability_count = sum(1 for item in products if item.get("side") != "asset")

    kpis = [
        ("EVE de base", _fmt_money(base_eve), "PV actifs - PV passifs"),
        ("PV actifs", _fmt_money(base_pv_assets), "FCFA actualises"),
        ("PV passifs", _fmt_money(base_pv_liabilities), "FCFA actualises"),
        ("Pire delta", _fmt_money(worst.get("delta_eve") if isinstance(worst, dict) else None), str((worst or {}).get("label") or "-")),
    ]
    kpi_html = "".join(
        f"""
        <div class="nii-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    product_rows = []
    for item in products:
        side = "Actif" if item.get("side") == "asset" else "Passif"
        side_class = "asset" if item.get("side") == "asset" else "liability"
        product_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(_product_label(item.get("label")))}</td>'
            f'<td class="side {side_class}">{side}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("amount")))}</td>'
            f'<td class="num strong">{html.escape(_fmt_mfcfa(item.get("pv")))}</td>'
            f'<td class="num">{html.escape(_fmt_rate_value(item.get("avg_rate")))}</td>'
            f'<td class="num">{html.escape(_fmt_money(item.get("duration_years"), digits=2))}</td>'
            "</tr>"
        )

    scenario_rows = []
    for item in scenarios:
        delta = float(item.get("delta_eve") or 0)
        scenario_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("label") or item.get("scenario") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("pv_assets")))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("pv_liabilities")))}</td>'
            f'<td class="num strong">{html.escape(_fmt_mfcfa(item.get("eve")))}</td>'
            f'<td class="num strong {"neg" if delta < 0 else "pos"}">{html.escape(_fmt_mfcfa(delta))}</td>'
            "</tr>"
        )

    bucket_rows = []
    for item in buckets:
        eve = float(item.get("eve") or 0)
        bucket_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("bucket") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("pv_assets")))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(item.get("pv_liabilities")))}</td>'
            f'<td class="num strong {"neg" if eve < 0 else "pos"}">{html.escape(_fmt_mfcfa(eve))}</td>'
            "</tr>"
        )

    worst_label = str((worst or {}).get("label") or "-") if isinstance(worst, dict) else "-"
    worst_delta = (worst or {}).get("delta_eve") if isinstance(worst, dict) else None
    return f"""
    <section class="nii-hero">
      <div>
        <div class="eyebrow">IRRBB</div>
        <h1>EVE Sensitivity</h1>
        <p>Sensibilite de la valeur economique des fonds propres aux chocs de taux paralleles et non paralleles.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(_fmt_money(base_eve, digits=0))}</div>
        <small>Date donnees : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="nii-summary">
      <div>
        <span>Valeur economique des fonds propres</span>
        <strong>{html.escape(_fmt_money(base_eve))}</strong>
        <small>PV actifs - PV passifs</small>
      </div>
      <div>
        <span>EVE / PV actifs</span>
        <strong>{html.escape(_fmt_rate_value(eve_ratio))}</strong>
        <small>{asset_count} actifs / {liability_count} passifs</small>
      </div>
      <div>
        <span>Pire perte economique</span>
        <strong class="neg">{html.escape(_fmt_money(worst_delta))}</strong>
        <small>{html.escape(worst_label)}</small>
      </div>
    </section>
    <section class="nii-kpi-grid">{kpi_html}</section>
    <section class="nii-chart-card">
      <div class="rate-chart-head">
        <div>
          <h2>Variation EVE par scenario</h2>
          <p>Barres positives en vert, pertes economiques en rouge. Montants en FCFA.</p>
        </div>
        <div class="rate-chart-legend">
          <span><i class="nii-pos"></i>Gain EVE</span>
          <span><i class="nii-neg"></i>Perte EVE</span>
        </div>
      </div>
      {_render_eve_delta_svg(data)}
    </section>
    <section class="nii-grid">
      <div class="nii-table-block eve-product-block">
        <div class="section-title"><h2>EVE de base par produit</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table nii-product-table">
          <colgroup>
            <col style="width: 27%" />
            <col style="width: 10%" />
            <col style="width: 18%" />
            <col style="width: 18%" />
            <col style="width: 13%" />
            <col style="width: 14%" />
          </colgroup>
          <thead><tr><th class="label-col">Produit</th><th>Sens</th><th>Encours<br><small>M FCFA</small></th><th>PV<br><small>M FCFA</small></th><th>Taux moyen</th><th>Duration<br><small>annees</small></th></tr></thead>
          <tbody>{''.join(product_rows)}</tbody>
        </table>
      </div>
    </section>
    <section class="nii-table-stack">
      <div class="nii-table-block">
        <div class="section-title"><h2>Sensibilites par scenario</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table compact nii-scenario-table">
          <colgroup>
            <col style="width: 30%" />
            <col style="width: 18%" />
            <col style="width: 18%" />
            <col style="width: 17%" />
            <col style="width: 17%" />
          </colgroup>
          <thead><tr><th class="label-col">Scenario</th><th>PV actifs</th><th>PV passifs</th><th>EVE</th><th>Delta EVE</th></tr></thead>
          <tbody>{''.join(scenario_rows)}</tbody>
        </table>
      </div>
      <div class="nii-table-block">
        <div class="section-title"><h2>EVE de base par bucket</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table compact nii-bucket-table">
          <colgroup>
            <col style="width: 31%" />
            <col style="width: 23%" />
            <col style="width: 23%" />
            <col style="width: 23%" />
          </colgroup>
          <thead><tr><th class="label-col">Bucket</th><th>PV actifs</th><th>PV passifs</th><th>EVE</th></tr></thead>
          <tbody>{''.join(bucket_rows)}</tbody>
        </table>
      </div>
    </section>
    {enriched_html}
    """


def _render_concentration_block(title: str, block: dict[str, Any], top_limit: int) -> str:
    hhi = float(block.get("hhi") or 0)
    hhi_level = str(block.get("hhi_level") or "-")
    hhi_class = _hhi_class(hhi_level)
    max_exposure = block.get("max_exposure") or {}
    top_rows = []
    for row in list(block.get("top_n") or [])[:top_limit]:
        top_rows.append(
            "<tr>"
            f'<td class="rank">{int(row.get("rank") or 0)}</td>'
            f'<td class="label">{html.escape(str(row.get("key") or "-"))}</td>'
            f'<td>{html.escape(str(row.get("type") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(row.get("amount")))}</td>'
            f'<td class="num">{html.escape(_fmt_rate_value(row.get("share_pct")))}</td>'
            "</tr>"
        )

    type_rows = []
    for row in block.get("type_breakdown") or []:
        share = float(row.get("share_pct") or 0)
        type_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(row.get("type") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mfcfa(row.get("amount")))}</td>'
            f'<td class="num">{html.escape(_fmt_rate_value(share))}</td>'
            f'<td><span class="mini-bar"><i style="width: {min(max(share, 0), 100):.2f}%"></i></span></td>'
            "</tr>"
        )

    return f"""
    <section class="concentration-block">
      <div class="concentration-block-head">
        <div>
          <div class="eyebrow">{html.escape(title)}</div>
          <h2>Analyse de concentration</h2>
        </div>
        <div class="hhi-badge {hhi_class}">
          <span>HHI</span>
          <strong>{html.escape(_fmt_money(hhi, digits=2))}</strong>
          <small>{html.escape(hhi_level)}</small>
        </div>
      </div>
      <div class="concentration-metrics">
        <div><span>Total</span><strong>{html.escape(_fmt_mfcfa(block.get("total")))}</strong><small>M FCFA</small></div>
        <div><span>Positions</span><strong>{html.escape(_fmt_money(block.get("count"), digits=0))}</strong><small>lignes agrégées</small></div>
        <div><span>Top 1</span><strong>{html.escape(_fmt_rate_value(block.get("top_1_pct")))}</strong><small>du total</small></div>
        <div><span>Top 10</span><strong>{html.escape(_fmt_rate_value(block.get("top_10_pct")))}</strong><small>du total</small></div>
      </div>
      <div class="max-exposure">
        <span>Plus forte position</span>
        <strong>{html.escape(str(max_exposure.get("key") or "-"))}</strong>
        <small>{html.escape(_fmt_mfcfa(max_exposure.get("amount")))} M FCFA - {html.escape(_fmt_rate_value(max_exposure.get("share_pct")))}</small>
      </div>
      <div class="concentration-table-card concentration-breakdown-card">
        <div class="section-title"><h2>Ventilation par type</h2><span>Montants en M FCFA</span></div>
        <table class="concentration-table breakdown-table">
          <colgroup><col style="width: 38%" /><col style="width: 20%" /><col style="width: 14%" /><col style="width: 28%" /></colgroup>
          <thead><tr><th>Type</th><th>Montant</th><th>Part</th><th>Poids</th></tr></thead>
          <tbody>{''.join(type_rows) if type_rows else '<tr><td colspan="4">Aucune donnee</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="concentration-top-section">
      <div class="section-title"><h2>Top positions - {html.escape(title)}</h2><span>Top {top_limit}</span></div>
      <table class="concentration-table top-table">
        <colgroup><col style="width: 7%" /><col style="width: 43%" /><col style="width: 24%" /><col style="width: 16%" /><col style="width: 10%" /></colgroup>
        <thead><tr><th>#</th><th>Référence / contrepartie</th><th>Type</th><th>Montant</th><th>Part</th></tr></thead>
        <tbody>{''.join(top_rows) if top_rows else '<tr><td colspan="5">Aucune donnee</td></tr>'}</tbody>
      </table>
    </section>
    """


def _render_scenario_curve_svg(data: dict[str, Any], scenario: str) -> str:
    curves = data.get("liquidity_curves", {})
    curve = curves.get(scenario) or next(iter(curves.values()), {})
    buckets = [str(v) for v in curve.get("buckets", [])]
    net = [float(v or 0) for v in curve.get("net_funding", [])]
    cumulative = [float(v or 0) for v in curve.get("cumulative_net_funding", [])]
    width, height = 1040, 285
    left, right, top, bottom = 76, 28, 26, 64
    plot_w = width - left - right
    plot_h = height - top - bottom
    minimum, maximum = _chart_bounds([net, cumulative, [0.0]])
    count = max(len(buckets), 1)
    slot = plot_w / count
    bar_w = min(34, slot * 0.48)

    def y_pos(value: float) -> float:
        return _chart_y(value, minimum, maximum, top, plot_h)

    zero_y = y_pos(0)
    grid = []
    for tick in _chart_ticks(minimum, maximum):
        y = y_pos(tick)
        grid.append(
            f'<line x1="{left}" y1="{_svg_num(y)}" x2="{width - right}" y2="{_svg_num(y)}" stroke="#DDE7F1" stroke-width="1"/>'
            f'<text x="{left - 10}" y="{_svg_num(y + 4)}" text-anchor="end" class="axis-label">{html.escape(_svg_label(tick))}</text>'
        )

    bars = []
    for index, value in enumerate(net):
        x = left + slot * index + (slot - bar_w) / 2
        y = y_pos(value)
        rect_y = min(y, zero_y)
        rect_h = max(abs(zero_y - y), 1)
        color = "#B42318" if value < 0 else "#002E5F"
        bars.append(
            f'<rect x="{_svg_num(x)}" y="{_svg_num(rect_y)}" width="{_svg_num(bar_w)}" height="{_svg_num(rect_h)}" rx="3" fill="{color}" opacity="0.78"/>'
        )

    line_points = []
    dots = []
    for index, value in enumerate(cumulative):
        x = left + slot * index + slot / 2
        y = y_pos(value)
        line_points.append(f"{_svg_num(x)},{_svg_num(y)}")
        dots.append(f'<circle cx="{_svg_num(x)}" cy="{_svg_num(y)}" r="3" fill="#FF4B18" stroke="#FFFFFF" stroke-width="1.1"/>')

    labels = "".join(
        f'<text x="{_svg_num(left + slot * i + slot / 2)}" y="{height - 22}" text-anchor="end" transform="rotate(-20 {_svg_num(left + slot * i + slot / 2)} {height - 22})" class="bucket-label">{html.escape(bucket)}</text>'
        for i, bucket in enumerate(buckets)
    )

    return f"""
    <svg class="rate-chart-svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img">
      <rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#FFFFFF"/>
      <g>{''.join(grid)}</g>
      <line x1="{left}" y1="{_svg_num(zero_y)}" x2="{width - right}" y2="{_svg_num(zero_y)}" stroke="#8FA3B8" stroke-width="1"/>
      <g>{''.join(bars)}</g>
      <polyline points="{' '.join(line_points)}" fill="none" stroke="#FF4B18" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
      <g>{''.join(dots)}</g>
      <g>{labels}</g>
    </svg>
    """


def _render_scenario_analysis_pdf(data: dict[str, Any]) -> str:
    scenarios = list(data.get("scenarios", []))
    interest = data.get("interest_rate", {})
    worst_liquidity = min(scenarios, key=lambda item: float(item.get("min_cumulative_gap") or 0), default={})
    worst_nii = interest.get("worst_nii") or {}
    worst_eve = interest.get("worst_eve") or {}
    selected_scenario = str(worst_liquidity.get("scenario") or "severe")
    mode_label = str(data.get("mode_label") or "Bilan statique")

    def fmt_m(value: Any) -> str:
        return f"{_fmt_money(value)} M"

    kpis = [
        ("Mode de bilan", mode_label, str(data.get("mode_note") or "")),
        ("Point bas liquidite", fmt_m(worst_liquidity.get("min_cumulative_gap")), str(worst_liquidity.get("label") or "-")),
        ("MCO defavorable", fmt_m(worst_liquidity.get("mco")), str(worst_liquidity.get("mco_label") or "-")),
        ("Basis risk", str(interest.get("basis_risk_count") or 0), "alertes taux par bucket"),
    ]
    kpi_html = "".join(
        f"""
        <div class="nii-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    scenario_rows = []
    for item in scenarios:
        lcr = item.get("lcr_pct")
        min_gap = float(item.get("min_cumulative_gap") or 0)
        mco = float(item.get("mco") or 0)
        delta = float(item.get("delta_min_cumulative_gap_vs_base") or 0)
        scenario_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("label") or item.get("scenario") or "-"))}</td>'
            f'<td class="num strong">{html.escape(_fmt_rate_value(lcr) if lcr is not None else "-")}</td>'
            f'<td class="num strong {"neg" if mco < 0 else "pos"}">{html.escape(fmt_m(mco))}</td>'
            f'<td class="num strong {"neg" if min_gap < 0 else "pos"}">{html.escape(fmt_m(min_gap))}</td>'
            f'<td class="num {"neg" if delta < 0 else "pos"}">{html.escape(fmt_m(delta))}</td>'
            f'<td class="num">{html.escape(str(item.get("negative_buckets") or 0))}</td>'
            f'<td>{html.escape("Oui" if item.get("off_balance_included") else "Non")}</td>'
            "</tr>"
        )

    basis_rows = []
    for item in list(interest.get("basis_risk_alerts", []))[:8]:
        basis_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("label") or item.get("bucket_code") or "-"))}</td>'
            f'<td class="num strong">{html.escape(_fmt_point(item.get("max_basis_spread")))}</td>'
            f'<td>{html.escape(str(item.get("severity") or "-"))}</td>'
            f'<td>{html.escape(", ".join(item.get("types_present", [])))}</td>'
            "</tr>"
        )

    if not basis_rows:
        basis_rows.append('<tr><td colspan="4" class="label">Aucune alerte de basis risk significative sur les buckets alimentes.</td></tr>')

    return f"""
    <section class="nii-hero">
      <div>
        <div class="eyebrow">Stress testing</div>
        <h1>Scenario Analysis</h1>
        <p>Comparaison ALCO des scénarios de liquidite, hors-bilan, LCR, MCO, NII, EVE et basis risk.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(str(worst_liquidity.get("label") or "-"))}</div>
        <small>Point bas : {html.escape(fmt_m(worst_liquidity.get("min_cumulative_gap")))}</small>
      </div>
    </section>
    <section class="nii-summary">
      <div>
        <span>Pire choc NII</span>
        <strong class="{'neg' if float(worst_nii.get('delta_nii') or 0) < 0 else 'pos'}">{html.escape(_fmt_mfcfa(worst_nii.get("delta_nii")))}</strong>
        <small>{html.escape(str(worst_nii.get("label") or "-"))}</small>
      </div>
      <div>
        <span>Pire choc EVE</span>
        <strong class="{'neg' if float(worst_eve.get('delta_eve') or 0) < 0 else 'pos'}">{html.escape(_fmt_mfcfa(worst_eve.get("delta_eve")))}</strong>
        <small>{html.escape(str(worst_eve.get("label") or "-"))}</small>
      </div>
      <div>
        <span>Hypotheses dynamiques</span>
        <strong>{html.escape("Activees" if data.get("dynamic_assumptions") else "Non appliquees")}</strong>
        <small>{html.escape(mode_label)}</small>
      </div>
    </section>
    <section class="nii-kpi-grid">{kpi_html}</section>
    <section class="nii-chart-card">
      <div class="rate-chart-head">
        <div>
          <h2>Courbe de liquidite - scenario defavorable</h2>
          <p>Barres : gap net par bucket. Ligne : gap net cumule. Montants en M FCFA.</p>
        </div>
        <div class="rate-chart-legend">
          <span><i class="spread"></i>Gap net</span>
          <span><i class="debit"></i>Cumul</span>
        </div>
      </div>
      {_render_scenario_curve_svg(data, selected_scenario)}
    </section>
    <section class="nii-table-stack">
      <div class="nii-table-block">
        <div class="section-title"><h2>Comparaison des scenarios</h2><span>Montants en millions de FCFA</span></div>
        <table class="nii-table compact nii-scenario-table">
          <colgroup>
            <col style="width: 20%" />
            <col style="width: 12%" />
            <col style="width: 14%" />
            <col style="width: 17%" />
            <col style="width: 15%" />
            <col style="width: 11%" />
            <col style="width: 11%" />
          </colgroup>
          <thead><tr><th class="label-col">Scenario</th><th>LCR</th><th>MCO</th><th>Point bas cumule</th><th>Delta vs base</th><th>Buckets neg.</th><th>Hors-bilan</th></tr></thead>
          <tbody>{''.join(scenario_rows)}</tbody>
        </table>
      </div>
      <div class="nii-table-block">
        <div class="section-title"><h2>Alertes de basis risk</h2><span>Types de taux multiples par bucket</span></div>
        <table class="nii-table compact">
          <colgroup>
            <col style="width: 28%" />
            <col style="width: 18%" />
            <col style="width: 16%" />
            <col style="width: 38%" />
          </colgroup>
          <thead><tr><th class="label-col">Bucket</th><th>Spread max</th><th>Severite</th><th>Types presents</th></tr></thead>
          <tbody>{''.join(basis_rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _render_concentration_pdf(data: dict[str, Any]) -> str:
    reference_date = str(data.get("reference_date") or "")[:10]
    deposits = data.get("deposits") or {}
    assets = data.get("assets") or {}
    top_n = int(data.get("n") or 20)
    display_top = max(1, top_n)
    deposits_hhi = float(deposits.get("hhi") or 0)
    assets_hhi = float(assets.get("hhi") or 0)
    worst_label, worst_block = ("Depots", deposits) if deposits_hhi >= assets_hhi else ("Actifs", assets)
    notes = [
        f'<li>{html.escape(str(note))}</li>'
        for note in data.get("notes") or []
    ]

    kpis = [
        ("Total depots", _fmt_mfcfa(deposits.get("total")), "M FCFA"),
        ("Total actifs", _fmt_mfcfa(assets.get("total")), "M FCFA"),
        ("HHI depots", _fmt_money(deposits_hhi, digits=2), str(deposits.get("hhi_level") or "-")),
        ("HHI actifs", _fmt_money(assets_hhi, digits=2), str(assets.get("hhi_level") or "-")),
    ]
    kpi_html = "".join(
        f"""
        <div class="concentration-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    return f"""
    <section class="concentration-hero">
      <div>
        <div class="eyebrow">Risques</div>
        <h1>Analyse de concentration</h1>
        <p>Diagnostic des poches concentrees : HHI, top positions et ventilation par nature d'exposition.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(worst_label)}</div>
        <small>Poche la plus concentree - Date donnees : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="concentration-summary">
      <div>
        <span>Poche la plus concentree</span>
        <strong>{html.escape(worst_label)}</strong>
        <small>HHI {html.escape(_fmt_money(worst_block.get("hhi"), digits=2))} - {html.escape(str(worst_block.get("hhi_level") or "-"))}</small>
      </div>
      <div>
        <span>Top 10</span>
        <strong>{html.escape(_fmt_rate_value(worst_block.get("top_10_pct")))}</strong>
        <small>du total analyse</small>
      </div>
      <div>
        <span>Top N</span>
        <strong>{display_top}</strong>
        <small>positions affichees par poche</small>
      </div>
    </section>
    <section class="concentration-kpi-grid">{kpi_html}</section>
    {'<section class="concentration-notes"><ul>' + ''.join(notes) + '</ul></section>' if notes else ''}
    {_render_concentration_block("Depots", deposits, display_top)}
    {_render_concentration_block("Actifs", assets, display_top)}
    """


def _fmt_mc_amount(value: Any) -> str:
    """Multicurrency service already returns amounts in millions FCFA."""
    return _fmt_money(value, digits=2)


def _render_multicurrency_source_panel(row: dict[str, Any]) -> str:
    sources = list(row.get("source_breakdown") or [])[:8]
    total = sum(abs(float(item.get("amount_m_base") or 0)) for item in sources) or 1.0
    source_rows = []
    for item in sources:
        amount = float(item.get("amount_m_base") or 0)
        weight = min(abs(amount) / total * 100, 100)
        source_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(item.get("source") or "-"))}</td>'
            f'<td class="num">{html.escape(_fmt_mc_amount(amount))}</td>'
            f'<td><span class="mini-bar"><i style="width: {_svg_num(weight)}%"></i></span></td>'
            "</tr>"
        )
    return f"""
    <div class="mc-source-card">
      <div class="section-title"><h2>Ventilation de {html.escape(str(row.get("currency") or "-"))}</h2><span>Sources principales</span></div>
      <table class="mc-table mc-source-table">
        <colgroup>
          <col style="width: 48%" />
          <col style="width: 24%" />
          <col style="width: 28%" />
        </colgroup>
        <thead><tr><th class="label-col">Source</th><th>Montant<br><small>M FCFA</small></th><th>Poids</th></tr></thead>
        <tbody>{''.join(source_rows) if source_rows else '<tr><td colspan="3">Aucune ventilation.</td></tr>'}</tbody>
      </table>
    </div>
    """


def _render_multicurrency_pdf(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    currencies = list(data.get("by_currency") or [])
    buckets = [str(bucket) for bucket in data.get("buckets") or []]
    reference_date = str(data.get("reference_date") or "")[:10]
    worst = summary.get("worst_currency") or (currencies[0] if currencies else {})
    worst_currency = str(worst.get("currency") or "-") if isinstance(worst, dict) else "-"

    summary_cards = [
        ("Devise la plus sensible", worst_currency, f"Net {html.escape(_fmt_mc_amount((worst or {}).get('net_total') if isinstance(worst, dict) else None))} M FCFA"),
        ("Part FCY", _fmt_rate_value(summary.get("fcy_share_pct")), f"{int(summary.get('fcy_currency_count') or 0)} devise(s) FCY"),
        ("Pire bucket global", str(summary.get("worst_bucket") or "-"), f"{html.escape(_fmt_mc_amount(summary.get('worst_bucket_gap')))} M FCFA"),
    ]
    summary_html = "".join(
        f"""
        <div>
          <span>{html.escape(label)}</span>
          <strong>{html.escape(value)}</strong>
          <small>{helper}</small>
        </div>
        """
        for label, value, helper in summary_cards
    )

    kpis = [
        ("Actifs LCY", _fmt_mc_amount(summary.get("lcy_assets")), "M FCFA"),
        ("Net LCY", _fmt_mc_amount(summary.get("lcy_net")), "M FCFA"),
        ("Actifs FCY", _fmt_mc_amount(summary.get("fcy_assets")), "M FCFA convertis"),
        ("Net FCY", _fmt_mc_amount(summary.get("fcy_net")), "M FCFA convertis"),
    ]
    kpi_html = "".join(
        f"""
        <div class="mc-kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-helper">{html.escape(helper)}</div>
        </div>
        """
        for label, value, helper in kpis
    )

    alert_rows = "".join(f"<li>{html.escape(str(alert))}</li>" for alert in data.get("alerts") or [])

    currency_rows = []
    for row in currencies:
        net = float(row.get("net_total") or 0)
        fx_label = "Manquant" if row.get("fx_missing") else _fmt_money(row.get("fx_rate"), digits=4)
        currency_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(row.get("currency") or "-"))}</td>'
            f'<td><span class="ccy-badge {"lcy" if row.get("is_lcy") else "fcy"}">{"LCY" if row.get("is_lcy") else "FCY"}</span></td>'
            f'<td class="num">{html.escape(_fmt_mc_amount(row.get("actif_total")))}</td>'
            f'<td class="num">{html.escape(_fmt_mc_amount(row.get("passif_total")))}</td>'
            f'<td class="num strong {"neg" if net < 0 else "pos"}">{html.escape(_fmt_mc_amount(net))}</td>'
            f'<td class="num">{html.escape(str(row.get("worst_bucket") or "-"))} / {html.escape(_fmt_mc_amount(row.get("worst_gap")))}</td>'
            f'<td class="num">{html.escape(fx_label)}</td>'
            "</tr>"
        )

    gap_header = "".join(f"<th>{html.escape(bucket)}</th>" for bucket in buckets)

    def gap_cells(values: list[Any]) -> str:
        cells = []
        for value in values:
            number = float(value or 0)
            cells.append(f'<td class="num {"neg" if number < 0 else "pos"}">{html.escape(_fmt_mc_amount(number))}</td>')
        return "".join(cells)

    gap_rows = []
    for row in currencies:
        net = float(row.get("net_total") or 0)
        gap_rows.append(
            "<tr>"
            f'<td class="label">{html.escape(str(row.get("currency") or "-"))}</td>'
            f'<td class="num strong {"neg" if net < 0 else "pos"}">{html.escape(_fmt_mc_amount(net))}</td>'
            f'{gap_cells(list(row.get("gap") or []))}'
            "</tr>"
        )
    fcy_net = float(summary.get("fcy_net") or 0)
    total_net = float(summary.get("total_net") or 0)
    gap_rows.append(
        '<tr class="total-fcy">'
        '<td class="label">Total FCY</td>'
        f'<td class="num strong {"neg" if fcy_net < 0 else "pos"}">{html.escape(_fmt_mc_amount(fcy_net))}</td>'
        f'{gap_cells(list(summary.get("fcy_gap") or []))}'
        "</tr>"
    )
    gap_rows.append(
        '<tr class="total-all">'
        '<td class="label">Total toutes devises</td>'
        f'<td class="num strong {"neg" if total_net < 0 else "pos"}">{html.escape(_fmt_mc_amount(total_net))}</td>'
        f'{gap_cells(list(summary.get("total_gap") or []))}'
        "</tr>"
    )

    source_panel = _render_multicurrency_source_panel(worst) if isinstance(worst, dict) and worst else ""

    return f"""
    <section class="mc-hero">
      <div>
        <div class="eyebrow">Multi-devises</div>
        <h1>Positions par devise</h1>
        <p>Pilotage LCY / FCY des actifs, passifs, gaps nets et échéances après conversion en millions FCFA.</p>
      </div>
      <div class="hero-meta">
        <div>{html.escape(worst_currency)}</div>
        <small>Date donnees : {html.escape(reference_date or "-")}</small>
      </div>
    </section>
    <section class="mc-summary">{summary_html}</section>
    <section class="mc-kpi-grid">{kpi_html}</section>
    {'<section class="mc-alerts"><ul>' + alert_rows + '</ul></section>' if alert_rows else ''}
    <section class="mc-layout">
      <div class="mc-table-block">
        <div class="section-title"><h2>Détail par devise</h2><span>Montants en M FCFA</span></div>
        <table class="mc-table mc-currency-table">
          <colgroup>
            <col style="width: 13%" />
            <col style="width: 8%" />
            <col style="width: 15%" />
            <col style="width: 15%" />
            <col style="width: 15%" />
            <col style="width: 23%" />
            <col style="width: 11%" />
          </colgroup>
          <thead><tr><th class="label-col">Devise</th><th>Type</th><th>Actifs</th><th>Passifs</th><th>Net</th><th>Pire bucket</th><th>FX</th></tr></thead>
          <tbody>{''.join(currency_rows) if currency_rows else '<tr><td colspan="7">Aucune position en devises identifiée.</td></tr>'}</tbody>
        </table>
      </div>
      {source_panel}
    </section>
    <section class="mc-gap-block">
      <div class="section-title"><h2>Gaps par bucket</h2><span>Position nette par devise et maturite - M FCFA</span></div>
      <table class="mc-table mc-gap-table">
        <thead><tr><th class="label-col">Devise</th><th>Total net</th>{gap_header}</tr></thead>
        <tbody>{''.join(gap_rows)}</tbody>
      </table>
    </section>
    """


def _render_table(title: str, value: Any, depth: int = 0) -> str:
    if isinstance(value, dict):
        simple_items = {
            k: v for k, v in value.items()
            if not isinstance(v, (dict, list, tuple))
        }
        complex_items = {
            k: v for k, v in value.items()
            if isinstance(v, (dict, list, tuple))
        }

        parts = [f"<section class='block depth-{depth}'><h2>{html.escape(title)}</h2>"]
        if simple_items:
            parts.append("<table><tbody>")
            for key, val in simple_items.items():
                parts.append(
                    f"<tr><th>{html.escape(str(key))}</th><td>{_fmt(val)}</td></tr>"
                )
            parts.append("</tbody></table>")
        for key, val in complex_items.items():
            parts.append(_render_table(str(key), val, depth + 1))
        parts.append("</section>")
        return "".join(parts)

    if isinstance(value, (list, tuple)):
        if not value:
            return f"<section class='block depth-{depth}'><h2>{html.escape(title)}</h2><p>Aucune donnee.</p></section>"
        if all(isinstance(row, dict) for row in value):
            keys = list(dict.fromkeys(k for row in value for k in row.keys()))
            rows = ["<table><thead><tr>"]
            rows += [f"<th>{html.escape(str(k))}</th>" for k in keys]
            rows.append("</tr></thead><tbody>")
            for row in value:
                rows.append("<tr>")
                for key in keys:
                    rows.append(f"<td>{_fmt(row.get(key))}</td>")
                rows.append("</tr>")
            rows.append("</tbody></table>")
            return f"<section class='block depth-{depth}'><h2>{html.escape(title)}</h2>{''.join(rows)}</section>"

        rows = ["<table><thead><tr>"]
        rows += [f"<th>{idx + 1}</th>" for idx in range(len(value))]
        rows.append("</tr></thead><tbody><tr>")
        rows += [f"<td>{_fmt(v)}</td>" for v in value]
        rows.append("</tr></tbody></table>")
        return f"<section class='block depth-{depth}'><h2>{html.escape(title)}</h2>{''.join(rows)}</section>"

    return f"<section class='block depth-{depth}'><h2>{html.escape(title)}</h2><p>{_fmt(value)}</p></section>"


def _annotation_scope_for_report(report_type: str, params: dict[str, Any]) -> tuple[str, str] | None:
    scope = REPORT_ANNOTATION_SCOPES.get(report_type)
    if not scope:
        return None
    section, scenario_source = scope
    if scenario_source == "scenario":
        scenario = str(params.get("scenario") or "base")
        if scenario not in ("base", "modere", "severe"):
            scenario = "base"
    else:
        scenario = scenario_source
    return section, scenario


def _render_report_annotation(report_type: str, params: dict[str, Any]) -> str:
    scope = _annotation_scope_for_report(report_type, params)
    if not scope:
        return ""
    section, scenario = scope
    annotation = (
        ReportAnnotation.objects
        .select_related("created_by")
        .filter(section=section, scenario=scenario)
        .order_by("-created_at")
        .first()
    )
    if not annotation or not annotation.body:
        return ""

    author = annotation.created_by.get_full_name() if annotation.created_by else ""
    author = author or (annotation.created_by.get_username() if annotation.created_by else "Utilisateur")
    date_label = annotation.created_at.strftime("%d/%m/%Y %H:%M")
    scope_label = f"{section}{' / ' + scenario if scenario else ''}"
    title = annotation.title or "Commentaire de lecture"
    body = html.escape(annotation.body).replace("\n", "<br />")

    return f"""
    <section class="pdf-annotation-card">
      <div class="section-title">
        <h2>{html.escape(title)}</h2>
        <span>{html.escape(scope_label)} - {html.escape(author)} - {html.escape(date_label)}</span>
      </div>
      <p>{body}</p>
    </section>
    """


def _render_model_versioning_pdf(report_type: str, params: dict[str, Any]) -> str:
    snapshot = report_version_snapshot(report_type, params)
    assumptions = snapshot.get("assumptions") or []
    scenarios = snapshot.get("scenarios") or []
    assumption_rows = []
    for row in assumptions[:8]:
        assumption_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('code') or '-'))}</td>"
            f"<td>{html.escape(str(row.get('category') or '-'))}</td>"
            f"<td class=\"num\">v{html.escape(str(row.get('version') or '-'))}</td>"
            f"<td class=\"num\">{html.escape(str(row.get('value') or '-'))}</td>"
            f"<td>{html.escape(str(row.get('activated_at') or '-'))}</td>"
            "</tr>"
        )
    if not assumption_rows:
        assumption_rows.append("<tr><td colspan=\"5\">Aucune hypothèse active trouvée.</td></tr>")

    scenario_labels = ", ".join(
        f"{item.get('label') or item.get('code')} ({item.get('scope')})"
        for item in scenarios[:6]
    ) or "Aucun scénario actif trouvé"
    more_assumptions = max(int(snapshot.get("assumptions_count") or 0) - 8, 0)
    more_label = f" + {more_assumptions} autre(s)" if more_assumptions else ""

    return f"""
    <section class="pdf-version-card">
      <div class="section-title">
        <h2>Version modele et hypotheses</h2>
        <span>Empreinte {html.escape(str(snapshot.get('assumptions_digest') or '-'))}</span>
      </div>
      <div class="version-kpis">
        <div><span>Version application</span><b>{html.escape(str(snapshot.get('app_version') or '-'))}</b></div>
        <div><span>Contexte rapport</span><b>{html.escape(str(snapshot.get('requested_scenario') or '-'))}</b></div>
        <div><span>Hypotheses actives</span><b>{int(snapshot.get('assumptions_count') or 0)}</b></div>
        <div><span>Scenarios actifs</span><b>{int(snapshot.get('scenarios_count') or 0)}</b></div>
      </div>
      <table class="version-table">
        <thead><tr><th>Hypothese</th><th>Categorie</th><th>Version</th><th>Valeur</th><th>Activation</th></tr></thead>
        <tbody>{''.join(assumption_rows)}</tbody>
      </table>
      <p class="version-scenarios"><b>Scenarios actifs :</b> {html.escape(scenario_labels)}{html.escape(more_label)}</p>
    </section>
    """


def build_report_pdf(report_type: str, params: dict[str, Any], user_label: str) -> bytes:
    report_title, payload = get_report_payload(report_type, params)
    generated_at = datetime.now()
    bank_name, bank_logo = _bank_branding()
    public_user_label = _public_user_label(user_label)
    footer_text = (
        f"{bank_name} - {public_user_label} - {generated_at:%d/%m/%Y %H:%M}"
        if bank_name
        else f"{public_user_label} - {generated_at:%d/%m/%Y %H:%M}"
    )
    if report_type == "synthesis":
        body = _render_synthesis_pdf(payload)
    elif report_type == "charts":
        body = _render_charts_pdf(payload)
    elif report_type == "lcr":
        body = _render_lcr_pdf(payload)
    elif report_type == "rate_gap":
        body = _render_rate_gap_pdf(payload)
    elif report_type == "nii":
        body = _render_nii_pdf(payload)
    elif report_type == "eve":
        body = _render_eve_pdf(payload)
    elif report_type == "scenario_analysis":
        body = _render_scenario_analysis_pdf(payload)
    elif report_type == "concentration":
        body = _render_concentration_pdf(payload)
    elif report_type == "multicurrency":
        body = _render_multicurrency_pdf(payload)
    else:
        body = _render_table(report_title, payload)
    body += _render_report_annotation(report_type, params)
    body += _render_model_versioning_pdf(report_type, params)
    designed_reports = ("synthesis", "charts", "lcr", "rate_gap", "nii", "eve", "scenario_analysis", "concentration", "multicurrency")
    cover_heading = "" if report_type in designed_reports else f"<h1>{html.escape(report_title)}</h1>"
    logo_watermark = ""
    if report_type in designed_reports:
        logo_uri = _logo_watermark_data_uri()
        if logo_uri:
            logo_watermark = f'<img class="pdf-logo-watermark" src="{logo_uri}" alt="" />'
    client_brand = _client_brand_html(bank_name, bank_logo)

    html_str = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<style>
@page {{
  size: A4 landscape;
  margin: 12mm 10mm 14mm;
  @bottom-right {{
    content: "{html.escape(footer_text)}";
    font-size: 8px;
    color: #8A94A6;
  }}
}}
body {{
  font-family: Arial, sans-serif;
  color: #111827;
  font-size: 10px;
  margin: 0;
}}
.pdf-logo-watermark {{
  position: fixed;
  left: 50%;
  top: 50%;
  width: 135mm;
  transform: translate(-50%, -50%);
  opacity: 0.035;
  z-index: 0;
}}
.pdf-content {{
  position: relative;
  z-index: 1;
}}
.cover {{
  border-bottom: 3px solid #FF4B18;
  margin-bottom: 14px;
  padding-bottom: 10px;
}}
.cover-top {{
  display: table;
  width: 100%;
}}
.client-brand {{
  display: table-cell;
  vertical-align: middle;
  text-align: left;
  color: #002E5F;
  font-weight: 900;
  font-size: 17px;
}}
.client-brand img {{
  max-height: 42px;
  max-width: 150px;
  object-fit: contain;
  vertical-align: middle;
  margin-right: 10px;
}}
.report-meta {{
  display: table-cell;
  vertical-align: middle;
  text-align: right;
  color: #5C697A;
  font-size: 10px;
}}
h1 {{
  color: #002E5F;
  font-size: 22px;
  margin: 10px 0 4px;
}}
h2 {{
  color: #002E5F;
  font-size: 12px;
  margin: 12px 0 6px;
}}
.block {{
  page-break-inside: avoid;
  margin-bottom: 10px;
}}
.depth-1, .depth-2 {{
  margin-left: 8px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 6px;
}}
th {{
  background: #EEF5FC;
  color: #002E5F;
  font-weight: 800;
  text-align: left;
}}
th, td {{
  border: 1px solid #D8E1EA;
  padding: 5px 6px;
  vertical-align: top;
}}
td {{
  color: #172033;
}}
.synthesis-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.synthesis-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.synthesis-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.synthesis-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.synthesis-hero p {{
  margin: 0;
  max-width: 640px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.hero-meta {{
  width: 190px;
  padding: 10px 12px;
  border: 1px solid rgba(255,255,255,0.20);
  border-radius: 10px;
  background: rgba(255,255,255,0.10);
  text-align: right;
  font-size: 14px;
  font-weight: 900;
}}
.hero-meta small {{
  display: block;
  margin-top: 4px;
  color: rgba(255,255,255,0.68);
  font-size: 8px;
  font-weight: 700;
}}
.charts-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.charts-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.charts-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.charts-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.charts-hero p {{
  margin: 0;
  max-width: 660px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.lcr-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.lcr-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.lcr-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.lcr-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.lcr-hero p {{
  margin: 0;
  max-width: 700px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.rate-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.rate-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.rate-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.rate-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.rate-hero p {{
  margin: 0;
  max-width: 700px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.nii-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.nii-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.nii-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.nii-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.nii-hero p {{
  margin: 0;
  max-width: 700px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.concentration-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.concentration-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.concentration-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.concentration-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.concentration-hero p {{
  margin: 0;
  max-width: 720px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.mc-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 92px;
  margin-bottom: 10px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.mc-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.mc-hero .eyebrow {{
  color: #FFB199;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}}
.mc-hero h1 {{
  margin: 4px 0 5px;
  color: #FFFFFF;
  font-size: 25px;
  line-height: 1;
}}
.mc-hero p {{
  margin: 0;
  max-width: 720px;
  color: rgba(255,255,255,0.72);
  font-size: 10.5px;
}}
.hero-meta.ok div {{ color: #DDF8E7; }}
.hero-meta.warn div {{ color: #FEF3C7; }}
.hero-meta.ko div {{ color: #FFE1D9; }}
.kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.kpi-label {{
  color: #5D6B7D;
  font-size: 7.8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.kpi-value {{
  margin-top: 4px;
  color: #002E5F;
  font-size: 14px;
  font-weight: 900;
  line-height: 1;
}}
.kpi-helper {{
  margin-top: 3px;
  color: #748094;
  font-size: 7.8px;
}}
.chart-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 7px 0;
  margin: 0 -7px 10px;
}}
.chart-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.lcr-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.lcr-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.rate-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.rate-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.nii-summary {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 7px 0;
  margin: 0 -7px 10px;
}}
.nii-summary > div {{
  display: table-cell;
  padding: 11px 13px;
  border: 1px solid #DDE7F1;
  border-left: 4px solid #002E5F;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.nii-summary span {{
  display: block;
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.nii-summary strong {{
  display: block;
  margin-top: 5px;
  color: #002E5F;
  font-size: 17px;
  font-weight: 900;
  line-height: 1;
}}
.nii-summary small {{
  display: block;
  margin-top: 4px;
  color: #748094;
  font-size: 8px;
}}
.nii-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.nii-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.concentration-summary {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 7px 0;
  margin: 0 -7px 10px;
}}
.concentration-summary > div {{
  display: table-cell;
  padding: 11px 13px;
  border: 1px solid #DDE7F1;
  border-left: 4px solid #002E5F;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.concentration-summary span,
.concentration-metrics span,
.max-exposure span {{
  display: block;
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.concentration-summary strong,
.concentration-metrics strong {{
  display: block;
  margin-top: 5px;
  color: #002E5F;
  font-size: 17px;
  font-weight: 900;
  line-height: 1;
}}
.concentration-summary small,
.concentration-metrics small,
.max-exposure small {{
  display: block;
  margin-top: 4px;
  color: #748094;
  font-size: 8px;
}}
.concentration-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.concentration-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.mc-summary {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 7px 0;
  margin: 0 -7px 10px;
}}
.mc-summary > div {{
  display: table-cell;
  padding: 11px 13px;
  border: 1px solid #DDE7F1;
  border-left: 4px solid #002E5F;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.mc-summary span {{
  display: block;
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.mc-summary strong {{
  display: block;
  margin-top: 5px;
  color: #002E5F;
  font-size: 17px;
  font-weight: 900;
  line-height: 1;
}}
.mc-summary small {{
  display: block;
  margin-top: 4px;
  color: #748094;
  font-size: 8px;
}}
.mc-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.mc-kpi {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
  box-shadow: 0 8px 20px rgba(0, 27, 56, 0.06);
}}
.mc-alerts {{
  margin-bottom: 10px;
  padding: 8px 12px;
  border: 1px solid #F7C948;
  border-radius: 10px;
  background: #FFF8E6;
  color: #7A4D00;
  font-size: 8.8px;
}}
.mc-alerts ul {{
  margin: 0;
  padding-left: 14px;
}}
.mc-layout {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 12px 0;
  margin: 0 -12px 16px;
}}
.mc-layout > div {{
  display: table-cell;
  vertical-align: top;
}}
.mc-table-block,
.mc-source-card,
.mc-gap-block {{
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
}}
.mc-table-block {{
  width: 64%;
}}
.mc-source-card {{
  width: 36%;
}}
.mc-gap-block {{
  page-break-before: always;
  page-break-inside: avoid;
  margin-bottom: 14px;
}}
.mc-table-block .section-title,
.mc-source-card .section-title,
.mc-gap-block .section-title {{
  padding: 13px 14px;
}}
.mc-table-block .section-title h2,
.mc-source-card .section-title h2,
.mc-gap-block .section-title h2 {{
  font-size: 15px;
}}
.mc-table-block .section-title span,
.mc-source-card .section-title span,
.mc-gap-block .section-title span {{
  font-size: 9.5px;
}}
table.mc-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 9.7px;
}}
table.mc-table th,
table.mc-table td {{
  border: 1px solid #DDE7F1;
  padding: 8.8px 8px;
}}
table.mc-table thead th {{
  color: #002E5F;
  background: #EEF5FC;
  font-size: 9px;
  font-weight: 900;
  text-align: right;
}}
table.mc-table thead small {{
  display: block;
  color: #6B7280;
  font-size: 7.3px;
  font-weight: 800;
}}
table.mc-table th.label-col,
table.mc-table td.label {{
  text-align: left;
}}
table.mc-table td.label {{
  color: #172033;
  font-weight: 780;
  line-height: 1.25;
}}
table.mc-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}}
table.mc-table td.strong {{
  font-weight: 900;
}}
.ccy-badge {{
  display: inline-block;
  padding: 4px 7px;
  border-radius: 6px;
  font-size: 7.6px;
  font-weight: 900;
}}
.ccy-badge.lcy {{
  color: #002E5F;
  background: #EAF2FA;
}}
.ccy-badge.fcy {{
  color: #7A3E00;
  background: #FFF0D8;
}}
table.mc-table .neg {{ color: #B42318; }}
table.mc-table .pos {{ color: #166534; }}
table.mc-gap-table {{
  font-size: 8.1px;
}}
table.mc-gap-table th,
table.mc-gap-table td {{
  padding: 7.2px 5.4px;
}}
table.mc-gap-table thead th {{
  font-size: 7.5px;
}}
table.mc-gap-table tr.total-fcy td {{
  background: rgba(0,46,95,0.10);
  font-weight: 900;
}}
table.mc-gap-table tr.total-all td {{
  background: rgba(255,75,24,0.10);
  font-weight: 900;
}}
.concentration-notes {{
  margin-bottom: 10px;
  padding: 8px 12px;
  border: 1px solid #DDE7F1;
  border-radius: 10px;
  background: #F7FAFD;
  color: #5D6B7D;
  font-size: 8.6px;
}}
.concentration-notes ul {{
  margin: 0;
  padding-left: 14px;
}}
.concentration-block {{
  page-break-before: always;
  page-break-inside: avoid;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  background: rgba(255,255,255,0.96);
}}
.concentration-top-section {{
  page-break-before: always;
  page-break-inside: avoid;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  background: rgba(255,255,255,0.96);
}}
.concentration-block-head {{
  display: table;
  width: 100%;
  margin-bottom: 8px;
}}
.concentration-block-head > div {{
  display: table-cell;
  vertical-align: middle;
}}
.concentration-block-head .eyebrow {{
  color: #FF4B18;
  font-size: 8px;
  font-weight: 900;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}}
.concentration-block-head h2 {{
  margin: 2px 0 0;
  color: #002E5F;
  font-size: 14px;
}}
.hhi-badge {{
  width: 118px;
  padding: 7px 9px;
  border-radius: 10px;
  text-align: right;
  background: #EEF5FC;
  border-left: 4px solid #002E5F;
}}
.hhi-badge.ok {{ border-left-color: #166534; }}
.hhi-badge.warn {{ border-left-color: #B45309; }}
.hhi-badge.ko {{ border-left-color: #B42318; }}
.hhi-badge span {{
  display: block;
  color: #5D6B7D;
  font-size: 7px;
  font-weight: 900;
  text-transform: uppercase;
}}
.hhi-badge strong {{
  display: block;
  color: #002E5F;
  font-size: 14px;
  font-weight: 900;
}}
.hhi-badge small {{
  color: #5D6B7D;
  font-size: 7px;
}}
.concentration-metrics {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 8px;
}}
.concentration-metrics > div {{
  display: table-cell;
  padding: 8px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #FFFFFF;
}}
.max-exposure {{
  margin-bottom: 9px;
  padding: 9px 11px;
  border: 1px solid rgba(0,46,95,0.12);
  border-radius: 10px;
  background: rgba(0,46,95,0.04);
}}
.max-exposure strong {{
  display: block;
  margin-top: 4px;
  color: #002E5F;
  font-size: 12px;
  font-weight: 900;
}}
.concentration-two-cols {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 8px 0;
  margin: 0 -8px;
}}
.concentration-table-card {{
  display: table-cell;
  border: 1px solid #DDE7F1;
  border-radius: 10px;
  overflow: hidden;
  background: #FFFFFF;
  vertical-align: top;
}}
.concentration-breakdown-card {{
  display: block;
  width: 58%;
}}
table.concentration-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 8.8px;
}}
table.concentration-table th,
table.concentration-table td {{
  border: 1px solid #DDE7F1;
  padding: 6.2px 6.4px;
  page-break-inside: avoid;
}}
table.concentration-table thead th {{
  color: #002E5F;
  background: #EEF5FC;
  font-weight: 900;
  text-align: right;
  font-size: 8.4px;
}}
table.concentration-table thead th:first-child,
table.concentration-table td.label,
table.concentration-table td.rank + td {{
  text-align: left;
}}
table.concentration-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}}
table.concentration-table td.rank {{
  color: #002E5F;
  font-weight: 900;
  text-align: center;
}}
.top-table td.label,
.top-table td:nth-child(2),
.top-table td:nth-child(3) {{
  line-height: 1.22;
}}
.concentration-top-section table.concentration-table {{
  font-size: 9.2px;
}}
.concentration-top-section table.concentration-table th,
.concentration-top-section table.concentration-table td {{
  padding: 7px 7.5px;
}}
.mini-bar {{
  display: block;
  height: 8px;
  border-radius: 99px;
  background: #EAF0F5;
  overflow: hidden;
}}
.mini-bar i {{
  display: block;
  height: 8px;
  border-radius: 99px;
  background: #FF4B18;
}}
.nii-chart-card {{
  padding: 10px 12px 8px;
  margin-bottom: 10px;
  border: 1px solid #DDE7F1;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.nii-chart-svg {{
  display: block;
  width: 100%;
  height: 44mm;
}}
.eve-chart-svg {{
  height: 66mm;
}}
.nii-value-label {{
  fill: #172033;
  font-size: 7.4px;
  font-weight: 900;
}}
.eve-bucket-label {{
  font-size: 7.4px;
  font-weight: 800;
}}
.rate-chart-legend .nii-pos {{ background: #166534; }}
.rate-chart-legend .nii-neg {{ background: #B42318; }}
.rate-chart-card {{
  padding: 10px 12px 8px;
  margin-bottom: 8px;
  border: 1px solid #DDE7F1;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.rate-chart-head {{
  display: table;
  width: 100%;
  margin-bottom: 2px;
}}
.rate-chart-head > div {{
  display: table-cell;
  vertical-align: top;
}}
.rate-chart-head h2 {{
  margin: 0;
  color: #002E5F;
  font-size: 13px;
  font-weight: 900;
}}
.rate-chart-head p {{
  margin: 3px 0 0;
  color: #5D6B7D;
  font-size: 8.3px;
}}
.rate-chart-legend {{
  text-align: right;
  white-space: nowrap;
  padding-top: 2px;
}}
.rate-chart-legend span {{
  display: inline-block;
  margin-left: 10px;
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 700;
}}
.rate-chart-legend i {{
  display: inline-block;
  width: 10px;
  height: 6px;
  margin-right: 4px;
  border-radius: 2px;
  vertical-align: middle;
}}
.rate-chart-legend .spread {{ background: #002E5F; }}
.rate-chart-legend .debit {{
  background: #FF4B18;
  height: 3px;
}}
.rate-chart-legend .credit {{
  background: #735247;
  height: 3px;
}}
.rate-chart-svg {{
  display: block;
  width: 100%;
  height: 62mm;
}}
.chart-scenario {{
  page-break-inside: avoid;
  margin-bottom: 11px;
  padding: 10px;
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  background: rgba(255,255,255,0.94);
}}
.scenario-heading {{
  display: table;
  width: 100%;
  margin-bottom: 8px;
}}
.scenario-heading > div {{
  display: table-cell;
  vertical-align: middle;
}}
.scenario-heading .eyebrow {{
  color: #FF4B18;
  font-size: 7.5px;
  font-weight: 900;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}}
.scenario-heading h2 {{
  margin: 2px 0 0;
  color: #002E5F;
  font-size: 13px;
}}
.scenario-stats {{
  text-align: right;
  color: #5D6B7D;
  font-size: 8px;
}}
.scenario-stats span {{
  display: inline-block;
  margin-left: 10px;
}}
.scenario-stats b {{
  color: #002E5F;
}}
.chart-grid {{
  width: 100%;
  margin: 0;
}}
.chart-card {{
  display: block;
  padding: 6px;
  margin-bottom: 16px;
  border: 1px solid #DDE7F1;
  border-radius: 10px;
  background: #FFFFFF;
  box-shadow: 0 10px 24px rgba(0, 27, 56, 0.05);
}}
.chart-svg {{
  display: block;
  width: 100%;
  height: 64mm;
}}
.chart-title {{
  fill: #002E5F;
  font-size: 10px;
  font-weight: 800;
}}
.axis-label {{
  fill: #6B7280;
  font-size: 7.5px;
}}
.bucket-label {{
  fill: #5C697A;
  font-size: 7px;
}}
.legend {{
  fill: #5C697A;
  font-size: 7.8px;
  font-weight: 700;
}}
.matrix-block {{
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  overflow: hidden;
}}
.section-title {{
  padding: 10px 12px;
  border-bottom: 1px solid #D8E1EA;
  background: #FFFFFF;
}}
.section-title h2 {{
  display: inline-block;
  margin: 0;
  color: #002E5F;
  font-size: 14px;
}}
.section-title span {{
  float: right;
  color: #6B7280;
  font-size: 9px;
  margin-top: 2px;
}}
.pdf-annotation-card {{
  margin-top: 12px;
  border: 1px solid #D8E1EA;
  border-left: 4px solid #FF4B18;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
  page-break-inside: avoid;
}}
.pdf-annotation-card p {{
  margin: 0;
  padding: 11px 12px 12px;
  color: #172033;
  font-size: 11px;
  line-height: 1.55;
  white-space: normal;
}}
.pdf-version-card {{
  margin-top: 12px;
  border: 1px solid #D8E1EA;
  border-left: 4px solid #002E5F;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
  page-break-inside: avoid;
}}
.version-kpis {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 8px 0;
  margin: 10px -8px 8px;
  padding: 0 12px;
  box-sizing: border-box;
}}
.version-kpis div {{
  display: table-cell;
  padding: 8px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #F8FBFE;
}}
.version-kpis span {{
  display: block;
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.version-kpis b {{
  display: block;
  margin-top: 3px;
  color: #002E5F;
  font-size: 13px;
}}
.version-table {{
  width: calc(100% - 24px);
  margin: 8px 12px;
  border-collapse: collapse;
  font-size: 8.6px;
}}
.version-table th,
.version-table td {{
  border: 1px solid #DDE7F1;
  padding: 5px 6px;
}}
.version-table th {{
  background: #EEF5FC;
  color: #002E5F;
}}
.version-scenarios {{
  margin: 0;
  padding: 0 12px 12px;
  color: #5D6B7D;
  font-size: 9px;
}}
table.synthesis-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 7.2px;
}}
table.synthesis-table th,
table.synthesis-table td {{
  border: 1px solid #DDE7F1;
  padding: 4.4px 4.6px;
}}
table.synthesis-table thead th {{
  background: #EEF5FC;
  color: #002E5F;
  text-align: right;
  font-size: 7px;
  font-weight: 900;
}}
table.synthesis-table thead th.label-col {{
  width: 23%;
  text-align: left;
}}
table.synthesis-table thead th.total-col {{
  width: 8%;
  background: #E3EEF9;
}}
table.synthesis-table thead th.bucket {{
  width: 6.25%;
}}
table.synthesis-table td.label {{
  color: #172033;
  font-weight: 800;
  text-align: left;
}}
table.synthesis-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}}
table.synthesis-table td.total-col {{
  background: #F2F7FC;
  color: #002E5F;
  font-weight: 900;
}}
table.synthesis-table tr.group th {{
  padding: 5px 7px;
  color: #FFFFFF;
  text-align: left;
  font-size: 8px;
  letter-spacing: 0.2px;
}}
table.synthesis-table tr.group-asset th {{ background: #002E5F; }}
table.synthesis-table tr.group-liability th {{ background: #735247; }}
table.synthesis-table tr.summary-row td {{
  font-weight: 900;
}}
table.synthesis-table tr.total-assets td {{ background: #EAF5EE; }}
table.synthesis-table tr.total-liabilities td {{ background: #FFF5E6; }}
table.synthesis-table tr.total-net td,
table.synthesis-table tr.total-cumulative td {{ background: #EEF5FC; }}
table.synthesis-table .neg {{ color: #B42318; }}
table.synthesis-table .pos {{ color: #166534; }}
table.synthesis-table .muted {{ color: #8A94A6; }}
.lcr-table-block {{
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
}}
table.lcr-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 6.8px;
}}
table.lcr-table th,
table.lcr-table td {{
  border: 1px solid #DDE7F1;
  padding: 4.2px 4px;
}}
table.lcr-table thead th {{
  color: #002E5F;
  background: #EEF5FC;
  font-weight: 900;
  text-align: center;
}}
table.lcr-table th.lcr-label {{
  width: 22%;
  text-align: left;
}}
table.lcr-table th.lcr-weight {{
  width: 5%;
}}
table.lcr-table th.scenario {{
  color: #FFFFFF;
  font-size: 7px;
  text-transform: uppercase;
  letter-spacing: 0.2px;
}}
table.lcr-table th.scenario-current {{ background: #002E5F; }}
table.lcr-table th.scenario-base {{ background: #0B3E75; }}
table.lcr-table th.scenario-modere {{ background: #8A6A5A; }}
table.lcr-table th.scenario-severe {{ background: #B73A1F; }}
table.lcr-table th.amount {{
  width: 9.1%;
  font-size: 6.5px;
}}
table.lcr-table td.label {{
  color: #172033;
  font-weight: 700;
  line-height: 1.18;
}}
table.lcr-table td.weight {{
  color: #FF4B18;
  font-weight: 900;
  text-align: center;
}}
table.lcr-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}}
table.lcr-table td.weighted {{
  background: rgba(238,245,252,0.48);
}}
table.lcr-table tr.group-row td {{
  background: #EAF0F5;
  color: #002E5F;
  font-weight: 900;
}}
table.lcr-table tr.group-row td.weight {{
  color: #002E5F;
}}
table.lcr-table td.ok {{
  color: #166534;
  font-size: 8px;
  font-weight: 900;
}}
table.lcr-table td.ko {{
  color: #B42318;
  font-size: 8px;
  font-weight: 900;
}}
table.lcr-table td.warn {{
  color: #B45309;
  font-size: 8px;
  font-weight: 900;
}}
.rate-table-block {{
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
}}
table.rate-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 7px;
}}
table.rate-table th,
table.rate-table td {{
  border: 1px solid #DDE7F1;
  padding: 4.4px 4.6px;
}}
table.rate-table thead th {{
  background: #EEF5FC;
  color: #002E5F;
  font-weight: 900;
  text-align: right;
}}
table.rate-table th.rate-label {{
  width: 21%;
  text-align: left;
}}
table.rate-table th.rate-average {{
  width: 8%;
}}
table.rate-table th.bucket {{
  width: 6.45%;
  font-size: 6.5px;
}}
table.rate-table td.label {{
  color: #172033;
  font-weight: 720;
  text-align: left;
  line-height: 1.18;
}}
table.rate-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}}
table.rate-table td.average {{
  background: #F2F7FC;
  color: #002E5F;
  font-weight: 900;
}}
table.rate-table tr.group-row td {{
  color: #FFFFFF;
  font-weight: 900;
  text-align: left;
  font-size: 8px;
}}
table.rate-table tr.group-row.asset td {{ background: #002E5F; }}
table.rate-table tr.group-row.liability td {{ background: #735247; }}
table.rate-table tr.asset-total td {{
  background: rgba(255, 75, 24, 0.13);
  font-weight: 900;
}}
table.rate-table tr.liability-total td {{
  background: rgba(115, 82, 71, 0.14);
  font-weight: 900;
}}
table.rate-table tr.gap-row td {{
  background: rgba(0, 46, 95, 0.10);
  font-weight: 900;
}}
table.rate-table .neg {{ color: #B42318; }}
table.rate-table .pos {{ color: #166534; }}
.nii-grid {{
  margin-bottom: 10px;
  page-break-before: always;
}}
.nii-table-stack {{
  margin-top: 10px;
}}
.nii-table-stack .nii-table-block {{
  margin-bottom: 10px;
  margin-left: auto;
  margin-right: auto;
  page-break-inside: avoid;
}}
.nii-table-block {{
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.96);
  width: 92%;
  margin-left: auto;
  margin-right: auto;
}}
table.nii-table {{
  margin: 0;
  table-layout: fixed;
  font-size: 10.2px;
}}
.nii-product-table {{
  width: 100%;
}}
.nii-scenario-table {{
  width: 100%;
}}
.nii-bucket-table {{
  width: 100%;
  table-layout: fixed;
}}
table.nii-table.compact {{
  font-size: 10px;
}}
table.nii-table th,
table.nii-table td {{
  border: 1px solid #DDE7F1;
  padding: 6.7px 6.8px;
}}
table.nii-table thead th {{
  background: #EEF5FC;
  color: #002E5F;
  font-weight: 900;
  text-align: right;
  font-size: 9.8px;
}}
table.nii-table thead small {{
  display: block;
  color: #6B7280;
  font-size: 7.8px;
  font-weight: 800;
}}
table.nii-table th.label-col {{
  text-align: left;
}}
table.nii-table td.label {{
  color: #172033;
  font-weight: 760;
  text-align: left;
  line-height: 1.32;
}}
table.nii-table td.num {{
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  font-weight: 760;
}}
.nii-bucket-table th,
.nii-bucket-table td {{
  overflow: visible;
}}
.nii-bucket-table th:nth-child(4),
.nii-bucket-table td:nth-child(4) {{
  padding-right: 12px;
}}
table.nii-table td.strong {{
  font-weight: 900;
}}
table.nii-table td.side {{
  text-align: center;
  font-weight: 900;
}}
table.nii-table td.side.asset {{
  color: #166534;
  background: rgba(22, 101, 52, 0.08);
}}
table.nii-table td.side.liability {{
  color: #B45309;
  background: rgba(245, 158, 11, 0.12);
}}
table.nii-table .neg,
.nii-summary .neg {{ color: #B42318; }}
table.nii-table .pos {{ color: #166534; }}
</style>
</head>
<body>
  {logo_watermark}
  <main class="pdf-content">
    <header class="cover">
      <div class="cover-top">
        {client_brand}
        <div class="report-meta">Rapport genere le {generated_at:%d/%m/%Y a %H:%M} - Utilisateur : {html.escape(public_user_label)}</div>
      </div>
      {cover_heading}
    </header>
    {body}
  </main>
</body>
</html>"""
    return HTML(string=html_str).write_pdf()
