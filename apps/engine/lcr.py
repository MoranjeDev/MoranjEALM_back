"""Liquidity Coverage Ratio, aligné sur la table Symfony LCR.

La page LCR Symfony ne reprend pas simplement les totaux actifs/dépenses :
elle construit une table réglementaire avec HQLA, entrées, sorties,
plafonnement des entrées à 75 % et ratio final.
"""
from __future__ import annotations

from typing import Any

from apps.governance.services import get_assumption_value
from .synthesis import SCENARIOS, compute_synthesis


def _line(data: dict[str, Any], type_output: str) -> list[float]:
    return data["lignes"].get(type_output, [0.0] * 12)


def _v(data: dict[str, Any], type_output: str, index: int) -> float:
    row = _line(data, type_output)
    return float(row[index]) if index < len(row) else 0.0


def _sum_indexes(data: dict[str, Any], types: list[str], indexes: range) -> float:
    return round(sum(_v(data, t, i) for t in types for i in indexes), 2)


def _component(label: str, weight: str, gross: float, weighted: float | None = None) -> dict:
    return {
        "label": label,
        "weight": weight,
        "gross": round(gross, 2),
        "weighted": round(gross if weighted is None else weighted, 2),
    }


def _block(rows: list[dict]) -> dict:
    return {
        "detail": [
            {
                "type": row["label"],
                "weight": row["weight"],
                "gross": row["gross"],
                "weighted": row["weighted"],
            }
            for row in rows
        ],
        "total_gross": round(sum(row["gross"] for row in rows), 2),
        "total_weighted": round(sum(row["weighted"] for row in rows), 2),
    }


def _compute_one(scenario: str) -> dict:
    data = compute_synthesis(scenario)
    level2_haircut = get_assumption_value("lcr_level2_haircut_pct", 15.0)
    level2_weight = max(0.0, (100 - level2_haircut) / 100)
    level1_weight = get_assumption_value("lcr_level1_weight_pct", 100.0) / 100
    retail_inflow_weight = get_assumption_value("lcr_retail_inflow_weight_pct", 50.0) / 100
    financial_inflow_weight = get_assumption_value("lcr_financial_inflow_weight_pct", 100.0) / 100
    sight_financial_claim_weight = get_assumption_value("lcr_sight_financial_claim_weight_pct", 0.0) / 100
    retail_deposit_runoff = get_assumption_value("lcr_retail_deposit_runoff_pct", 10.0) / 100
    corporate_deposit_runoff = get_assumption_value("lcr_corporate_deposit_runoff_pct", 40.0) / 100
    financial_outflow_runoff = get_assumption_value("lcr_financial_outflow_runoff_pct", 100.0) / 100
    other_due_runoff = get_assumption_value("lcr_other_due_runoff_pct", 100.0) / 100
    guarantee_runoff = get_assumption_value("lcr_guarantee_runoff_pct", 5.0) / 100
    equity_weight = get_assumption_value("lcr_equity_weight_pct", 50.0) / 100
    inflow_cap_pct = get_assumption_value("lcr_inflow_cap_pct", 75.0) / 100
    minimum_ratio = get_assumption_value("lcr_minimum_ratio_pct", 100.0)

    cash = _v(data, "billet", 1)
    central_bank = _v(data, "beac", 0)
    sovereign = _v(data, "bta", 0) + _v(data, "ota", 0) + _v(data, "emprunt_obl", 0)
    level_1 = round(cash + central_bank + sovereign, 2)
    level_1_weighted = round(level_1 * level1_weight, 2)

    opcvm = _v(data, "pret_titre", 0)
    level_2_weighted = round(opcvm * level2_weight, 2)
    hqla_gross = round(level_1 + opcvm, 2)
    hqla_weighted = round(level_1_weighted + level_2_weighted, 2)

    financial_inflows = _sum_indexes(
        data,
        ["pret_ter_cor", "inter_blanc", "pret_cor", "pret_titre"],
        range(1, 5),
    )
    retail_inflows = _sum_indexes(data, ["credit", "decouvert"], range(1, 5))
    sight_financial_claims = 0.0
    financial_inflows_weighted = round(financial_inflows * financial_inflow_weight, 2)
    retail_inflows_weighted = round(retail_inflows * retail_inflow_weight, 2)
    inflows_gross = round(financial_inflows + retail_inflows, 2)
    inflows_weighted = round(
        financial_inflows_weighted + (sight_financial_claims * sight_financial_claim_weight) + retail_inflows_weighted,
        2,
    )

    retail_deposits = round(
        _v(data, "depot_terme", 4) + _v(data, "compte_372", 4) + _v(data, "compte_373", 4),
        2,
    )
    corporate_deposits = _v(data, "compte_373", 4)
    financial_outflows = round(
        _sum_indexes(
            data,
            ["pension_livree", "emprunt_inter_banc", "depot_terme", "emprunt_instit_etran", "bon", "avance_beac"],
            range(1, 5),
        )
        - _v(data, "compte_vue_cor", 4),
        2,
    )
    other_due = round(
        _v(data, "pension_livree", 4)
        + _v(data, "avance_beac", 4)
        + _v(data, "emprunt_inter_banc", 4)
        + _v(data, "emprunt_titre", 4),
        2,
    )

    retail_deposits_weighted = round(retail_deposits * retail_deposit_runoff, 2)
    corporate_deposits_weighted = round(corporate_deposits * corporate_deposit_runoff, 2)
    financial_outflows_weighted = round(financial_outflows * financial_outflow_runoff, 2)
    other_due_weighted = round(other_due * other_due_runoff, 2)
    guarantees = 0.0
    guarantees_weighted = round(guarantees * guarantee_runoff, 2)
    outflows_gross = round(retail_deposits + corporate_deposits + financial_outflows + other_due, 2)
    outflows_weighted = round(
        retail_deposits_weighted + corporate_deposits_weighted + financial_outflows_weighted + other_due_weighted + guarantees_weighted,
        2,
    )

    inflow_cap = round(outflows_weighted * inflow_cap_pct, 2)
    retained_inflows = min(inflows_weighted, inflow_cap)
    net_outflows = round(outflows_weighted - retained_inflows, 2)
    lcr_pct = round(hqla_weighted / net_outflows * 100, 2) if net_outflows > 0 else None

    components = {
        "level_1": _component("Actif liquide de niveau 1", "", level_1, level_1_weighted),
        "cash": _component("Valeurs en caisse", f"{level1_weight * 100:.0f}%", cash, round(cash * level1_weight, 2)),
        "central_bank": _component("Avoirs auprès de la Banque Centrale", f"{level1_weight * 100:.0f}%", central_bank, round(central_bank * level1_weight, 2)),
        "sovereign": _component("Bons et Obligations émis par des emprunteurs souverains", f"{level1_weight * 100:.0f}%", sovereign, round(sovereign * level1_weight, 2)),
        "level_2": _component("Actif liquide de niveau 2", "", opcvm, level_2_weighted),
        "state_bonds": _component("Obligations émises ou garanties par l'Etat, les organismes publics", f"{level2_weight * 100:.0f}%", 0, 0),
        "central_multilateral_bonds": _component("Obligations garanties par Banques Centrales et banques multilatérales", f"{level2_weight * 100:.0f}%", 0, 0),
        "opcvm": _component("Parts OPCVM et SICAV", f"{level2_weight * 100:.0f}%", opcvm, level_2_weighted),
        "equities": _component("Actions non émises par une entreprise financière", f"{equity_weight * 100:.0f}%", 0, 0),
        "hqla": _component("HQLA", "", hqla_gross, hqla_weighted),
        "inflows": _component("Entrées de trésorerie", "", inflows_gross, inflows_weighted),
        "financial_inflows": _component("Échéances des créances sur les entreprises financières dans 30 jours", f"{financial_inflow_weight * 100:.0f}%", financial_inflows, financial_inflows_weighted),
        "sight_financial_claims": _component("Créances à vue sur les entreprises financières", f"{sight_financial_claim_weight * 100:.0f}%", sight_financial_claims, sight_financial_claims * sight_financial_claim_weight),
        "retail_inflows": _component("Échéances des créances sur les particuliers et personnes morales dans 30 jours", f"{retail_inflow_weight * 100:.0f}%", retail_inflows, retail_inflows_weighted),
        "outflows": _component("Sorties de trésorerie", "", outflows_gross, outflows_weighted),
        "retail_deposits": _component("Dépôts des particuliers à vue ou à terme dans 30 jours", f"{retail_deposit_runoff * 100:.0f}%", retail_deposits, retail_deposits_weighted),
        "corporate_deposits": _component("Dépôts des entreprises à vue ou à terme dans 30 jours", f"{corporate_deposit_runoff * 100:.0f}%", corporate_deposits, corporate_deposits_weighted),
        "financial_outflows": _component("Dépôts et emprunts des entreprises financières", f"{financial_outflow_runoff * 100:.0f}%", financial_outflows, financial_outflows_weighted),
        "other_due": _component("Autres dépôts et emprunts exigibles du passif", f"{other_due_runoff * 100:.0f}%", other_due, other_due_weighted),
        "guarantees": _component("Sorties relatives aux garanties et obligations conditionnelles", f"{guarantee_runoff * 100:.0f}%", guarantees, guarantees_weighted),
        "net_outflows": _component("Sortie nette de trésorerie", "", 0, net_outflows),
        "lcr": _component("LCR", "", 0, lcr_pct or 0),
    }

    return {
        **data,
        "components": components,
        "hqla": _block([components["cash"], components["central_bank"], components["sovereign"], components["opcvm"]]),
        "inflows": _block([components["financial_inflows"], components["retail_inflows"]]),
        "outflows": _block([
            components["retail_deposits"],
            components["corporate_deposits"],
            components["financial_outflows"],
            components["other_due"],
            components["guarantees"],
        ]),
        "inflow_cap": inflow_cap,
        "retained_inflows": retained_inflows,
        "net_outflows": net_outflows,
        "lcr_pct": lcr_pct,
        "ratio_pct": lcr_pct,
        "compliant": lcr_pct is not None and lcr_pct >= minimum_ratio,
        "total_assets_sum": hqla_weighted,
        "total_depense_sum": net_outflows,
        "net_gap_sum": round(hqla_weighted - net_outflows, 2),
    }


def compute_lcr_all() -> dict:
    return {scenario: _compute_one(scenario) for scenario in SCENARIOS}
