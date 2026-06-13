"""
Export PowerPoint de tableau de bord ALCO.

Demande explicite de la Direction de la Trésorerie : « space to allow
the creation of the templates that could be converted to PPT ».

Le générateur compose un .pptx dynamiquement à partir des sections
configurées dans ReportTemplate (synthese, lcr, nii, eve, ftp,
concentration, multicurrency, commentary).
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

from apps.engine.synthesis import compute_all_scenarios
from apps.engine.lcr import compute_lcr_all
from apps.engine.rate_gap import compute_rate_gap
from apps.parameters.models import Parameter
from apps.reporting.models import ReportAnnotation
from apps.reporting.versioning import report_version_snapshot


PRIMARY = RGBColor(0x1F, 0x38, 0x64)
ACCENT = RGBColor(0x2E, 0x74, 0xB5)
LIGHT = RGBColor(0xF5, 0xF7, 0xFA)

ANNOTATION_SCOPES = (
    ("synthesis", "base", "Synthèse liquidité - Cas de base"),
    ("synthesis", "modere", "Synthèse liquidité - Stress modéré"),
    ("synthesis", "severe", "Synthèse liquidité - Stress sévère"),
    ("lcr", "", "Liquidity Coverage Ratio"),
    ("rate_gap", "", "Gap de taux"),
    ("rate_gap_by_type", "", "Gap de taux par type"),
    ("nii", "", "NII Sensitivity"),
    ("eve", "", "EVE Sensitivity"),
    ("eve_enriched", "", "EVE enrichi"),
    ("scenario_analysis", "", "Scenario Analysis"),
    ("concentration", "", "Concentration"),
    ("concentration_enriched", "", "Concentration enrichie"),
    ("multicurrency", "", "Multi-devises"),
    ("balance_sheet", "", "Bilan complet"),
    ("fx_position", "", "Position FX nette"),
)


def _fmt(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return str(n)


def _add_title_slide(prs, title: str, subtitle: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # Bandeau bleu
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(2))
    rect.fill.solid()
    rect.fill.fore_color.rgb = PRIMARY
    rect.line.fill.background()
    # Texte
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), prs.slide_width - Inches(1), Inches(1.2))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = title
    for run in p.runs:
        run.font.size = Pt(36); run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p2 = tf.add_paragraph()
    p2.text = subtitle
    for run in p2.runs:
        run.font.size = Pt(18)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    return slide


def _add_section_title(prs, title: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(2.5), prs.slide_width, Inches(1))
    rect.fill.solid()
    rect.fill.fore_color.rgb = ACCENT
    rect.line.fill.background()
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(2.7), prs.slide_width - Inches(1), Inches(0.7))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = title
    for run in p.runs:
        run.font.size = Pt(28); run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    return slide


def _add_kpi_slide(prs, title: str, kpis: list[dict]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), prs.slide_width - Inches(1), Inches(0.7))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    for run in p.runs:
        run.font.size = Pt(24); run.font.bold = True
        run.font.color.rgb = PRIMARY
    # KPI cards
    n = len(kpis)
    if n == 0:
        return slide
    card_w = (prs.slide_width - Inches(1) - Inches(0.3) * (n - 1)) / n
    for i, kpi in enumerate(kpis):
        left = Inches(0.5) + (card_w + Inches(0.3)) * i
        top = Inches(1.5)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_w, Inches(2))
        card.fill.solid(); card.fill.fore_color.rgb = LIGHT
        card.line.color.rgb = ACCENT
        card_tf = card.text_frame
        card_tf.word_wrap = True
        # Label
        p1 = card_tf.paragraphs[0]; p1.text = kpi.get("label", "")
        for r in p1.runs:
            r.font.size = Pt(14); r.font.color.rgb = PRIMARY
        # Value
        p2 = card_tf.add_paragraph(); p2.text = kpi.get("value", "")
        for r in p2.runs:
            r.font.size = Pt(28); r.font.bold = True; r.font.color.rgb = ACCENT
        # Comment
        if kpi.get("comment"):
            p3 = card_tf.add_paragraph(); p3.text = kpi["comment"]
            for r in p3.runs:
                r.font.size = Pt(11); r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)
    return slide


def _add_table_slide(prs, title: str, headers: list[str], rows: list[list[str]]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), prs.slide_width - Inches(1), Inches(0.7))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    for run in p.runs:
        run.font.size = Pt(22); run.font.bold = True; run.font.color.rgb = PRIMARY
    if not rows:
        return slide

    nrows, ncols = len(rows) + 1, len(headers)
    table = slide.shapes.add_table(
        nrows, ncols,
        Inches(0.5), Inches(1.2),
        prs.slide_width - Inches(1), Inches(0.4) * (nrows + 1),
    ).table

    # Header
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid(); cell.fill.fore_color.rgb = PRIMARY
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(11); r.font.bold = True
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    # Body
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row[:ncols]):
            cell = table.cell(i, j)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(10)
    return slide


def _add_commentary_slide(prs, title: str, body: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), prs.slide_width - Inches(1), Inches(0.6))
    p = tb.text_frame.paragraphs[0]; p.text = title
    for r in p.runs:
        r.font.size = Pt(22); r.font.bold = True; r.font.color.rgb = PRIMARY
    body_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.2),
                                         prs.slide_width - Inches(1.4), prs.slide_height - Inches(1.5))
    tf = body_box.text_frame; tf.word_wrap = True
    tf.text = body or "(aucun commentaire)"
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(13)
    return slide


# ----------------------------------------------------------------------------
# Orchestration des sections
# ----------------------------------------------------------------------------

DEFAULT_SECTIONS = [
    "title", "model_versioning", "balance_sheet", "nim_profitability",
    "synthese", "mco", "scenario_analysis", "lcr",
    "rate_gap", "rate_gap_by_type",
    "nii", "eve", "eve_enriched",
    "fx_position",
    "concentration", "concentration_enriched",
    "multicurrency", "commentary",
]


def build_alco_pptx(template_sections: list[str] | None = None) -> bytes:
    sections = template_sections or DEFAULT_SECTIONS
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    param = Parameter.get_solo()
    ref_str = (param.dateMajCore.strftime("%d/%m/%Y") if param.dateMajCore
               else datetime.now().strftime("%d/%m/%Y"))

    if "title" in sections:
        _add_title_slide(prs, "Tableau de bord ALCO",
                          f"Date d'arrêté : {ref_str}")

    if "model_versioning" in sections:
        _add_section_title(prs, "Version modèle, hypothèses et scénarios")
        _build_model_versioning_section(prs)

    if "balance_sheet" in sections:
        _add_section_title(prs, "Bilan par devise")
        _build_balance_sheet_section(prs)

    if "nim_profitability" in sections:
        _add_section_title(prs, "Profitabilité — NIM / WAR / COF")
        _build_nim_profitability_section(prs)

    if "synthese" in sections:
        _add_section_title(prs, "Synthèse — Gap de liquidité")
        scenarios = compute_all_scenarios()
        for sc, data in scenarios.items():
            kpis = [
                {"label": "Total Actifs (M FCFA)",
                 "value": _fmt(sum(data["total_assets"]))},
                {"label": "Total Dépenses (M FCFA)",
                 "value": _fmt(sum(data["total_depense"]))},
                {"label": "Net funding (M FCFA)",
                 "value": _fmt(sum(data["net_funding"]))},
            ]
            _add_kpi_slide(prs, f"Synthèse {sc.upper()}", kpis)

    if "mco" in sections:
        _add_section_title(prs, "Maximum Cumulative Outflow")
        _build_mco_section(prs)

    if "scenario_analysis" in sections:
        _add_section_title(prs, "Scenario Analysis")
        _build_scenario_analysis_section(prs)

    if "lcr" in sections:
        _add_section_title(prs, "Liquidity Coverage Ratio")
        lcr = compute_lcr_all()
        rows = [
            [sc.upper(),
             _fmt(d["hqla"]["total_weighted"]),
             _fmt(d["net_outflows"]),
             _fmt(d["lcr_pct"]) + " %" if d["lcr_pct"] is not None else "—",
             "✓" if d["compliant"] else "✗"]
            for sc, d in lcr.items()
        ]
        _add_table_slide(prs, "LCR par scénario",
                          ["Scénario", "HQLA pondéré", "Sortie nette", "LCR", "Conformité"],
                          rows)

    if "rate_gap" in sections:
        _add_section_title(prs, "Gap de taux d'intérêt")
        rg = compute_rate_gap()
        rows = []
        for i, b in enumerate(rg["buckets"]):
            rows.append([b, _fmt(rg["total_assets"][i]), _fmt(rg["total_liabilities"][i]),
                         _fmt(rg["gap"][i])])
        _add_table_slide(prs, "Gap de taux contractuel par bucket",
                          ["Bucket", "Taux actifs", "Taux passifs", "Spread"], rows)

    if "rate_gap_by_type" in sections:
        _add_section_title(prs, "Gap de taux par type — Basis Risk")
        _build_rate_gap_by_type_section(prs)

    if "nii" in sections:
        try:
            from apps.analytics.nii import compute_nii_sensitivity
            nii = compute_nii_sensitivity()
            rows = [
                [s["label"], _fmt(s["nii"]), _fmt(s["delta_nii"]), f"{s['delta_pct']} %"]
                for s in nii["scenarios"]
            ]
            _add_table_slide(prs, "NII Sensitivity (12 mois)",
                              ["Scénario", "NII", "Δ NII", "Δ %"], rows)
        except Exception:
            pass

    if "eve" in sections:
        try:
            from apps.analytics.eve import compute_eve_sensitivity
            eve = compute_eve_sensitivity()
            rows = [
                [s["label"], _fmt(s["eve"]), _fmt(s["delta_eve"]), f"{s['delta_pct']} %"]
                for s in eve["scenarios"]
            ]
            _add_table_slide(prs, "EVE Sensitivity (IRRBB)",
                              ["Scénario", "EVE", "Δ EVE", "Δ %"], rows)
        except Exception:
            pass

    if "eve_enriched" in sections:
        _add_section_title(prs, "EVE Enrichi — IRRBB")
        _build_eve_enriched_section(prs)

    if "concentration" in sections:
        try:
            from apps.analytics.concentration import compute_concentration
            c = compute_concentration(n=10)
            kpis = [
                {"label": "HHI dépôts", "value": _fmt(c["deposits"]["hhi"])},
                {"label": "HHI actifs", "value": _fmt(c["assets"]["hhi"])},
                {"label": "Top 10 dépôts %", "value": f"{_fmt(c['deposits']['top_n_pct'])} %"},
                {"label": "Top 10 actifs %", "value": f"{_fmt(c['assets']['top_n_pct'])} %"},
            ]
            _add_kpi_slide(prs, "Concentration", kpis)
        except Exception:
            pass

    if "concentration_enriched" in sections:
        _add_section_title(prs, "Concentration enrichie")
        _build_concentration_enriched_section(prs)

    if "multicurrency" in sections:
        try:
            from apps.multicurrency.services import compute_positions_by_currency
            mc = compute_positions_by_currency()
            rows = [[c["currency"],
                     "LCY" if c["is_lcy"] else "FCY",
                     _fmt(c["actif_total"]),
                     _fmt(c["passif_total"]),
                     _fmt(c["actif_total"] - c["passif_total"])]
                    for c in mc["by_currency"]]
            _add_table_slide(prs, "Positions par devise",
                              ["Devise", "Type", "Total Actifs", "Total Passifs", "Net"], rows)
        except Exception:
            pass

    if "fx_position" in sections:
        _add_section_title(prs, "Position FX nette")
        _build_fx_position_section(prs)

    if "commentary" in sections:
        annotation_lines = []
        for section, scenario, label in ANNOTATION_SCOPES:
            annotation = (
                ReportAnnotation.objects
                .filter(section=section, scenario=scenario)
                .order_by("-created_at")
                .first()
            )
            if annotation and annotation.body:
                annotation_lines.append(f"{label} : {annotation.body}")
        body = "\n\n".join(filter(None, [
            "ALCO — Cas de base : " + (param.commalcobase or ""),
            "ALCO — Cas modéré : " + (param.commalcomodere or ""),
            "ALCO — Cas sévère : " + (param.commalcosevere or ""),
            "DG — Cas de base : " + (param.commdgbase or ""),
            "DG — Cas modéré : " + (param.commdgmodere or ""),
            "DG — Cas sévère : " + (param.commdgsevere or ""),
            "Commentaires par section :\n" + "\n".join(annotation_lines) if annotation_lines else "",
        ]))
        _add_commentary_slide(prs, "Commentaires ALCO et Direction Générale", body)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Phase D — Nouvelles sections
# ----------------------------------------------------------------------------

def _build_model_versioning_section(prs):
    """Section de traçabilité modèle/hypothèses pour le dossier ALCO."""
    snapshot = report_version_snapshot("alco_pptx", {})
    _add_kpi_slide(prs, "Version modèle et hypothèses actives", [
        {"label": "Version application", "value": str(snapshot.get("app_version", "—"))},
        {"label": "Empreinte hypothèses", "value": str(snapshot.get("assumptions_digest", "—"))},
        {"label": "Hypothèses actives", "value": str(snapshot.get("assumptions_count", 0))},
        {"label": "Scénarios actifs", "value": str(snapshot.get("scenarios_count", 0))},
    ])

    assumptions = snapshot.get("assumptions", [])
    if assumptions:
        rows = [
            [
                str(row.get("code", "")),
                str(row.get("category", "")),
                f"v{row.get('version', '')}",
                str(row.get("value", "")),
                str(row.get("activated_at", "")),
            ]
            for row in assumptions[:12]
        ]
        _add_table_slide(
            prs,
            "Hypothèses actives utilisées par les calculs",
            ["Code", "Catégorie", "Version", "Valeur", "Activation"],
            rows,
        )

    scenarios = snapshot.get("scenarios", [])
    if scenarios:
        rows = [
            [
                str(row.get("code", "")),
                str(row.get("label", "")),
                str(row.get("scope", "")),
                "Oui" if row.get("approved") else "Non",
            ]
            for row in scenarios[:12]
        ]
        _add_table_slide(
            prs,
            "Bibliothèque de scénarios active",
            ["Code", "Libellé", "Portée", "Approuvé"],
            rows,
        )


def _build_balance_sheet_section(prs):
    """Section bilan complet FCY/LCY/consolidé."""
    try:
        from apps.multicurrency.balance_sheet_currency import compute_balance_sheet_by_currency
        data = compute_balance_sheet_by_currency()
    except Exception as e:
        _add_kpi_slide(prs, "Bilan par devise", [{"label": "Erreur", "value": str(e)}])
        return

    if "error" in data:
        _add_kpi_slide(prs, "Bilan par devise", [{"label": "Données manquantes", "value": data["error"]}])
        return

    consolidated = data.get("consolidated", {})
    lcy = data.get("lcy_only", {})
    fcy = data.get("fcy_total", {})

    # Slide 1 : KPIs consolidés
    _add_kpi_slide(prs, f"Bilan au {data.get('date_arrete', '—')}", [
        {"label": "Total Actif (LCY)", "value": _fmt(consolidated.get("total_actif_lcy", 0) / 1e6) + " M"},
        {"label": "Total Passif (LCY)", "value": _fmt(consolidated.get("total_passif_lcy", 0) / 1e6) + " M"},
        {"label": "Gap Bilan", "value": _fmt(consolidated.get("gap_lcy", 0) / 1e6) + " M"},
        {"label": "Actif FCY (éq. LCY)", "value": _fmt(fcy.get("actif_lcy_equivalent", 0) / 1e6) + " M"},
    ])

    # Slide 2 : Tableau par devise
    devises = data.get("devises", [])
    if devises:
        headers = ["Devise", "Actif LCY (M)", "Passif LCY (M)", "Gap (M)", "Taux FX"]
        rows = [
            [
                d["devise"],
                _fmt(d.get("actif_lcy_equivalent", 0) / 1e6),
                _fmt(d.get("passif_lcy_equivalent", 0) / 1e6),
                _fmt(d.get("gap_lcy", 0) / 1e6),
                _fmt(d.get("fx_rate", 1.0)),
            ]
            for d in devises
        ]
        _add_table_slide(prs, "Bilan par devise — détail", headers, rows)


def _build_nim_profitability_section(prs):
    """Section NIM, WAR, COF, ratios de profitabilité."""
    try:
        from apps.analytics.nim import compute_profitability_ratios
        data = compute_profitability_ratios()
    except Exception as e:
        _add_kpi_slide(prs, "Profitabilité", [{"label": "Erreur", "value": str(e)}])
        return

    if "error" in data:
        _add_kpi_slide(prs, "Profitabilité", [{"label": "Données manquantes", "value": data["error"]}])
        return

    period = data.get("period", {})
    interp = data.get("interpretation", {})

    def status_icon(s):
        return {"GOOD": "✓", "WATCH": "⚠", "ALERT": "✗", "N/A": "—"}.get(s, "")

    _add_kpi_slide(prs, f"Profitabilité — {period.get('from', '')}", [
        {"label": "NIM", "value": f"{data.get('nim', 0):.2f}%", "comment": status_icon(interp.get("nim_status", ""))},
        {"label": "WAR (Actifs)", "value": f"{data.get('war', 0):.2f}%"},
        {"label": "COF (Passifs)", "value": f"{data.get('cof', 0):.2f}%"},
        {"label": "LDR", "value": f"{data.get('ldr', 0):.1f}%" if data.get("ldr") else "—", "comment": status_icon(interp.get("ldr_status", ""))},
    ])

    # Tableau par BU si disponible
    by_bu = data.get("by_bu", [])
    if by_bu:
        headers = ["Business Unit", "WAR (%)", "COF (%)", "NIM (%)", "Actif Moy. (M)", "Passif Moy. (M)"]
        rows = [
            [
                b.get("business_unit", ""),
                f"{b.get('war', 0):.2f}",
                f"{b.get('cof', 0):.2f}",
                f"{b.get('nim', 0):.2f}",
                _fmt(b.get("actif_moyen", 0) / 1e6),
                _fmt(b.get("passif_moyen", 0) / 1e6),
            ]
            for b in by_bu
        ]
        _add_table_slide(prs, "NIM par Business Unit", headers, rows)


def _build_mco_section(prs):
    """Section Maximum Cumulative Outflow."""
    try:
        from apps.engine.mco import compute_mco
        data = compute_mco()
    except Exception as e:
        _add_kpi_slide(prs, "MCO", [{"label": "Erreur", "value": str(e)}])
        return

    scenarios = data.get("scenarios", {})

    # KPIs par scénario
    kpis = []
    for sc_code in ["base", "modere", "severe"]:
        sc = scenarios.get(sc_code, {})
        mco = sc.get("mco", 0)
        mco_label = sc.get("mco_label", "—")
        kpis.append({"label": f"MCO {sc_code.capitalize()}", "value": _fmt(mco / 1e6) + " M", "comment": mco_label})
    _add_kpi_slide(prs, "Maximum Cumulative Outflow", kpis)

    # Tableau détail scénario sévère
    sc_severe = scenarios.get("severe", {})
    buckets = sc_severe.get("buckets", [])
    if buckets:
        headers = ["Bucket", "Gap Net (M)", "Hors-Bilan (M)", "Gap Cumulé (M)"]
        rows = [
            [
                b.get("label", b.get("bucket_code", "")),
                _fmt(b.get("gap_net", 0) / 1e6),
                _fmt(b.get("off_balance", 0) / 1e6),
                _fmt(b.get("gap_cumul", 0) / 1e6),
            ]
            for b in buckets
        ]
        _add_table_slide(prs, "MCO — Scénario Sévère (détail buckets)", headers, rows)


def _build_scenario_analysis_section(prs):
    """Section ALCO de comparaison stress testing statique/dynamique."""
    try:
        from apps.engine.scenario_analysis import compute_scenario_analysis

        static = compute_scenario_analysis("static")
        dynamic = compute_scenario_analysis("dynamic")
    except Exception as e:
        _add_kpi_slide(prs, "Scenario Analysis", [{"label": "Erreur", "value": str(e)}])
        return

    scenarios = static.get("scenarios", [])
    worst_liquidity = min(scenarios, key=lambda row: row.get("min_cumulative_gap", 0), default={})
    interest = static.get("interest_rate", {})
    worst_nii = interest.get("worst_nii") or {}
    worst_eve = interest.get("worst_eve") or {}

    kpis = [
        {
            "label": "Point bas liquidité",
            "value": _fmt(worst_liquidity.get("min_cumulative_gap", 0)) + " M",
            "comment": worst_liquidity.get("label", "—"),
        },
        {
            "label": "MCO défavorable",
            "value": _fmt(worst_liquidity.get("mco", 0)) + " M",
            "comment": worst_liquidity.get("mco_label", "—"),
        },
        {
            "label": "Pire NII",
            "value": _fmt((worst_nii.get("delta_nii") or 0) / 1e6) + " M",
            "comment": worst_nii.get("label", "—"),
        },
        {
            "label": "Pire EVE",
            "value": _fmt((worst_eve.get("delta_eve") or 0) / 1e6) + " M",
            "comment": f"Basis alerts : {interest.get('basis_risk_count', 0)}",
        },
    ]
    _add_kpi_slide(prs, "Scenario Analysis — synthèse", kpis)

    if scenarios:
        rows = [
            [
                row.get("label", row.get("scenario", "")),
                f"{row.get('lcr_pct', 0):.1f}%" if row.get("lcr_pct") is not None else "—",
                _fmt(row.get("mco", 0)),
                _fmt(row.get("min_cumulative_gap", 0)),
                _fmt(row.get("delta_min_cumulative_gap_vs_base", 0)),
                str(row.get("negative_buckets", 0)),
                "Oui" if row.get("off_balance_included") else "Non",
            ]
            for row in scenarios
        ]
        _add_table_slide(
            prs,
            "Scenario Analysis — bilan statique",
            ["Scénario", "LCR", "MCO (M)", "Point bas (M)", "Delta vs base", "Buckets nég.", "Hors-bilan"],
            rows,
        )

    dynamic_rows = []
    static_by_code = {row.get("scenario"): row for row in static.get("scenarios", [])}
    for row in dynamic.get("scenarios", []):
        static_row = static_by_code.get(row.get("scenario"), {})
        dynamic_rows.append(
            [
                row.get("label", row.get("scenario", "")),
                _fmt(static_row.get("min_cumulative_gap", 0)),
                _fmt(row.get("min_cumulative_gap", 0)),
                _fmt(row.get("min_cumulative_gap", 0) - static_row.get("min_cumulative_gap", 0)),
                _fmt(row.get("mco", 0)),
                str(row.get("negative_buckets", 0)),
            ]
        )
    if dynamic_rows:
        _add_table_slide(
            prs,
            "Scenario Analysis — statique vs dynamique",
            ["Scénario", "Point bas statique", "Point bas dynamique", "Impact", "MCO dynamique", "Buckets nég."],
            dynamic_rows,
        )


def _build_eve_enriched_section(prs):
    """Section EVE enrichi — table Bucket × Scénario + breaches IRRBB."""
    try:
        from apps.analytics.eve_enriched import compute_eve_enriched
        data = compute_eve_enriched()
    except Exception as e:
        _add_kpi_slide(prs, "EVE Enrichi", [{"label": "Erreur", "value": str(e)}])
        return

    nb_breaches = data.get("nb_breaches", 0)
    tier1 = data.get("tier1_capital", 0)

    # KPIs globaux
    kpis = []
    for sc_code in ["base", "parallel_up_200", "parallel_down_200"]:
        sc = data.get("scenarios", {}).get(sc_code, {})
        kpis.append({"label": sc.get("label", sc_code), "value": _fmt(sc.get("eve_total", 0) / 1e6) + " M"})
    kpis.append({"label": "Breaches IRRBB", "value": str(nb_breaches), "comment": "HIGH" if nb_breaches > 0 else "OK"})
    _add_kpi_slide(prs, "EVE Sensitivity — Enrichi", kpis)

    # Tableau des breaches
    breaches = data.get("breaches", [])
    if breaches:
        headers = ["Bucket", "Scénario", "ΔEVE (M)", "% Tier 1", "Sévérité"]
        rows = [
            [
                b.get("label", ""),
                b.get("scenario_label", b.get("scenario", "")),
                _fmt(b.get("delta_eve", 0) / 1e6),
                f"{b.get('pct_tier1', 0):.1f}%",
                b.get("severity", ""),
            ]
            for b in breaches
        ]
        _add_table_slide(prs, f"EVE — Buckets en breach (seuil {data.get('breach_threshold_pct', 15)}% Tier 1)", headers, rows)
    else:
        _add_kpi_slide(prs, "EVE — Aucun breach détecté", [
            {"label": "Statut", "value": "CONFORME", "comment": f"Seuil : {data.get('breach_threshold_pct', 15)}% Tier 1"},
        ])


def _build_rate_gap_by_type_section(prs):
    """Section gap de taux par type — analyse du basis risk."""
    try:
        from apps.engine.rate_gap import compute_rate_gap_enriched
        data = compute_rate_gap_enriched()
    except Exception as e:
        _add_kpi_slide(prs, "Gap de taux par type", [{"label": "Erreur", "value": str(e)}])
        return

    # Alertes basis risk
    alerts = data.get("basis_risk_summary", [])
    if alerts:
        headers = ["Bucket", "Spread max (%)", "Sévérité", "Types présents"]
        rows = [
            [
                a.get("label", ""),
                f"{a.get('max_basis_spread', 0):.2f}",
                a.get("severity", ""),
                ", ".join(a.get("types_present", [])),
            ]
            for a in alerts
        ]
        _add_table_slide(prs, "Basis Risk — Alertes par bucket", headers, rows)
    else:
        _add_kpi_slide(prs, "Basis Risk", [{"label": "Statut", "value": "Aucune alerte", "comment": "Spread < 0.5% sur tous les buckets"}])

    # Tableau global par bucket
    by_bucket = data.get("by_bucket", [])
    if by_bucket:
        headers = ["Bucket", "Actif (M)", "Passif (M)", "Gap (M)", "Taux Actif", "Taux Passif", "Spread"]
        rows = [
            [
                b.get("label", ""),
                _fmt(b.get("actif_amount", 0) / 1e6),
                _fmt(b.get("passif_amount", 0) / 1e6),
                _fmt(b.get("gap", 0) / 1e6),
                f"{b.get('taux_actif', 0):.2f}%",
                f"{b.get('taux_passif', 0):.2f}%",
                f"{b.get('spread', 0):.2f}%",
            ]
            for b in by_bucket
        ]
        _add_table_slide(prs, "Gap de taux — vue globale par bucket", headers, rows)


def _build_fx_position_section(prs):
    """Section position FX nette et swapped funds."""
    try:
        from apps.multicurrency.balance_sheet_currency import compute_fx_position
        data = compute_fx_position()
    except Exception as e:
        _add_kpi_slide(prs, "Position FX", [{"label": "Erreur", "value": str(e)}])
        return

    if "error" in data:
        _add_kpi_slide(prs, "Position FX", [{"label": "Données manquantes", "value": data["error"]}])
        return

    _add_kpi_slide(prs, f"Position FX nette au {data.get('date_arrete', '—')}", [
        {"label": "Position nette totale", "value": _fmt(data.get("total_position_lcy", 0) / 1e6) + " M LCY"},
        {"label": "Swapped Funds", "value": _fmt(data.get("total_swapped_funds_lcy", 0) / 1e6) + " M LCY"},
        {"label": "Devise pivot", "value": data.get("base_currency", "XAF")},
    ])

    positions = data.get("positions", [])
    if positions:
        headers = ["Devise", "Actif FCY", "Passif FCY", "HB Net FCY", "Position Nette FCY", "Sens", "Swapped (LCY M)"]
        rows = [
            [
                p.get("devise", ""),
                _fmt(p.get("actif_fcy", 0)),
                _fmt(p.get("passif_fcy", 0)),
                _fmt(p.get("hors_bilan_fcy_net", 0)),
                _fmt(p.get("position_nette_fcy", 0)),
                p.get("sens", ""),
                _fmt(p.get("swapped_funds_lcy", 0) / 1e6),
            ]
            for p in positions
        ]
        _add_table_slide(prs, "Position FX par devise", headers, rows)


def _build_concentration_enriched_section(prs):
    """Section concentration par secteur et segment."""
    try:
        from apps.analytics.concentration_enriched import compute_concentration_enriched
        data = compute_concentration_enriched(n_top=10)
    except Exception as e:
        _add_kpi_slide(prs, "Concentration enrichie", [{"label": "Erreur", "value": str(e)}])
        return

    for dim_key, dim_label in [("by_secteur", "Secteur"), ("by_segment", "Segment"), ("by_business_unit", "Business Unit")]:
        dim = data.get(dim_key, {})
        if "error" in dim:
            continue
        hhi = dim.get("hhi", 0)
        status = dim.get("hhi_status", "")
        top_n = dim.get("top_n", [])
        dim_field = dim.get("dimension", dim_key.replace("by_", ""))

        _add_kpi_slide(prs, f"Concentration par {dim_label}", [
            {"label": "HHI", "value": f"{hhi:.0f}", "comment": status},
            {"label": "Nb catégories", "value": str(dim.get("nb_categories", 0))},
            {"label": "Top 3 share", "value": f"{dim.get('top3_share_pct', 0):.1f}%"},
            {"label": "Total", "value": _fmt(dim.get("total_global", 0) / 1e6) + " M"},
        ])

        if top_n:
            headers = ["Rang", dim_label, "Montant (M)", "Part (%)", "Hors-bilan (M)"]
            rows = [
                [
                    str(r.get("rank", i + 1)),
                    str(r.get(dim_field, "")),
                    _fmt(r.get("total", 0) / 1e6),
                    f"{r.get('share_pct', 0):.1f}%",
                    _fmt(r.get("off_balance", 0) / 1e6),
                ]
                for i, r in enumerate(top_n)
            ]
            _add_table_slide(prs, f"Top 10 par {dim_label}", headers, rows)
