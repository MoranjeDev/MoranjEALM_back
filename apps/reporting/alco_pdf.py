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
from apps.engine.scenario_analysis import compute_scenario_analysis
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


def _public_user_label(user_label: str) -> str:
    """Nettoie le libellé utilisateur affiché dans les PDF client."""
    cleaned = (user_label or "").replace("MoranjEALM", "").strip(" -—")
    return cleaned or "Utilisateur"


def _safe_div(value: float, divisor: float) -> float:
    return (value / divisor) if divisor else 0.0


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


def _build_balance_sheet_html() -> tuple[str, dict[str, float]]:
    """Construit la section bilan officiel LCY/FCY/consolidé pour le PDF ALCO."""
    try:
        from apps.multicurrency.balance_sheet_currency import compute_balance_sheet_by_currency
        data = compute_balance_sheet_by_currency()
    except Exception as exc:  # noqa: BLE001
        return (
            f'''
  <section class="section">
    <h2 class="section-title">Bilan officiel</h2>
    <div class="notice error">Impossible de charger le bilan officiel : {html.escape(str(exc))}</div>
  </section>
''',
            {},
        )

    if data.get("error"):
        return (
            f'''
  <section class="section">
    <h2 class="section-title">Bilan officiel</h2>
    <div class="notice">Données non disponibles : {html.escape(str(data["error"]))}</div>
  </section>
''',
            {},
        )

    consolidated = data.get("consolidated", {})
    lcy = data.get("lcy_only", {})
    fcy = data.get("fcy_total", {})
    devises = data.get("devises", [])

    total_actif = float(consolidated.get("total_actif_lcy", 0) or 0)
    total_passif = float(consolidated.get("total_passif_lcy", 0) or 0)
    gap = float(consolidated.get("gap_lcy", 0) or 0)
    fcy_actif = float(fcy.get("actif_lcy_equivalent", 0) or 0)
    fcy_passif = float(fcy.get("passif_lcy_equivalent", 0) or 0)
    fcy_gap = float(fcy.get("gap_lcy", 0) or 0)
    lcy_actif = float(lcy.get("actif", 0) or 0)
    lcy_passif = float(lcy.get("passif", 0) or 0)
    fcy_share = _safe_div(fcy_actif + fcy_passif, total_actif + total_passif) * 100

    rows = []
    for row in devises:
        row_gap = float(row.get("gap_lcy", 0) or 0)
        lcy_tag = " <span class='tag'>LCY</span>" if row.get("is_base") else ""
        rows.append(f'''
        <tr>
          <td><b>{html.escape(str(row.get("devise", "")))}</b>{lcy_tag}</td>
          <td>{_fmt(float(row.get("actif_lcy_equivalent", 0) or 0) / 1e6)}</td>
          <td>{_fmt(float(row.get("passif_lcy_equivalent", 0) or 0) / 1e6)}</td>
          <td class="{'neg' if row_gap < 0 else 'pos'}">{_fmt(row_gap / 1e6)}</td>
          <td>{_fmt(float(row.get("actif_fcy", 0) or 0))}</td>
          <td>{_fmt(float(row.get("passif_fcy", 0) or 0))}</td>
          <td>{_fmt(float(row.get("fx_rate", 1) or 1))}</td>
        </tr>''')

    html_section = f'''
  <section class="section">
    <h2 class="section-title">Bilan officiel LCY / FCY / consolidé</h2>
    <div class="section-subtitle">Source de contrôle : lignes de bilan GL importées — montants consolidés en millions FCFA.</div>
    <div class="balance-kpis">
      <div><span>Total actif consolidé</span><b>{_short_fmt(total_actif / 1e6)}</b><small>M FCFA</small></div>
      <div><span>Total passif consolidé</span><b>{_short_fmt(total_passif / 1e6)}</b><small>M FCFA</small></div>
      <div><span>Gap bilan</span><b class="{'neg' if gap < 0 else 'pos'}">{_short_fmt(gap / 1e6)}</b><small>Actif - passif</small></div>
      <div><span>Part FCY</span><b>{_fmt(fcy_share)} %</b><small>Actif + passif</small></div>
    </div>
    <div class="balance-split">
      <div>
        <h3>Lecture LCY</h3>
        <p>Actif : <b>{_fmt(lcy_actif / 1e6)}</b> M FCFA</p>
        <p>Passif : <b>{_fmt(lcy_passif / 1e6)}</b> M FCFA</p>
        <p>Gap : <b class="{'neg' if (lcy_actif - lcy_passif) < 0 else 'pos'}">{_fmt((lcy_actif - lcy_passif) / 1e6)}</b> M FCFA</p>
      </div>
      <div>
        <h3>Lecture FCY convertie</h3>
        <p>Actif FCY : <b>{_fmt(fcy_actif / 1e6)}</b> M FCFA</p>
        <p>Passif FCY : <b>{_fmt(fcy_passif / 1e6)}</b> M FCFA</p>
        <p>Gap FCY : <b class="{'neg' if fcy_gap < 0 else 'pos'}">{_fmt(fcy_gap / 1e6)}</b> M FCFA</p>
      </div>
    </div>
    <table class="balance-table">
      <thead>
        <tr>
          <th>Devise</th>
          <th>Actif éq. LCY</th>
          <th>Passif éq. LCY</th>
          <th>Gap LCY</th>
          <th>Actif FCY</th>
          <th>Passif FCY</th>
          <th>FX</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>
'''
    return html_section, {
        "total_actif_lcy": total_actif,
        "total_passif_lcy": total_passif,
        "gap_lcy": gap,
        "fcy_share": fcy_share,
    }


def _build_rate_basis_html() -> str:
    """Construit une section ALCO courte sur le basis risk."""
    try:
        from apps.engine.rate_gap import compute_rate_gap
        data = compute_rate_gap()
    except Exception as exc:  # noqa: BLE001
        return f'''
  <section class="section">
    <h2 class="section-title">Gap de taux par type — Basis Risk</h2>
    <div class="notice error">Impossible de charger le basis risk : {html.escape(str(exc))}</div>
  </section>
'''

    alerts = data.get("basis_risk_summary") or []
    type_rows = []
    for bucket in (data.get("by_bucket_and_type") or {}).values():
        for row in (bucket.get("types") or {}).values():
            gap = float(row.get("gap", 0) or 0)
            spread = float(row.get("basis_risk", 0) or 0)
            type_rows.append(f'''
        <tr>
          <td>{html.escape(str(bucket.get("label") or "-"))}</td>
          <td>{html.escape(str(row.get("label") or "-"))}</td>
          <td>{_fmt(float(row.get("actif", 0) or 0) / 1e6)}</td>
          <td>{_fmt(float(row.get("passif", 0) or 0) / 1e6)}</td>
          <td class="{'neg' if gap < 0 else 'pos'}">{_fmt(gap / 1e6)}</td>
          <td>{_fmt(float(row.get("taux_actif", 0) or 0))} %</td>
          <td>{_fmt(float(row.get("taux_passif", 0) or 0))} %</td>
          <td class="{'neg' if spread < 0 else 'pos'}">{_fmt(spread)} pts</td>
        </tr>''')

    alert_html = (
        ''.join(
            f'''
        <div class="risk-alert {'high' if str(item.get("severity")) == "HIGH" else "medium"}">
          <b>{html.escape(str(item.get("label") or "-"))}</b>
          <span>{_fmt(float(item.get("max_basis_spread", 0) or 0))} pts — {html.escape(", ".join(item.get("types_present") or []))}</span>
        </div>'''
            for item in alerts
        )
        if alerts
        else '<div class="notice">Aucun basis risk significatif détecté sur les buckets alimentés.</div>'
    )

    return f'''
  <section class="section">
    <h2 class="section-title">Gap de taux par type — Basis Risk</h2>
    <div class="section-subtitle">Lecture par base de taux : fixe, variable, administré, indexé ou révisable.</div>
    <div class="risk-alerts">{alert_html}</div>
    <table class="risk-table">
      <thead>
        <tr>
          <th>Bucket</th><th>Type de taux</th><th>Actif</th><th>Passif</th><th>Gap</th><th>Taux actif</th><th>Taux passif</th><th>Spread</th>
        </tr>
      </thead>
      <tbody>{''.join(type_rows) if type_rows else '<tr><td colspan="8">Aucune donnée sensible aux taux.</td></tr>'}</tbody>
    </table>
  </section>
'''


def _build_eve_irrbb_html() -> str:
    """Construit une section ALCO sur les buckets sensibles EVE/IRRBB."""
    try:
        from apps.analytics.eve_enriched import compute_eve_enriched
        data = compute_eve_enriched()
    except Exception as exc:  # noqa: BLE001
        return f'''
  <section class="section">
    <h2 class="section-title">EVE enrichi — IRRBB</h2>
    <div class="notice error">Impossible de charger l'EVE enrichi : {html.escape(str(exc))}</div>
  </section>
'''

    scenarios = [
        (code, item.get("label") or code)
        for code, item in (data.get("scenarios") or {}).items()
        if code != "base"
    ]
    scenario_headers = ''.join(f'<th>{html.escape(str(label))}</th>' for _code, label in scenarios)
    rows = []
    for row in data.get("bucket_summary") or []:
        max_delta = float(row.get("max_delta_eve", 0) or 0)
        cells = [
            f'<td><b>{html.escape(str(row.get("label") or "-"))}</b></td>',
            f'<td class="{"neg" if max_delta < 0 else "pos"}">{_fmt(max_delta / 1e6)}</td>',
        ]
        deltas = row.get("delta_eve_by_scenario") or {}
        for code, _label in scenarios:
            value = float(deltas.get(code, 0) or 0)
            cells.append(f'<td class="{"neg" if value < 0 else "pos"}">{_fmt(value / 1e6)}</td>')
        cells.append(f'<td class="{"neg" if row.get("breach") else "pos"}">{"Breach" if row.get("breach") else "OK"}</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')

    breach_rows = []
    for row in data.get("breaches") or []:
        breach_rows.append(f'''
        <tr>
          <td>{html.escape(str(row.get("label") or "-"))}</td>
          <td>{html.escape(str(row.get("scenario_label") or row.get("scenario") or "-"))}</td>
          <td class="neg">{_fmt(float(row.get("delta_eve", 0) or 0) / 1e6)}</td>
          <td class="neg">{_fmt(float(row.get("pct_tier1", 0) or 0))} %</td>
          <td>{html.escape(str(row.get("severity") or "-"))}</td>
        </tr>''')

    breaches = (
        f'''
    <table class="risk-table compact">
      <thead><tr><th>Bucket</th><th>Scénario</th><th>Delta EVE</th><th>% Tier 1</th><th>Sévérité</th></tr></thead>
      <tbody>{''.join(breach_rows)}</tbody>
    </table>'''
        if breach_rows
        else '<div class="notice">Aucun bucket ne dépasse le seuil IRRBB paramétré.</div>'
    )

    return f'''
  <section class="section">
    <h2 class="section-title">EVE enrichi — IRRBB</h2>
    <div class="section-subtitle">Matrice Bucket × scénario — Montants en millions FCFA. Hors-bilan {'inclus' if data.get('off_balance_included') else 'exclu'}.</div>
    <table class="risk-table">
      <thead><tr><th>Bucket</th><th>Pire Δ EVE</th>{scenario_headers}<th>Statut</th></tr></thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan="9">Aucune donnée EVE enrichie.</td></tr>'}</tbody>
    </table>
    <h3 class="subsection-title">Breaches IRRBB</h3>
    {breaches}
  </section>
'''


def _build_scenario_analysis_html() -> str:
    """Construit la section Scenario Analysis du PDF ALCO."""
    try:
        data = compute_scenario_analysis("static")
    except Exception as exc:  # noqa: BLE001
        return f'''
  <section class="section">
    <h2 class="section-title">Scenario Analysis</h2>
    <div class="notice error">Impossible de calculer le Scenario Analysis : {html.escape(str(exc))}</div>
  </section>
'''

    scenarios = list(data.get("scenarios", []))
    interest = data.get("interest_rate", {})
    worst = min(scenarios, key=lambda row: float(row.get("min_cumulative_gap") or 0), default={})
    worst_nii = interest.get("worst_nii") or {}
    worst_eve = interest.get("worst_eve") or {}

    kpi_html = f'''
      <div><span>Point bas liquidité</span><b>{html.escape(_fmt(float(worst.get("min_cumulative_gap") or 0)))}</b><small>{html.escape(str(worst.get("label") or "-"))} - M FCFA</small></div>
      <div><span>MCO défavorable</span><b>{html.escape(_fmt(float(worst.get("mco") or 0)))}</b><small>{html.escape(str(worst.get("mco_label") or "-"))}</small></div>
      <div><span>Pire NII</span><b>{html.escape(_short_fmt(float(worst_nii.get("delta_nii") or 0) / 1e6))}</b><small>{html.escape(str(worst_nii.get("label") or "-"))} - M FCFA</small></div>
      <div><span>Pire EVE</span><b>{html.escape(_short_fmt(float(worst_eve.get("delta_eve") or 0) / 1e6))}</b><small>{html.escape(str(worst_eve.get("label") or "-"))} - M FCFA</small></div>
    '''

    rows = []
    for row in scenarios:
        lcr = row.get("lcr_pct")
        min_gap = float(row.get("min_cumulative_gap") or 0)
        mco = float(row.get("mco") or 0)
        delta = float(row.get("delta_min_cumulative_gap_vs_base") or 0)
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('label') or row.get('scenario') or '-'))}</td>"
            f"<td>{html.escape(_fmt(float(lcr)) + ' %' if lcr is not None else '—')}</td>"
            f'<td class="{"neg" if mco < 0 else "pos"}">{html.escape(_fmt(mco))}</td>'
            f'<td class="{"neg" if min_gap < 0 else "pos"}">{html.escape(_fmt(min_gap))}</td>'
            f'<td class="{"neg" if delta < 0 else "pos"}">{html.escape(_fmt(delta))}</td>'
            f"<td>{html.escape(str(row.get('negative_buckets') or 0))}</td>"
            f"<td>{'Oui' if row.get('off_balance_included') else 'Non'}</td>"
            "</tr>"
        )

    alerts = list(interest.get("basis_risk_alerts", []))[:6]
    alert_html = "".join(
        f'''
        <div class="risk-alert {'high' if str(a.get("severity")) == "HIGH" else "medium"}">
          <b>{html.escape(str(a.get("label") or a.get("bucket_code") or "-"))}</b>
          <span>{html.escape(_fmt(float(a.get("max_basis_spread") or 0)))} pts - {html.escape(", ".join(a.get("types_present", [])))}</span>
        </div>'''
        for a in alerts
    ) or '<div class="notice">Aucune alerte de basis risk significative sur les buckets alimentés.</div>'

    return f'''
  <section class="section">
    <h2 class="section-title">Scenario Analysis</h2>
    <div class="section-subtitle">Comparaison ALCO des scénarios liquidité, hors-bilan, LCR, MCO, NII, EVE et basis risk.</div>
    <div class="balance-kpis">{kpi_html}</div>
    <table class="risk-table compact scenario-table">
      <thead>
        <tr>
          <th>Scénario</th><th>LCR</th><th>MCO</th><th>Point bas cumulé</th><th>Delta vs base</th><th>Buckets nég.</th><th>Hors-bilan</th>
        </tr>
      </thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan="7">Aucune donnée scenario.</td></tr>'}</tbody>
    </table>
    <h3 class="subsection-title">Alertes de basis risk</h3>
    <div class="risk-alerts">{alert_html}</div>
  </section>
'''


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

    public_user_label = _public_user_label(user_label)
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
        f"{param.bankName.strip()} — exemplaire de {public_user_label} — {generated_at.strftime('%d/%m/%Y %H:%M')}"
        if param.bankName.strip()
        else f"Exemplaire de {public_user_label} — {generated_at.strftime('%d/%m/%Y %H:%M')}"
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

    balance_sheet_html, balance_sheet_summary = _build_balance_sheet_html()
    balance_gap = balance_sheet_summary.get("gap_lcy")
    rate_basis_html = _build_rate_basis_html()
    eve_irrbb_html = _build_eve_irrbb_html()
    scenario_analysis_html = _build_scenario_analysis_html()

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
.notice {{
  padding: 12pt 14pt;
  border: 0.7pt solid #DDE7F1;
  border-radius: 7pt;
  background: #F8FBFE;
  color: #5F6E7A;
  font-weight: 700;
}}
.notice.error {{ color: #B71C1C; background: #FFF3F3; border-color: #F2C5C5; }}
.balance-kpis {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 8pt 0;
  margin: 8pt -8pt 12pt;
}}
.balance-kpis div {{
  display: table-cell;
  padding: 10pt 11pt;
  border: 0.7pt solid #DDE7F1;
  border-radius: 8pt;
  background: #FFFFFF;
}}
.balance-kpis span {{
  display: block;
  color: #5D6B7D;
  font-size: 7.5pt;
  font-weight: 900;
  text-transform: uppercase;
}}
.balance-kpis b {{
  display: block;
  margin-top: 5pt;
  color: #002E5F;
  font-size: 15pt;
  line-height: 1;
}}
.balance-kpis small {{
  display: block;
  margin-top: 4pt;
  color: #748094;
  font-size: 7.5pt;
}}
.balance-split {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10pt;
  margin-bottom: 11pt;
}}
.balance-split div {{
  padding: 9pt 11pt;
  border: 0.7pt solid rgba(0,46,95,0.14);
  border-radius: 7pt;
  background: rgba(248,251,254,0.80);
}}
.balance-split h3 {{
  margin: 0 0 6pt;
  color: #002E5F;
  font-size: 10.5pt;
  font-weight: 850;
}}
.balance-split p {{
  margin: 3pt 0;
  color: #3E4C5D;
  font-size: 9.3pt;
}}
table.balance-table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 8.8pt;
}}
table.balance-table th {{
  padding: 6pt 7pt;
  background: #EAF1F8;
  color: #002E5F;
  border: 0.5pt solid #D6E2EE;
  font-weight: 850;
  text-align: right;
}}
table.balance-table th:first-child {{ text-align: left; }}
table.balance-table td {{
  padding: 5pt 7pt;
  border: 0.5pt solid #DDE7F1;
  text-align: right;
}}
table.balance-table td:first-child {{ text-align: left; }}
.tag {{
  display: inline-block;
  margin-left: 4pt;
  padding: 1pt 4pt;
  border-radius: 99pt;
  background: #EEF5FC;
  color: #002E5F;
  font-size: 6.8pt;
  font-weight: 850;
}}
.neg {{ color: #B71C1C !important; }}
.pos {{ color: #1B5E20 !important; }}
.risk-alerts {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8pt;
  margin: 8pt 0 12pt;
}}
.risk-alert {{
  padding: 9pt 10pt;
  border-radius: 7pt;
  border: 0.7pt solid #DDE7F1;
  background: #FFFFFF;
}}
.risk-alert.high {{ border-color: #F2C5C5; background: #FFF3F3; }}
.risk-alert.medium {{ border-color: #F6D99C; background: #FFF8E8; }}
.risk-alert b {{
  display: block;
  color: #002E5F;
  font-size: 9.5pt;
}}
.risk-alert span {{
  display: block;
  margin-top: 3pt;
  color: #5F6E7A;
  font-size: 8pt;
  font-weight: 700;
}}
.subsection-title {{
  margin: 13pt 0 7pt;
  color: #002E5F;
  font-size: 11pt;
  font-weight: 850;
}}
table.risk-table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 8.3pt;
}}
table.risk-table.compact {{ font-size: 8.8pt; }}
table.risk-table th {{
  padding: 6pt 6pt;
  border: 0.5pt solid #D6E2EE;
  background: #EAF1F8;
  color: #002E5F;
  text-align: right;
  font-weight: 850;
}}
table.risk-table th:first-child,
table.risk-table th:nth-child(2) {{ text-align: left; }}
table.risk-table td {{
  padding: 5pt 6pt;
  border: 0.5pt solid #DDE7F1;
  text-align: right;
}}
table.risk-table td:first-child,
table.risk-table td:nth-child(2) {{ text-align: left; }}

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
      <div class="kpi"><span>Gap bilan GL</span><b>{_short_fmt(balance_gap / 1e6) if balance_gap is not None else "-"}</b><small>M FCFA</small></div>
    </div>
    <div class="cover-footer">
      <div>{lcr_chip}</div>
      <table>
        <tr><td class="lbl">Date du rapport</td><td>{generated_at.strftime("%d/%m/%Y %H:%M")}</td></tr>
        <tr><td class="lbl">Édité par</td><td>{html.escape(public_user_label)}</td></tr>
      </table>
    </div>
  </section>

  <!-- BILAN OFFICIEL -->
  {balance_sheet_html}

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

  <!-- TAUX / BASIS RISK -->
  {rate_basis_html}

  <!-- EVE / IRRBB -->
  {eve_irrbb_html}

  <!-- SCENARIO ANALYSIS -->
  {scenario_analysis_html}

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
