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


PRIMARY = RGBColor(0x1F, 0x38, 0x64)
ACCENT = RGBColor(0x2E, 0x74, 0xB5)
LIGHT = RGBColor(0xF5, 0xF7, 0xFA)


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
    "title", "synthese", "lcr", "rate_gap", "nii", "eve",
    "concentration", "multicurrency", "commentary",
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

    if "commentary" in sections:
        body = "\n\n".join(filter(None, [
            "ALCO — Cas de base : " + (param.commalcobase or ""),
            "ALCO — Cas modéré : " + (param.commalcomodere or ""),
            "ALCO — Cas sévère : " + (param.commalcosevere or ""),
            "DG — Cas de base : " + (param.commdgbase or ""),
            "DG — Cas modéré : " + (param.commdgmodere or ""),
            "DG — Cas sévère : " + (param.commdgsevere or ""),
        ]))
        _add_commentary_slide(prs, "Commentaires ALCO et Direction Générale", body)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
