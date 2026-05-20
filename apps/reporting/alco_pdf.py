"""
Génération du rapport ALCO en PDF (impression contrôlée par l'application).

Utilise WeasyPrint pour produire un PDF stylé à partir d'un template HTML.
Inclut :
- Page de couverture avec scenario, dates.
- Matrice de synthèse complète par bucket.
- Graphes SVG inline (gap par bucket, profil cumulatif).
- Commentaires ALCO et DG.
- Pied de page : « Confidentiel — exemplaire de <nom> — <heure> ».

Aucune dépendance Chart.js : les graphes SVG sont générés directement en Python
pour rester complètement maîtrisés côté serveur.
"""
from __future__ import annotations

import base64
import html
import io
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Iterable

from weasyprint import HTML, CSS

from apps.engine.lcr import compute_lcr_all
from apps.engine.synthesis import compute_synthesis
from apps.parameters.models import Parameter


# ===========================================================================
# Définitions partagées avec la page React AlcoReport
# ===========================================================================
ROW_GROUPS = [
    ("Actifs maturités contractuelles", "asset",
     ["credit", "bta", "ota", "emprunt_obl", "pret_ter_cor", "inter_blanc", "pret_cor", "pret_titre"]),
    ("Actifs maturités comportementales", "asset",
     ["decouvert", "beac", "billet"]),
    ("Dépenses maturités contractuelles", "liability",
     ["pension_livree", "emprunt_inter_banc", "depot_terme", "emprunt_instit_etran",
      "bon", "avance_beac", "emprunt_titre"]),
    ("Dépenses maturités comportementales", "liability",
     ["compte_371", "compte_372", "compte_373", "compte_vue_cor"]),
]

TYPE_LABELS = {
    "credit": "Crédits CT MT LT", "bta": "BTA", "ota": "OTA",
    "emprunt_obl": "Emprunts obligataires",
    "pret_ter_cor": "Prêts à terme des correspondants",
    "inter_blanc": "Prêts interbancaires à blanc",
    "pret_cor": "Prêts aux correspondants", "pret_titre": "Prêts titres",
    "decouvert": "Découverts", "beac": "Compte BEAC", "billet": "Billets et pièces",
    "pension_livree": "Pensions livrées",
    "emprunt_inter_banc": "Emprunts interbancaires",
    "depot_terme": "Dépôts à terme",
    "emprunt_instit_etran": "Emprunts inst. étrangers",
    "bon": "Bons de caisse", "avance_beac": "Avances BEAC",
    "emprunt_titre": "Emprunts titres",
    "compte_371": "Comptes 371", "compte_372": "Comptes 372",
    "compte_373": "Comptes 373", "compte_vue_cor": "Comptes vue correspondants",
}

SCENARIO_TITLES = {
    "base": "Cas de base",
    "modere": "Cas modéré",
    "severe": "Cas sévère",
}

COMMENT_FIELDS = {
    "base": ("commalcobase", "commdgbase"),
    "modere": ("commalcomodere", "commdgmodere"),
    "severe": ("commalcosevere", "commdgsevere"),
}


def _logo_watermark_data_uri() -> str:
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


def _client_brand_html(param: Parameter) -> str:
    bank_name = (param.bankName or "").strip()
    bank_logo = ""
    if param.bankLogo:
        try:
            bank_logo = _file_data_uri(param.bankLogo.path)
        except Exception:
            bank_logo = ""
    if not bank_name and not bank_logo:
        return ""
    logo = f'<img src="{bank_logo}" alt="" />' if bank_logo else ""
    name = f'<span>{html.escape(bank_name)}</span>' if bank_name else ""
    return f'<div class="client-brand">{logo}{name}</div>'


def _fmt(n: float) -> str:
    if n == 0:
        return "—"
    s = f"{n:,.2f}".replace(",", " ").replace(".", ",")
    return s


def _short_fmt(n: float) -> str:
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".", ",")
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".", ",")
    return f"{n:.0f}"


def _chart_ticks(vmin: float, vmax: float, steps: int = 4) -> list[float]:
    if vmax == vmin:
        vmax += 1
        vmin -= 1
    return [vmin + (vmax - vmin) * i / steps for i in range(steps + 1)]


# ===========================================================================
# Génération de SVG charts inline (sans matplotlib)
# ===========================================================================
def _svg_bar_chart(values: list[float], labels: list[str],
                   width: int = 1120, height: int = 390,
                   title: str = "Gap par bucket (M FCFA)") -> str:
    """Rend un histogramme simple en SVG inline. Les barres positives sont
    en vert, les négatives en rouge."""
    if not values:
        return f'<div class="chart-empty">{title} — aucune donnée</div>'

    margin_l, margin_r, margin_t, margin_b = 76, 34, 64, 92
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    max_abs = max((abs(v) for v in values), default=1) or 1
    vmin, vmax = -max_abs, max_abs
    bar_w = plot_w / max(len(values), 1) * 0.8
    gap = plot_w / max(len(values), 1) * 0.2
    zero_y = margin_t + plot_h / 2

    bars = []
    for i, v in enumerate(values):
        x = margin_l + i * (bar_w + gap) + gap / 2
        height_bar = abs(v) / max_abs * (plot_h / 2)
        if v >= 0:
            y = zero_y - height_bar
            color = "#2E7D32"
        else:
            y = zero_y
            color = "#D32F2F"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{height_bar:.1f}" '
            f'fill="{color}" rx="2" />'
        )

    # X axis labels (rotated)
    x_labels = []
    for i, lab in enumerate(labels):
        x = margin_l + i * (bar_w + gap) + gap / 2 + bar_w / 2
        y = margin_t + plot_h + 28
        x_labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="end" '
            f'transform="rotate(-24 {x:.1f},{y:.1f})" '
            f'font-size="10" fill="#5F6E7A">{html.escape(lab)}</text>'
        )

    grid = []
    for tick in _chart_ticks(vmin, vmax):
        y = margin_t + (vmax - tick) / (vmax - vmin) * plot_h
        grid.append(
            f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width - margin_r}" y2="{y:.1f}" '
            f'stroke="#E1E8F0" stroke-width="1" />'
            f'<text x="{margin_l - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#5F6E7A">{html.escape(_short_fmt(tick))}</text>'
        )

    value_labels = []
    for i, v in enumerate(values):
        if v == 0:
            continue
        x = margin_l + i * (bar_w + gap) + gap / 2 + bar_w / 2
        height_bar = abs(v) / max_abs * (plot_h / 2)
        y = zero_y - height_bar - 6 if v >= 0 else zero_y + height_bar + 13
        value_labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="9" fill="#1F2937">{html.escape(_short_fmt(v))}</text>'
        )

    min_v = min(values)
    max_v = max(values)

    return f'''
<div class="chart-block">
  <div class="chart-title">{html.escape(title)}</div>
  <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" class="chart-svg">
    <text x="{margin_l}" y="22" font-size="10" fill="#5F6E7A">Min {html.escape(_short_fmt(min_v))} | Max {html.escape(_short_fmt(max_v))}</text>
    {''.join(grid)}
    <line x1="{margin_l}" y1="{zero_y:.1f}" x2="{width - margin_r}" y2="{zero_y:.1f}"
          stroke="#BFBFBF" stroke-width="0.7" />
    {''.join(bars)}
    {''.join(value_labels)}
    {''.join(x_labels)}
  </svg>
</div>'''


def _svg_line_chart(series: list[tuple[str, list[float], str]], labels: list[str],
                    width: int = 1120, height: int = 390,
                    title: str = "Profil cumulatif (M FCFA)") -> str:
    """Plusieurs courbes sur le même graphe : series = [(label, values, color), ...]."""
    if not series or not series[0][1]:
        return f'<div class="chart-empty">{title} — aucune donnée</div>'

    all_vals = [v for _, vals, _ in series for v in vals]
    if not all_vals:
        return f'<div class="chart-empty">{title} — aucune donnée</div>'

    margin_l, margin_r, margin_t, margin_b = 76, 190, 64, 92
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    vmax = max(all_vals)
    vmin = min(all_vals)
    if vmax == vmin:
        vmin -= 1
        vmax += 1
    n = len(labels)
    step = plot_w / max(n - 1, 1)

    def to_y(v: float) -> float:
        return margin_t + (vmax - v) / (vmax - vmin) * plot_h

    paths = []
    legend_items = []
    for li, (label, values, color) in enumerate(series):
        if not values:
            continue
        d_parts = []
        for i, v in enumerate(values):
            x = margin_l + i * step
            y = to_y(v)
            d_parts.append(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}")
        paths.append(
            f'<path d="{" ".join(d_parts)}" fill="none" stroke="{color}" stroke-width="2" />'
        )
        # Points
        for i, v in enumerate(values):
            x = margin_l + i * step
            y = to_y(v)
            paths.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}" />')
        # Legend
        ly = margin_t + 14 + li * 16
        legend_items.append(
            f'<rect x="{width - 120}" y="{ly - 8:.1f}" width="12" height="3" fill="{color}" />'
            f'<text x="{width - 102}" y="{ly:.1f}" font-size="10" fill="#1F1F1F">{html.escape(label)}</text>'
        )

    # Axe zéro
    zero_line = ""
    if vmin <= 0 <= vmax:
        y0 = to_y(0)
        zero_line = (f'<line x1="{margin_l}" y1="{y0:.1f}" x2="{width - margin_r}" y2="{y0:.1f}" '
                     f'stroke="#BFBFBF" stroke-width="0.7" />')

    # X labels
    x_labels = []
    for i, lab in enumerate(labels):
        x = margin_l + i * step
        y = margin_t + plot_h + 12
        x_labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="end" '
            f'transform="rotate(-24 {x:.1f},{y:.1f})" '
            f'font-size="10" fill="#5F6E7A">{html.escape(lab)}</text>'
        )

    grid = []
    for tick in _chart_ticks(vmin, vmax):
        y = to_y(tick)
        grid.append(
            f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width - margin_r}" y2="{y:.1f}" '
            f'stroke="#E1E8F0" stroke-width="1" />'
            f'<text x="{margin_l - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#5F6E7A">{html.escape(_short_fmt(tick))}</text>'
        )

    end_labels = []
    for label, values, color in series:
        if not values:
            continue
        x = margin_l + (len(values) - 1) * step + 6
        y = to_y(values[-1])
        end_labels.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="9" fill="{color}" font-weight="700">{html.escape(_short_fmt(values[-1]))}</text>'
        )

    return f'''
<div class="chart-block">
  <div class="chart-title">{html.escape(title)}</div>
  <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" class="chart-svg">
    <text x="{margin_l}" y="22" font-size="10" fill="#5F6E7A">Min {html.escape(_short_fmt(vmin))} | Max {html.escape(_short_fmt(vmax))}</text>
    {''.join(grid)}
    {zero_line}
    {''.join(paths)}
    {''.join(end_labels)}
    {''.join(x_labels)}
    {''.join(legend_items)}
  </svg>
</div>'''


# ===========================================================================
# Builder HTML
# ===========================================================================
def _build_html(scenario: str, *, user_label: str, generated_at: datetime) -> str:
    if scenario not in SCENARIO_TITLES:
        raise ValueError(f"Scénario inconnu : {scenario}")

    synth = compute_synthesis(scenario)
    param = Parameter.get_solo()
    lcr_all = compute_lcr_all()
    lcr = lcr_all.get(scenario, {})

    ref_date = synth["reference_date"][:10] if synth.get("reference_date") else "-"

    alco_field, dg_field = COMMENT_FIELDS[scenario]
    comm_alco = getattr(param, alco_field, "") or "(aucun commentaire)"
    comm_dg = getattr(param, dg_field, "") or "(aucun commentaire)"

    # ---- Tableau matrice ----
    buckets = synth["buckets"]
    rows_html = []
    for title, tone, types in ROW_GROUPS:
        rows_html.append(
            f'<tr><td class="group-{tone}" colspan="{len(buckets) + 2}">{html.escape(title)}</td></tr>'
        )
        for t in types:
            row = synth["lignes"].get(t)
            if not row:
                continue
            cells = [f'<td class="total">{_fmt(row[0])}</td>']
            for v in row[1:]:
                cells.append(f'<td>{_fmt(v)}</td>')
            rows_html.append(
                f'<tr><th>{html.escape(TYPE_LABELS.get(t, t))}</th>{"".join(cells)}</tr>'
            )

    # Totaux
    total_assets_sum = sum(synth["total_assets"])
    total_dep_sum = sum(synth["total_depense"])
    total_net_sum = sum(synth["net_funding"])
    min_cumulative = min(synth["cumulative_net_funding"]) if synth["cumulative_net_funding"] else 0
    negative_buckets = len([v for v in synth["net_funding"] if v < 0])
    logo_uri = _logo_watermark_data_uri()
    logo_watermark = f'<img class="pdf-logo-watermark" src="{logo_uri}" alt="" />' if logo_uri else ""
    client_brand = _client_brand_html(param)
    footer_text = (
        f"{param.bankName.strip()} — exemplaire de {user_label} — {generated_at.strftime('%d/%m/%Y %H:%M')}"
        if param.bankName.strip()
        else f"Exemplaire de {user_label} — {generated_at.strftime('%d/%m/%Y %H:%M')}"
    )

    rows_html.append(
        '<tr class="total-row total-assets"><th>Total Actifs</th>'
        f'<td class="total">{_fmt(total_assets_sum)}</td>'
        + ''.join(f'<td>{_fmt(v)}</td>' for v in synth["total_assets"]) +
        '</tr>'
    )
    rows_html.append(
        '<tr class="total-row total-dep"><th>Total Dépenses</th>'
        f'<td class="total">{_fmt(total_dep_sum)}</td>'
        + ''.join(f'<td>{_fmt(v)}</td>' for v in synth["total_depense"]) +
        '</tr>'
    )
    rows_html.append(
        '<tr class="total-row total-net"><th>Net GAP</th>'
        f'<td class="total">{_fmt(total_net_sum)}</td>'
        + ''.join(
            f'<td class="{"neg" if v < 0 else "pos"}">{_fmt(v)}</td>'
            for v in synth["net_funding"]
        ) +
        '</tr>'
    )
    rows_html.append(
        '<tr class="total-row total-cum"><th>Cumulatif GAP</th><td></td>'
        + ''.join(
            f'<td class="{"neg" if v < 0 else "pos"}">{_fmt(v)}</td>'
            for v in synth["cumulative_net_funding"]
        ) +
        '</tr>'
    )

    bucket_headers = ''.join(f'<th class="bucket">{html.escape(b)}</th>' for b in buckets)

    # ---- Charts SVG ----
    gap_chart = _svg_bar_chart(
        synth["net_funding"], buckets,
        title="Gap de liquidité par bucket (M FCFA)",
    )
    profile_chart = _svg_line_chart(
        [
            ("Cumul net funding", synth["cumulative_net_funding"], "#002E5F"),
            ("Cumul actifs", synth["cumulative_assets"], "#2E7D32"),
            ("Cumul dépenses", synth["cumulative_depense"], "#D32F2F"),
        ],
        buckets,
        title="Profil de funding cumulatif (M FCFA)",
    )

    # ---- LCR ----
    lcr_pct = lcr.get("lcr_pct") if isinstance(lcr, dict) else None
    lcr_compliant = lcr.get("compliant", False) if isinstance(lcr, dict) else False
    lcr_chip = (
        f'<span class="lcr-chip {"ok" if lcr_compliant else "ko"}">'
        f'LCR {scenario.upper()} : {lcr_pct:.1f} %</span>'
        if lcr_pct is not None
        else '<span class="lcr-chip">LCR : N/D</span>'
    )

    # ---- HTML final ----
    return f'''<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Rapport ALCO — {html.escape(SCENARIO_TITLES[scenario])}</title>
<style>
@page {{
  size: A4 landscape;
  margin: 14mm 12mm 18mm 12mm;
  @bottom-left {{
    content: "{html.escape(footer_text)}";
    font-family: 'Helvetica', sans-serif;
    font-size: 8pt;
    color: #595959;
  }}
  @bottom-right {{
    content: "Page " counter(page) " / " counter(pages);
    font-family: 'Helvetica', sans-serif;
    font-size: 8pt;
    color: #595959;
  }}
}}

body {{
  font-family: 'Helvetica', 'Arial', sans-serif;
  color: #1F1F1F;
  font-size: 10pt;
  margin: 0;
  position: relative;
}}

main {{ position: relative; z-index: 1; }}
.pdf-logo-watermark {{
  position: fixed;
  left: 50%;
  top: 50%;
  width: 135mm;
  transform: translate(-50%, -50%);
  opacity: 0.035;
  z-index: 0;
}}

/* Cover */
.cover {{
  page-break-after: always;
  padding-top: 0;
}}
.cover-hero {{
  display: table;
  width: 100%;
  box-sizing: border-box;
  min-height: 150pt;
  padding: 24pt 28pt;
  border-radius: 14pt;
  background: linear-gradient(135deg, #03152B 0%, #002E5F 58%, #735247 100%);
  color: #FFFFFF;
}}
.cover-hero > div {{
  display: table-cell;
  vertical-align: middle;
}}
.cover-hero .eyebrow {{
  font-size: 11pt;
  letter-spacing: 1.2pt;
  color: #FFB199;
  font-weight: 900;
  text-transform: uppercase;
}}
.cover-hero h1 {{
  font-size: 34pt;
  color: #FFFFFF;
  margin: 8pt 0 4pt;
  font-weight: 900;
  line-height: 1;
}}
.cover-hero h2 {{
  font-size: 19pt;
  color: rgba(255,255,255,0.82);
  margin: 0 0 12pt;
  font-weight: 800;
}}
.cover-hero p {{
  margin: 0;
  max-width: 560pt;
  color: rgba(255,255,255,0.74);
  font-size: 11pt;
}}
.hero-meta {{
  width: 160pt;
  padding: 12pt;
  border: 1pt solid rgba(255,255,255,0.20);
  border-radius: 8pt;
  background: rgba(255,255,255,0.10);
  text-align: right;
  font-size: 20pt;
  font-weight: 900;
}}
.client-brand {{
  margin-bottom: 10pt;
  padding-bottom: 9pt;
  border-bottom: 1pt solid rgba(255,255,255,0.16);
  color: #FFFFFF;
  font-size: 12pt;
  font-weight: 900;
}}
.client-brand img {{
  display: block;
  max-width: 120pt;
  max-height: 42pt;
  object-fit: contain;
  margin: 0 0 6pt auto;
}}
.client-brand span {{
  display: block;
}}
.hero-meta small {{
  display: block;
  margin-top: 5pt;
  color: rgba(255,255,255,0.68);
  font-size: 8pt;
  font-weight: 700;
}}
.cover-kpis {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 7pt 0;
  margin: 14pt -7pt;
}}
.cover-kpis .kpi {{
  display: table-cell;
  padding: 11pt 10pt;
  border: 1pt solid #DDE7F1;
  border-radius: 8pt;
  background: #FFFFFF;
  box-shadow: 0 8pt 20pt rgba(0, 27, 56, 0.06);
}}
.cover-kpis span {{
  display: block;
  color: #5D6B7D;
  font-size: 7.8pt;
  font-weight: 900;
  text-transform: uppercase;
}}
.cover-kpis b {{
  display: block;
  margin-top: 5pt;
  color: #002E5F;
  font-size: 17pt;
  line-height: 1;
}}
.cover-kpis small {{
  display: block;
  margin-top: 4pt;
  color: #748094;
  font-size: 8pt;
}}
.cover-footer {{
  display: table;
  width: 100%;
  margin-top: 16pt;
  padding: 12pt 14pt;
  border: 1px solid rgba(0, 46, 95, 0.18);
  border-radius: 8pt;
  background: rgba(255,255,255,0.88);
}}
.cover-footer > div,
.cover-footer > table {{
  display: table-cell;
  vertical-align: middle;
}}
.cover-footer table {{
  width: 330pt;
  border-collapse: collapse;
}}
.cover-footer td {{ padding: 4pt 14pt 4pt 0; font-size: 10pt; }}
.cover-footer td.lbl {{ font-weight: 800; color: #002E5F; }}
.cover .lcr-chip.ok {{
  background: #2E7D32; color: #FFF; padding: 6pt 14pt; border-radius: 999pt;
  font-weight: 800; font-size: 12pt;
}}
.cover .lcr-chip.ko {{
  background: #D32F2F; color: #FFF; padding: 6pt 14pt; border-radius: 999pt;
  font-weight: 800; font-size: 12pt;
}}
.cover .lcr-chip {{
  background: #735247; color: #FFF; padding: 6pt 14pt; border-radius: 999pt;
  font-weight: 800; font-size: 12pt;
}}

/* Section title */
.section {{
  page-break-before: always;
}}
.section-title {{
  color: #002E5F;
  font-size: 16pt;
  font-weight: 850;
  border-bottom: 2pt solid #002E5F;
  padding-bottom: 4pt;
  margin: 0 0 10pt 0;
}}
.section-subtitle {{
  color: #5F6E7A;
  font-size: 9pt;
  margin: -6pt 0 12pt 0;
}}

/* Synthèse table */
table.synthesis {{
  border-collapse: collapse;
  width: 100%;
  font-size: 8.5pt;
  table-layout: fixed;
}}
table.synthesis th {{
  text-align: left;
  background: #FAFBFC;
  padding: 4pt 6pt;
  font-size: 8.5pt;
  border: 0.5pt solid #BFBFBF;
}}
table.synthesis th.bucket {{ font-size: 7.5pt; text-align: center; }}
table.synthesis td {{
  padding: 3pt 5pt;
  border: 0.5pt solid #DDD;
  text-align: right;
  font-size: 8.5pt;
}}
table.synthesis td.total {{
  background: rgba(238, 245, 252, 0.7);
  font-weight: 700;
}}
table.synthesis td.group-asset {{
  background: rgba(0, 46, 95, 0.92);
  color: #FFF;
  font-weight: 800;
  text-align: left;
  letter-spacing: 0.4pt;
}}
table.synthesis td.group-liability {{
  background: rgba(115, 82, 71, 0.92);
  color: #FFF;
  font-weight: 800;
  text-align: left;
  letter-spacing: 0.4pt;
}}
table.synthesis tr.total-row.total-assets td,
table.synthesis tr.total-row.total-assets th {{
  background: rgba(46, 125, 50, 0.13); font-weight: 800;
}}
table.synthesis tr.total-row.total-dep td,
table.synthesis tr.total-row.total-dep th {{
  background: rgba(245, 158, 11, 0.16); font-weight: 800;
}}
table.synthesis tr.total-row.total-net td,
table.synthesis tr.total-row.total-net th,
table.synthesis tr.total-row.total-cum td,
table.synthesis tr.total-row.total-cum th {{
  background: rgba(0, 46, 95, 0.10); font-weight: 850;
}}
table.synthesis td.neg {{ color: #B71C1C; }}
table.synthesis td.pos {{ color: #1B5E20; }}

/* Charts */
.chart-block {{ margin: 16pt 0; page-break-inside: avoid; }}
.chart-title {{
  color: #002E5F; font-weight: 800; font-size: 11pt; margin-bottom: 6pt;
}}
.chart-svg {{ width: 100%; height: 330pt; }}

/* Comments */
.comments {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14pt;
  margin-top: 8pt;
}}
.comments .box {{
  border: 0.7pt solid rgba(0, 46, 95, 0.20);
  border-radius: 3pt;
  padding: 12pt;
  background: rgba(248, 251, 254, 0.75);
}}
.comments .box h3 {{
  color: #002E5F; font-size: 11pt; margin: 0 0 8pt 0; font-weight: 800;
  border-left: 3pt solid #FF4B18; padding-left: 8pt;
}}
.comments .body {{ font-size: 10pt; line-height: 1.4; white-space: pre-wrap; }}

</style>
</head>
<body>
{logo_watermark}
<main>

  <!-- COVER -->
  <section class="cover">
    <div class="cover-hero">
      <div>
        <div class="eyebrow">Rapport ALCO</div>
        <h1>Synthèse de liquidité</h1>
        <h2>{html.escape(SCENARIO_TITLES[scenario])}</h2>
        <p>Lecture Comité Actif-Passif : matrice de liquidité, gap, profil cumulatif, LCR et commentaires.</p>
      </div>
      <div class="hero-meta">
        {client_brand}
        <div>{scenario.upper()}</div>
        <small>Date données : {ref_date}</small>
      </div>
    </div>
    <div class="cover-kpis">
      <div class="kpi"><span>Total Actifs</span><b>{_short_fmt(total_assets_sum)}</b><small>M FCFA</small></div>
      <div class="kpi"><span>Total Dépenses</span><b>{_short_fmt(total_dep_sum)}</b><small>M FCFA</small></div>
      <div class="kpi"><span>Net Funding</span><b>{_short_fmt(total_net_sum)}</b><small>M FCFA</small></div>
      <div class="kpi"><span>Point bas cumulé</span><b>{_short_fmt(min_cumulative)}</b><small>M FCFA</small></div>
      <div class="kpi"><span>Buckets négatifs</span><b>{negative_buckets}</b><small>sur {len(buckets)}</small></div>
    </div>
    <div class="cover-footer">
      <div>{lcr_chip}</div>
      <table>
        <tr><td class="lbl">Date du rapport</td><td>{generated_at.strftime("%d/%m/%Y %H:%M")}</td></tr>
        <tr><td class="lbl">Édité par</td><td>{html.escape(user_label)}</td></tr>
      </table>
    </div>
  </section>

  <!-- SYNTHÈSE -->
  <section class="section">
    <h2 class="section-title">Matrice de synthèse</h2>
    <div class="section-subtitle">Décomposition par bucket de maturité — Montants en millions FCFA</div>
    <table class="synthesis">
      <thead>
        <tr>
          <th style="width: 22%;">Ligne</th>
          <th style="width: 8%;">Total</th>
          {bucket_headers}
        </tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
  </section>

  <!-- GRAPHES -->
  <section class="section">
    <h2 class="section-title">Graphes</h2>
    <div class="section-subtitle">Lecture visuelle pour la séance ALCO</div>
    {gap_chart}
    {profile_chart}
  </section>

  <!-- COMMENTAIRES -->
  <section class="section">
    <h2 class="section-title">Commentaires</h2>
    <div class="section-subtitle">Lecture du gap, points de tension, leviers d'action.</div>
    <div class="comments">
      <div class="box">
        <h3>Commentaires ALCO</h3>
        <div class="body">{html.escape(comm_alco)}</div>
      </div>
      <div class="box">
        <h3>Commentaires Direction Générale</h3>
        <div class="body">{html.escape(comm_dg)}</div>
      </div>
    </div>
  </section>

</main>
</body></html>'''


def build_alco_pdf(scenario: str, user_label: str) -> bytes:
    """Génère le PDF du rapport ALCO pour un scénario donné.
    Retourne les bytes du PDF prêts à servir.
    """
    html_str = _build_html(scenario, user_label=user_label, generated_at=datetime.now())
    pdf_bytes = HTML(string=html_str).write_pdf()
    return pdf_bytes
