"""
Synthèse de gap de liquidité : ventilation des Output par bucket de maturité.

Trois scénarios :
- BASE : aucun choc.
- MODÉRÉ : chocs Parameter.credMod / banMod / retMod / guiMod.
- SÉVÈRE : chocs Parameter.credSev / banSev / retSev / guiSev.

La logique de mapping « type d'output -> choc » reproduit fidèlement
ModereController.php / SevereController.php :
    credit       -> (100 - credMod) / 100
    pret_ter_cor -> (100 - banMod)  / 100
    beac         -> (100 - banMod)  / 100
    decouvert    -> (100 - banMod)  / 100
    depot_terme  -> (100 + guiMod)  / 100   (sortie anticipée)
    compte_371   -> (100 + retMod)  / 100
    compte_372   -> (100 + retMod)  / 100
    compte_373   -> (100 + retMod)  / 100
    compte_vue_cor -> (100 + retMod) / 100
    bon          -> 1   (pas de choc)
    autres       -> 1   (pas de choc)

Les agrégats utilisés pour la synthèse :
- Actifs contractuels  : credit, bta, ota, emprunt_obl, pret_ter_cor, pret_cor, pret_titre, inter_blanc
- Actifs comportementaux : decouvert, beac, billet
- Dépenses contractuelles : pension_livree, emprunt_inter_banc, depot_terme, emprunt_instit_etran, bon, avance_beac, emprunt_titre
- Dépenses comportementales : compte_371, compte_372, compte_373, compte_vue_cor
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
from django.utils import timezone

from apps.inputs.models import Output
from apps.governance.services import get_assumption_value
from apps.parameters.models import Parameter
from .buckets import build_buckets, NB_BUCKETS

ASSETS_CONTRAT = ["credit", "bta", "ota", "emprunt_obl", "pret_ter_cor", "pret_cor", "pret_titre", "inter_blanc"]
ASSETS_COMPOR = ["decouvert", "beac", "billet"]
DEPENSES_CONTRAT = ["pension_livree", "emprunt_inter_banc", "depot_terme", "emprunt_instit_etran", "bon", "avance_beac", "emprunt_titre"]
DEPENSES_COMPOR = ["compte_371", "compte_372", "compte_373", "compte_vue_cor"]
ALL_TYPES = ASSETS_CONTRAT + ASSETS_COMPOR + DEPENSES_CONTRAT + DEPENSES_COMPOR

SCENARIOS = ("base", "modere", "severe")


def _shock_factor(type_output: str, scenario: str, param: Parameter) -> float:
    """Retourne le facteur multiplicatif à appliquer."""
    if scenario == "base":
        return 1.0
    if scenario == "modere":
        cred = get_assumption_value("stress_credit_modere_pct", param.credMod)
        ban = get_assumption_value("stress_bank_modere_pct", param.banMod)
        ret = get_assumption_value("stress_retail_withdrawal_modere_pct", param.retMod)
        gui = get_assumption_value("stress_term_deposit_modere_pct", param.guiMod)
    else:
        cred = get_assumption_value("stress_credit_severe_pct", param.credSev)
        ban = get_assumption_value("stress_bank_severe_pct", param.banSev)
        ret = get_assumption_value("stress_retail_withdrawal_severe_pct", param.retSev)
        gui = get_assumption_value("stress_term_deposit_severe_pct", param.guiSev)

    table = {
        "credit": (100 - cred) / 100,
        "pret_ter_cor": (100 - ban) / 100,
        "beac": (100 - ban) / 100,
        "decouvert": (100 - ban) / 100,
        "depot_terme": (100 + gui) / 100,
        "compte_371": (100 + ret) / 100,
        "compte_372": (100 + ret) / 100,
        "compte_373": (100 + ret) / 100,
        "compte_vue_cor": (100 + ret) / 100,
    }
    return table.get(type_output, 1.0)


def _outputs_dataframe() -> pd.DataFrame:
    """Charge tous les outputs en DataFrame."""
    qs = Output.objects.all().values("type_output", "date", "montant")
    df = pd.DataFrame.from_records(qs)
    if df.empty:
        df = pd.DataFrame(columns=["type_output", "date", "montant"])
    return df


def _aggregate_by_bucket(df: pd.DataFrame, ref: dt.datetime) -> dict[str, list[float]]:
    """Pour chaque type, retourne la liste des montants ventilés par bucket
    (en millions, 2 décimales) — comme dans la version Symfony."""
    buckets = build_buckets(ref)

    result: dict[str, list[float]] = {t: [0.0] * NB_BUCKETS for t in ALL_TYPES}
    if df.empty:
        return result

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True)

    for type_output, group in df.groupby("type_output"):
        if type_output not in result:
            result[type_output] = [0.0] * NB_BUCKETS
        for i, b in enumerate(buckets):
            start = pd.Timestamp(b.start)
            end = pd.Timestamp(b.end) if b.end else None
            mask = (group["date"] >= start)
            if end is not None:
                mask &= (group["date"] < end)
            total = group.loc[mask, "montant"].sum()
            result[type_output][i] = round(float(total) / 1_000_000, 2)
    return result


def compute_synthesis(scenario: str = "base") -> dict[str, Any]:
    """Calcule la synthèse pour un scénario donné."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Scénario inconnu : {scenario}")

    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)

    df = _outputs_dataframe()
    table = _aggregate_by_bucket(df, ref)

    # Application des chocs
    if scenario != "base":
        shocked = {}
        for t, values in table.items():
            f = _shock_factor(t, scenario, param)
            shocked[t] = [round(v * f, 2) for v in values]
        table = shocked

    # Pour chaque type, on préfixe le total ligne
    enriched: dict[str, list[float]] = {}
    for t, values in table.items():
        total = round(sum(values))
        enriched[t] = [total] + values

    # Agrégats
    def _sum_arrays(types: list[str]) -> list[float]:
        # On prend les buckets uniquement (pas la première colonne total)
        cols = [enriched[t][1:] for t in types if t in enriched]
        if not cols:
            return [0.0] * NB_BUCKETS
        return [round(sum(col[i] for col in cols), 2) for i in range(NB_BUCKETS)]

    total_assets_contrat = _sum_arrays(ASSETS_CONTRAT)
    total_assets_compor = _sum_arrays(ASSETS_COMPOR)
    total_assets = [round(a + b, 2) for a, b in zip(total_assets_contrat, total_assets_compor)]

    total_dep_contrat = _sum_arrays(DEPENSES_CONTRAT)
    total_dep_compor = _sum_arrays(DEPENSES_COMPOR)
    total_depense = [round(a + b, 2) for a, b in zip(total_dep_contrat, total_dep_compor)]

    # Cumulatives
    cum_assets, cum_dep = [], []
    s_a = s_d = 0.0
    for a, d in zip(total_assets, total_depense):
        s_a += a
        s_d += d
        cum_assets.append(round(s_a, 2))
        cum_dep.append(round(s_d, 2))

    # Net funding et cumul de net funding
    net_funding = [round(a - d, 2) for a, d in zip(total_assets, total_depense)]
    cum_net = []
    s_n = 0.0
    for n in net_funding:
        s_n += n
        cum_net.append(round(s_n, 2))

    return {
        "scenario": scenario,
        "reference_date": ref.isoformat(),
        "buckets": [b.label for b in build_buckets(ref)],
        "lignes": enriched,                # {type_output: [total, b1, b2, ...]}
        "total_assets_contrat": total_assets_contrat,
        "total_assets_compor": total_assets_compor,
        "total_assets": total_assets,
        "total_depense_contrat": total_dep_contrat,
        "total_depense_compor": total_dep_compor,
        "total_depense": total_depense,
        "net_funding": net_funding,
        "cumulative_net_funding": cum_net,
        "cumulative_assets": cum_assets,
        "cumulative_depense": cum_dep,
    }


def compute_all_scenarios() -> dict[str, dict]:
    """Calcule les trois scénarios d'un coup (utilisé par le dashboard)."""
    return {sc: compute_synthesis(sc) for sc in SCENARIOS}


def build_charts_payload() -> dict[str, dict[str, Any]]:
    """Sous-ensemble de la synthèse utilisé par Graphes et PDF Graphes."""
    all_scenarios = compute_all_scenarios()
    return {
        sc: {
            "buckets": data["buckets"],
            "net_funding": data["net_funding"],
            "cumulative_net_funding": data["cumulative_net_funding"],
            "total_assets": data["total_assets"],
            "total_depense": data["total_depense"],
            "cumulative_assets": data["cumulative_assets"],
            "cumulative_depense": data["cumulative_depense"],
        }
        for sc, data in all_scenarios.items()
    }
