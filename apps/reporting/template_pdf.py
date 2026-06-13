"""PDF multi-sections à partir d'un ReportTemplate sauvegardé."""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from weasyprint import HTML

from apps.engine.lcr import compute_lcr_all
from apps.engine.rate_gap import compute_rate_gap
from apps.engine.scenario_analysis import compute_scenario_analysis
from apps.engine.synthesis import build_charts_payload, compute_synthesis
from apps.analytics.concentration import compute_concentration
from apps.analytics.eve import compute_eve_sensitivity
from apps.analytics.eve_enriched import compute_eve_enriched
from apps.analytics.nii import compute_nii_sensitivity
from apps.multicurrency.services import compute_positions_by_currency
from apps.parameters.models import Parameter

from .models import ReportAnnotation, ReportTemplate
from .report_pdf import (
    _bank_branding,
    _client_brand_html,
    _logo_watermark_data_uri,
    _public_user_label,
    _render_model_versioning_pdf,
    _render_charts_pdf,
    _render_concentration_pdf,
    _render_eve_pdf,
    _render_lcr_pdf,
    _render_multicurrency_pdf,
    _render_nii_pdf,
    _render_rate_gap_pdf,
    _render_scenario_analysis_pdf,
    _render_synthesis_pdf,
)


SECTION_LABELS: dict[str, str] = {
    "title": "Page de titre",
    "commentary": "Commentaires ALCO et DG",
    "model_versioning": "Version modèle, hypothèses et scénarios",
    "balance_sheet": "Bilan complet FCY/LCY/Consolidé",
    "fx_position": "Position FX nette",
    "nim_profitability": "NIM, WAR, COF et profitabilité",
    "synthese": "Synthèse de gap de liquidité",
    "mco": "Maximum Cumulative Outflow",
    "scenario_analysis": "Scenario Analysis",
    "lcr": "Liquidity Coverage Ratio",
    "rate_gap": "Gap de taux",
    "rate_gap_by_type": "Gap de taux par type",
    "nii": "NII Sensitivity",
    "eve": "EVE Sensitivity",
    "eve_enriched": "EVE enrichi",
    "concentration": "Concentration",
    "concentration_enriched": "Concentration par secteur/segment",
    "multicurrency": "Multi-devises",
    "ftp": "Funds Transfer Pricing",
}

ANNOTATION_SCOPES: tuple[tuple[str, str, str], ...] = (
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


def _section_shell(key: str, body: str) -> str:
    title = SECTION_LABELS.get(key, key)
    return f"""
    <section class="template-section">
      <div class="template-section-heading">
        <span>SECTION</span>
        <h2>{html.escape(title)}</h2>
      </div>
      {body}
    </section>
    """


def _placeholder(key: str, note: str) -> str:
    return _section_shell(
        key,
        f"""
        <div class="template-note">
          <strong>Section prévue dans le template.</strong>
          <p>{html.escape(note)}</p>
        </div>
        """,
    )


def _commentary_section() -> str:
    param = Parameter.get_solo()
    rows = [
        ("ALCO - Cas de base", param.commalcobase or ""),
        ("ALCO - Cas modéré", param.commalcomodere or ""),
        ("ALCO - Cas sévère", param.commalcosevere or ""),
        ("DG - Cas de base", param.commdgbase or ""),
        ("DG - Cas modéré", param.commdgmodere or ""),
        ("DG - Cas sévère", param.commdgsevere or ""),
    ]
    for section, scenario, label in ANNOTATION_SCOPES:
        annotation = (
            ReportAnnotation.objects
            .filter(section=section, scenario=scenario)
            .order_by("-created_at")
            .first()
        )
        rows.append((label, annotation.body if annotation else ""))
    body = [
        "<table class='template-commentary'><thead><tr><th>Bloc</th><th>Commentaire</th></tr></thead><tbody>"
    ]
    for label, text in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{html.escape(text or 'Aucun commentaire saisi.')}</td>"
            "</tr>"
        )
    body.append("</tbody></table>")
    return _section_shell("commentary", "".join(body))


def _render_section(key: str, params: dict[str, Any]) -> str:
    if key == "synthese":
        scenario = str(params.get("scenario") or "base")
        if scenario not in ("base", "modere", "severe"):
            scenario = "base"
        return _section_shell(key, _render_synthesis_pdf(compute_synthesis(scenario)))
    if key == "charts":
        return _section_shell(key, _render_charts_pdf(build_charts_payload()))
    if key == "lcr":
        scenario = str(params.get("scenario") or "base")
        if scenario not in ("base", "modere", "severe"):
            scenario = "base"
        return _section_shell(key, _render_lcr_pdf(compute_lcr_all()[scenario]))
    if key in {"rate_gap", "rate_gap_by_type"}:
        return _section_shell(key, _render_rate_gap_pdf(compute_rate_gap()))
    if key == "nii":
        horizon = int(params.get("horizon_days") or 365)
        return _section_shell(key, _render_nii_pdf(compute_nii_sensitivity(horizon_days=horizon)))
    if key in {"eve", "eve_enriched"}:
        payload = compute_eve_sensitivity()
        try:
            payload["enriched"] = compute_eve_enriched()
        except Exception as exc:  # noqa: BLE001
            payload["enriched_error"] = str(exc)
        return _section_shell(key, _render_eve_pdf(payload))
    if key == "scenario_analysis" or key == "mco":
        mode = str(params.get("balance_sheet_mode") or "static").lower()
        if mode not in ("static", "dynamic"):
            mode = "static"
        return _section_shell(key, _render_scenario_analysis_pdf(compute_scenario_analysis(mode)))
    if key in {"concentration", "concentration_enriched"}:
        n = int(params.get("n") or 20)
        return _section_shell(key, _render_concentration_pdf(compute_concentration(n=n)))
    if key in {"multicurrency", "balance_sheet", "fx_position"}:
        return _section_shell(key, _render_multicurrency_pdf(compute_positions_by_currency()))
    if key == "commentary":
        return _commentary_section()
    if key == "model_versioning":
        return _section_shell(key, _render_model_versioning_pdf("template", params))
    if key == "nim_profitability":
        return _placeholder(
            key,
            "La section NIM/WAR/COF est disponible dans le support PPTX ALCO. "
            "Son rendu PDF détaillé pourra être branché sur les métriques de profitabilité validées.",
        )
    if key == "ftp":
        return _placeholder(
            key,
            "La section FTP est réservée dans le template. Elle sera alimentée lorsque le module FTP sera calibré.",
        )
    if key == "title":
        return ""
    return _placeholder(key, "Section inconnue ou non encore connectée au moteur PDF.")


def build_template_pdf(template: ReportTemplate, params: dict[str, Any], user_label: str) -> bytes:
    generated_at = datetime.now()
    bank_name, bank_logo = _bank_branding()
    public_user_label = _public_user_label(user_label)
    footer_text = (
        f"{bank_name} - {public_user_label} - {generated_at:%d/%m/%Y %H:%M}"
        if bank_name
        else f"{public_user_label} - {generated_at:%d/%m/%Y %H:%M}"
    )
    logo_uri = _logo_watermark_data_uri()
    logo_watermark = f'<img class="pdf-logo-watermark" src="{logo_uri}" alt="" />' if logo_uri else ""
    client_brand = _client_brand_html(bank_name, bank_logo)
    sections = template.sections or []
    body = "\n".join(_render_section(section, params) for section in sections)

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
.pdf-content {{ position: relative; z-index: 1; }}
.cover {{
  min-height: 82px;
  margin-bottom: 14px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #fff;
}}
.cover-top {{ display: table; width: 100%; }}
.client-brand {{
  display: table-cell;
  vertical-align: middle;
  text-align: left;
  color: #fff;
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
  color: rgba(255,255,255,0.72);
  font-size: 10px;
}}
.cover h1 {{
  margin: 12px 0 5px;
  color: #fff;
  font-size: 25px;
  line-height: 1;
}}
.cover p {{
  margin: 0;
  max-width: 760px;
  color: rgba(255,255,255,0.74);
}}
.template-section {{
  page-break-before: always;
  position: relative;
  z-index: 1;
}}
.template-section:first-of-type {{ page-break-before: auto; }}
.template-section-heading {{
  margin-bottom: 10px;
  padding: 10px 12px;
  border-left: 4px solid #FF4B18;
  border-radius: 10px;
  background: #F7FAFD;
}}
.template-section-heading span {{
  display: block;
  color: #FF4B18;
  font-size: 8px;
  font-weight: 900;
  letter-spacing: .5px;
}}
.template-section-heading h2 {{
  margin: 2px 0 0;
  color: #002E5F;
  font-size: 16px;
}}
.template-note {{
  padding: 18px;
  border: 1px solid #DDE7F1;
  border-radius: 12px;
  background: rgba(255,255,255,.95);
}}
.template-note strong {{ color: #002E5F; font-size: 13px; }}
.template-note p {{ color: #5D6B7D; }}
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
table {{
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 8px;
}}
th {{
  background: #EEF5FC;
  color: #002E5F;
  font-weight: 900;
}}
th, td {{
  border: 1px solid #D8E1EA;
  padding: 5px 6px;
  vertical-align: top;
}}
td.num, th.num {{ text-align: right; white-space: nowrap; }}
.kpi-grid, .chart-kpi-grid, .lcr-kpi-grid, .rate-kpi-grid,
.nii-summary, .nii-kpi-grid, .concentration-summary, .concentration-kpi-grid,
.mc-summary, .mc-kpi-grid {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 6px 0;
  margin: 0 -6px 10px;
}}
.kpi, .chart-kpi, .lcr-kpi, .rate-kpi, .nii-kpi,
.concentration-kpi, .mc-kpi,
.nii-summary > div, .concentration-summary > div, .mc-summary > div {{
  display: table-cell;
  padding: 9px 10px;
  border: 1px solid #DDE7F1;
  border-radius: 9px;
  background: #fff;
}}
.kpi-label, .nii-summary span, .concentration-summary span, .mc-summary span {{
  color: #5D6B7D;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}}
.kpi-value, .nii-summary strong, .concentration-summary strong, .mc-summary strong {{
  display: block;
  margin-top: 4px;
  color: #002E5F;
  font-size: 15px;
  font-weight: 900;
}}
.neg {{ color: #B42318; }}
.pos {{ color: #166534; }}
.muted {{ color: #8A94A6; }}
.chart-svg, .rate-chart-svg, .nii-chart-svg, .eve-chart-svg {{
  display: block;
  width: 100%;
  height: 58mm;
}}
.chart-card, .rate-chart-card, .nii-chart-card,
.matrix-block, .lcr-table-block, .rate-table-block, .nii-table-block,
.concentration-block, .mc-table-block, .mc-source-card, .mc-gap-block {{
  margin-bottom: 12px;
  padding: 8px;
  border: 1px solid #D8E1EA;
  border-radius: 12px;
  background: rgba(255,255,255,.96);
}}
.pdf-version-card {{
  margin-bottom: 12px;
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
.version-scenarios {{
  margin: 0;
  padding: 0 12px 12px;
  color: #5D6B7D;
  font-size: 9px;
}}
</style>
</head>
<body>
  {logo_watermark}
  <main class="pdf-content">
    <header class="cover">
      <div class="cover-top">
        {client_brand}
        <div class="report-meta">Généré le {generated_at:%d/%m/%Y à %H:%M} - Utilisateur : {html.escape(public_user_label)}</div>
      </div>
      <h1>{html.escape(template.label)}</h1>
      <p>{html.escape(template.description or "Rapport composé à partir d'un template utilisateur sauvegardé.")}</p>
    </header>
    {body}
  </main>
</body>
</html>"""
    return HTML(string=html_str).write_pdf()
