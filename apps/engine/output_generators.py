"""
Générateurs d'Output : transforment chaque ligne d'input en N lignes Output
(une par échéance attendue), avec montant et date.

Cette logique reproduit le comportement de l'application Symfony :
- Les inputs avec un échéancier (crédits, dépôts à terme, etc.) sont éclatés
  par échéance selon la fréquence/périodicité.
- Les inputs sans échéancier (BTA, OTA, BEAC, billet, comptes courants...)
  produisent un seul Output à leur date de maturité ou date courante.

Le module est appelé en deux temps :
1. `regenerate_outputs(reference_date)` : vide les Output et les regénère
   pour tous les inputs.
2. Les routines Synthèse/LCR/Gap de taux lisent ensuite les Output déjà
   stockés en base.
"""
from __future__ import annotations

import datetime as dt
import math
from contextlib import contextmanager
from typing import Iterable

from django.db import connection, transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.inputs import models as M
from .behavioral_resolver import resolve_behavioral_params

# ----------------------------------------------------------------------------
# Mapping (catégorie d'output -> méthode de génération)
# ----------------------------------------------------------------------------

FREQUENCE_DAYS = {
    "JOURNALIER": 30,    # mêmes valeurs que la version Symfony
    "HEBDOMADAIRE": 30,
    "MENSUEL": 30,
    "BIMENSUEL": 60,
    "TRIMESTRIEL": 90,
    "SEMESTRIEL": 180,
    "ANNUEL": 360,
    "AUTRE": 1,
}


def _expected_payments(
    last_due: dt.datetime,
    reference: dt.datetime,
    period_days: int,
) -> list[dt.datetime]:
    """Calcule les dates d'échéance restantes (de reference jusqu'à last_due)."""
    if period_days <= 0:
        return [last_due] if last_due > reference else []
    # Nombre d'échéances entre reference et last_due
    diff = (last_due - reference).days
    n = max(int(diff / period_days) + 1, 1)
    dates: list[dt.datetime] = []
    for i in range(n):
        ech = last_due - dt.timedelta(days=i * period_days)
        if ech > reference:
            dates.append(ech)
    return dates


def _is_after_reference_day(value: dt.datetime, reference: dt.datetime) -> bool:
    """Même comparaison que Symfony : format('Ymd') > dateMajCore.format('Ymd')."""
    return value.date() > reference.date()


def _credit_outputs_like_symfony(
    last_due: dt.datetime,
    reference: dt.datetime,
    frequency: str,
) -> tuple[list[dt.datetime], int]:
    """Reproduit la boucle validée dans InputCreditController::output().

    Point important : Symfony calcule `pay = capitalRestant / ech` avant de
    filtrer les dates égales ou antérieures à la date de MAJ. Le dénominateur
    doit donc rester le nombre théorique d'échéances, pas le nombre d'outputs
    finalement insérés.
    """
    freq = (frequency or "").upper()
    period_days = FREQUENCE_DAYS.get(freq, 30)
    day_gap = (last_due - reference).days
    scheduled_count = 1 if freq == "AUTRE" else int(day_gap / period_days) + 1
    scheduled_count = max(scheduled_count, 1)

    dates: list[dt.datetime] = []
    for i in range(scheduled_count):
        due_date = last_due - dt.timedelta(days=i * period_days)
        if _is_after_reference_day(due_date, reference):
            dates.append(due_date)
    return dates, scheduled_count


def _months_before(value: dt.datetime, months: int) -> dt.datetime:
    """Equivalent Python de strtotime('<date> -N month') pour les prêts à terme."""
    return value - relativedelta(months=months)


def _months_after(value: dt.datetime, months: int) -> dt.datetime:
    """Equivalent Python de strtotime('<date> +N month')."""
    return value + relativedelta(months=months)


def _make_output(type_output: str, date: dt.datetime, amount: float) -> M.Output:
    if timezone.is_naive(date):
        date = timezone.make_aware(date)
    return M.Output(type_output=type_output, date=date, montant=int(round(amount)))


def _row_behavioral_params(product_kind: str, row: object | None = None) -> dict:
    return resolve_behavioral_params(
        product_kind,
        segment="all",
        business_unit=getattr(row, "business_unit", "") if row else "",
        secteur=getattr(row, "secteur", "") if row else "",
        devise=getattr(row, "devise", "") if row else "",
    )


def _future_call_date(ref: dt.datetime) -> dt.datetime:
    return ref + dt.timedelta(days=30)


def _behavioral_credit_split(amount: float, ref: dt.datetime, row: object) -> tuple[float, float, dict]:
    params = _row_behavioral_params("credit", row)
    cpr = max(0.0, min(float(params.get("cpr_annual_pct") or 0.0), 100.0)) / 100.0
    prepayment = amount * cpr
    remaining = max(amount - prepayment, 0.0)
    return remaining, prepayment, params


def _behavioral_liability_split(product_kind: str, amount: float, ref: dt.datetime, row: object) -> tuple[float, float, float, dict]:
    params = _row_behavioral_params(product_kind, row)
    early = max(0.0, min(float(params.get("early_withdrawal_pct") or 0.0), 100.0)) / 100.0
    rollover = max(0.0, min(float(params.get("rollover_rate_pct") or 0.0), 100.0)) / 100.0
    early_amount = amount * early
    rolled_amount = amount * rollover
    projected_base = max(amount - early_amount - rolled_amount, 0.0)
    factor = projected_base / amount if amount else 1.0
    return factor, early_amount, rolled_amount, params


# ----------------------------------------------------------------------------
# Générateurs spécifiques
# ----------------------------------------------------------------------------

def _gen_credit(ref: dt.datetime) -> Iterable[M.Output]:
    for c in M.InputCredit.objects.all():
        if not c.date_deu_echeance or not _is_after_reference_day(c.date_deu_echeance, ref):
            continue
        dates, scheduled_count = _credit_outputs_like_symfony(c.date_deu_echeance, ref, c.frequence)
        if not dates:
            continue
        remaining, prepayment, _ = _behavioral_credit_split(c.capital_restant or 0, ref, c)
        if prepayment:
            yield _make_output("credit", _future_call_date(ref), prepayment)
        amount_each = remaining / scheduled_count
        for d in dates:
            yield _make_output("credit", d, amount_each)


def _gen_pret_cor(ref: dt.datetime) -> Iterable[M.Output]:
    for p in M.InputPretCor.objects.all():
        last = p.date_dern_echeance
        if not last or not _is_after_reference_day(last, ref):
            continue

        periodicity_months = {
            "ANNUEL": 12,
            "MENSUEL": 1,
            "BIMENSUEL": 2,
            "TRIMESTRIEL": 3,
            "SEMESTRIEL": 6,
        }
        freq = periodicity_months.get((p.periodicite or "").upper())
        if not freq:
            continue

        remaining_count = 0
        for i in range(p.nbre_echeance or 0):
            due_date = _months_after(p.date_prem_echeance, i * freq)
            if due_date.date() < ref.date():
                remaining_count = (p.nbre_echeance or 0) - i

        if remaining_count <= 0:
            continue

        pay = (p.capital_restant or 0) / remaining_count
        for i in range(remaining_count):
            due_date = _months_after(ref, i * freq)
            yield _make_output("pret_cor", due_date, pay)


def _gen_terme(ref: dt.datetime) -> Iterable[M.Output]:
    """Prêts à terme correspondants, selon la logique Symfony validée."""
    for t in M.InputTerme.objects.all():
        if not t.maturite or not _is_after_reference_day(t.maturite, ref):
            continue

        amount = t.montant or 0
        rate = t.taux_int or 0
        periodicity = t.periodicite or ""
        month_gap = ((t.maturite - ref).days) / 30

        if periodicity == "A terme":
            initial_date = t.date_mep or ref
            year_gap = ((t.maturite - initial_date).days) / 360
            interest_rate = (rate / 100) * year_gap
            pay = amount * (1 + interest_rate)
            yield _make_output("pret_ter_cor", t.maturite, pay)
            continue

        periodicity_months = {
            "Annuelle": 12,
            "Mensuelle": 1,
            "Bimensuelle": 2,
            "Trimestrielle": 3,
            "Semestrielle": 6,
        }
        freq = periodicity_months.get(periodicity)
        if not freq:
            continue

        scheduled_count = int(month_gap / freq)
        period_rate = rate * freq / 1200
        interest = amount * period_rate
        principal_plus_interest = amount + interest

        for i in range(scheduled_count):
            due_date = _months_before(t.maturite, i * freq)
            if not _is_after_reference_day(due_date, ref):
                continue
            pay = principal_plus_interest if periodicity == "Annuelle" else interest
            yield _make_output("pret_ter_cor", due_date, pay)


def _gen_depot_terme(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputDepotTerme.objects.all():
        if not row.maturite or not _is_after_reference_day(row.maturite, ref):
            continue

        amount = row.montant or 0
        liability_factor, early_amount, _, _ = _behavioral_liability_split("depot_terme", amount, ref, row)
        if early_amount:
            yield _make_output("depot_terme", _future_call_date(ref), early_amount)
        rate = row.taux_interet or 0
        periodicity = row.periodicite or ""
        month_gap = ((row.maturite - ref).days) / 30

        if periodicity == "A terme":
            initial_date = row.date_mep or ref
            year_gap = ((row.maturite - initial_date).days) / 360
            interest_rate = (rate / 100) * year_gap
            pay = amount * (1 + interest_rate) * liability_factor
            yield _make_output("depot_terme", row.maturite, pay)
            continue

        periodicity_months = {
            "Annuelle": 12,
            "Mensuelle": 1,
            "Bimensuelle": 2,
            "Trimestrielle": 3,
            "Semestrielle": 6,
        }
        freq = periodicity_months.get(periodicity)
        if not freq:
            continue

        scheduled_count = int(month_gap / freq)
        period_rate = rate * freq / 1200
        interest = amount * period_rate
        principal_plus_interest = (amount + interest) * liability_factor

        yield _make_output("depot_terme", row.maturite, principal_plus_interest)
        for i in range(scheduled_count):
            due_date = _months_before(row.maturite, i * freq)
            if not _is_after_reference_day(due_date, ref):
                continue
            yield _make_output("depot_terme", due_date, interest * liability_factor)


def _gen_bon(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputBonCaisse.objects.all():
        if not row.maturite or not _is_after_reference_day(row.maturite, ref):
            continue

        amount = row.montant or 0
        liability_factor, early_amount, _, _ = _behavioral_liability_split("bon", amount, ref, row)
        if early_amount:
            yield _make_output("bon", _future_call_date(ref), early_amount)
        rate = row.taux or 0
        periodicity = row.periodicite or ""
        month_gap = ((row.maturite - ref).days) / 30
        periodicity_months = {
            "Annuelle": 12,
            "Mensuelle": 1,
            "Bimensuelle": 2,
            "Trimestrielle": 3,
            "Semestrielle": 6,
        }
        if periodicity not in {"A terme", *periodicity_months.keys()}:
            periodicity = "A terme"

        if periodicity == "A terme":
            initial_date = row.date_mep or ref
            year_gap = ((row.maturite - initial_date).days) / 360
            interest_rate = (rate / 100) * year_gap
            pay = amount * (1 + interest_rate) * liability_factor
            yield _make_output("bon", row.maturite, pay)
            continue

        freq = periodicity_months.get(periodicity)
        if not freq:
            continue

        scheduled_count = int(month_gap / freq)
        period_rate = rate * freq / 1200
        interest = amount * period_rate
        principal_plus_interest = (amount + interest) * liability_factor

        for i in range(scheduled_count):
            due_date = _months_before(row.maturite, i * freq)
            if not _is_after_reference_day(due_date, ref):
                continue
            pay = principal_plus_interest if periodicity == "Annuelle" else interest * liability_factor
            yield _make_output("bon", due_date, pay)


def _gen_pension_livree(_: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputPensionLivree.objects.all():
        if not row.echeance:
            continue
        year_gap = ((row.echeance - row.date_mise_place).days) / 360
        interest_rate = (row.taux_interet or 0) / 100 * year_gap
        pay = (row.montant or 0) * (1 + interest_rate)
        yield _make_output("pension_livree", row.echeance, pay)


def _gen_avance_beac(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputAvanceBeac.objects.all():
        if not row.echeance or not _is_after_reference_day(row.echeance, ref):
            continue
        yield _make_output("avance_beac", row.echeance, row.montant_total_rembourse or 0)


def _gen_emprunt_titre(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputEmpruntTitre.objects.all():
        if not row.echeance or not _is_after_reference_day(row.echeance, ref):
            continue
        pay = (row.montant or 0) + (row.montant_total_rembourse or 0)
        yield _make_output("emprunt_titre", row.echeance, pay)


def _gen_emprunt_inter_banc(_: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputEmpruntInter.objects.all():
        if not row.echance:
            continue
        year_gap = ((row.echance - row.date_mise_place).days) / 365
        interest_rate = (row.taux_interet or 0) / 100 * year_gap
        pay = (row.montant or 0) * (1 + interest_rate)
        yield _make_output("emprunt_inter_banc", row.echance, pay)


def _gen_emprunt_instit_etran(ref: dt.datetime) -> Iterable[M.Output]:
    """Projection contractuelle des emprunts institutionnels sans équivalent Symfony."""
    for row in M.InputEmpruntInterBanc.objects.all():
        if not row.date_pro_echeance or not _is_after_reference_day(row.date_pro_echeance, ref):
            continue
        pay = (row.principal or 0) + (row.interet or 0)
        yield _make_output("emprunt_instit_etran", row.date_pro_echeance, pay)


def _gen_decouvert(ref: dt.datetime) -> Iterable[M.Output]:
    for d in M.InputDecouvert.objects.all():
        end = d.date_fin or (d.data_mise_place + dt.timedelta(days=d.duree or 0))
        if not end:
            continue

        amount = d.montant or 0
        ceiling = d.plafond or 0
        duration = d.duree or 0
        authorized_rate = d.taux_auto or 0
        over_ceiling_rate = d.taux_dela_plafond or 0

        regular_interest = amount * authorized_rate * duration / 36500
        over_ceiling_interest = 0
        if amount > ceiling:
            over_ceiling_interest = (amount - ceiling) * over_ceiling_rate * duration / 3650000
        pay = amount + regular_interest + over_ceiling_interest

        output_date = end if end.date() >= ref.date() else ref
        yield _make_output("decouvert", output_date, pay)


def _gen_simple_bullet(model_cls, type_output: str, date_field: str,
                      amount_field: str, ref: dt.datetime) -> Iterable[M.Output]:
    """Une ligne d'output au montant total à une date donnée."""
    for row in model_cls.objects.all():
        date = getattr(row, date_field)
        amount = getattr(row, amount_field)
        if date and amount and date > ref:
            yield _make_output(type_output, date, amount)


def _gen_treasury_security(model_cls, type_output: str, ref: dt.datetime) -> Iterable[M.Output]:
    for row in model_cls.objects.all():
        if not row.maturite or not _is_after_reference_day(row.maturite, ref):
            continue
        year_gap = ((row.maturite - row.date_valeur).days) / 365
        interest_rate = (row.taux_int or 0) / 100 * year_gap
        pay = (row.solde or 0) * (1 + interest_rate)
        yield _make_output(type_output, row.maturite, pay)


def _pmt_like_symfony(apr: float, loan_length: int, loan_amount: float) -> float:
    apr = (apr or 0) / 100
    if loan_length <= 0:
        return 0
    if apr == 0:
        return loan_amount / loan_length
    return apr * -loan_amount * (1 + apr) ** loan_length / (1 - (1 + apr) ** loan_length)


def _gen_emprunt_obl(_: dt.datetime) -> Iterable[M.Output]:
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    ref = param.dateMajCore or timezone.now()
    if timezone.is_naive(ref):
        ref = timezone.make_aware(ref)

    for row in M.InputEmpruntObl.objects.all():
        if not row.maturite:
            continue

        if row.maturite.date() >= ref.date():
            day_gap = (row.maturite - ref).days
            year_gap = int(day_gap / 365) + 1
            pay = _pmt_like_symfony(row.taux_int, year_gap, row.solde or 0)
            for i in range(year_gap):
                due_date = row.maturite - relativedelta(years=i)
                yield _make_output("emprunt_obl", due_date, pay)
        else:
            yield _make_output("emprunt_obl", ref, row.solde or 0)


def _gen_inter_blanc(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputPretInterBanc.objects.all():
        if not row.maturite or not _is_after_reference_day(row.maturite, ref):
            continue
        year_gap = ((row.maturite - row.date_mep).days) / 365
        interest_rate = (row.taux_int or 0) / 100 * year_gap
        pay = (row.solde or 0) * (1 + interest_rate)
        yield _make_output("inter_blanc", row.maturite, pay)


def _gen_pret_titre(ref: dt.datetime) -> Iterable[M.Output]:
    for row in M.InputPretTitre.objects.all():
        if not row.date_echeance or not _is_after_reference_day(row.date_echeance, ref):
            continue
        pay = (row.montant or 0) + (row.montant_rembourser or 0)
        yield _make_output("pret_titre", row.date_echeance, pay)


def _gen_billet(ref: dt.datetime) -> Iterable[M.Output]:
    """Billets : montant disponible à dateMajCore, comme Symfony."""
    for b in M.InputBillet.objects.all():
        yield _make_output("billet", ref, b.solde or 0)


def _gen_beac(ref: dt.datetime) -> Iterable[M.Output]:
    """Compte BEAC : modèle comportemental historique Symfony."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    logs: list[float] = []
    var_logs: list[float] = []
    previous_log = 0.0

    for index, row in enumerate(M.InputBeac.objects.all()):
        cumul = row.cumul or 0
        if cumul < 0:
            cumul *= -1
        if cumul <= 0:
            continue

        log_value = math.log(cumul)
        var_log = 0.0 if index == 0 else log_value - previous_log
        previous_log = log_value

        row.tableauLog = log_value
        row.tableauVarLog = var_log
        row.save(update_fields=["tableauLog", "tableauVarLog", "updated_at"])

        logs.append(log_value)
        var_logs.append(var_log)

    if not logs or not var_logs:
        return

    max_positive = abs(max(var_logs))
    max_negative = abs(min(var_logs))
    max_value = max_negative if (max_positive - max_negative) < 0 else max_positive
    n = int((2 * max_value) / 0.05) + 2

    values: list[float] = []
    frequencies: list[int] = []
    for i in range(n):
        value = max_value - (i * 0.05)
        values.append(value)
        frequencies.append(var_logs.count(value))

    max_frequency = max(frequencies)
    beta = 0.0
    for i in range(1, n):
        if frequencies[i] == max_frequency:
            beta = abs(values[i] - 0.008892)
            break

    if math.exp(beta) < 0.02:
        stable = math.exp(-beta)
        var = 1 - stable
    else:
        beta = 0.028892
        stable = math.exp(-0.02)
        var = 1 - stable

    param.beta_beac = beta
    param.stable_beac = stable
    param.var_beac = var
    param.save(update_fields=["beta_beac", "stable_beac", "var_beac", "updated_at"])

    initial_count = len(logs)
    for _ in range(30):
        avg = sum(logs) / len(logs)
        logs.append(avg - 0.3)

    for day_offset, log_index in ((0, 0), (7, 6), (15, 14), (30, 29)):
        due_date = ref + dt.timedelta(days=day_offset)
        amount = math.exp(logs[initial_count + log_index]) * stable
        yield _make_output("beac", due_date, amount)


def _gen_compte(model_cls, code: str, beta_field: str, stable_field: str,
                ref: dt.datetime) -> Iterable[M.Output]:
    """Comptes courants/chèques/livrets : pondérés par les coefficients
    comportementaux (stable, beta, var) du Parameter."""
    from apps.parameters.models import Parameter
    p = Parameter.get_solo()
    stable = getattr(p, stable_field) or 1.0
    for row in model_cls.objects.all():
        cumul = row.cumul
        if isinstance(cumul, str):
            try:
                cumul = float(cumul)
            except (TypeError, ValueError):
                cumul = 0
        yield _make_output(code, row.date or ref, (cumul or 0) * stable)


def _gen_compte_vue_cor(ref: dt.datetime) -> Iterable[M.Output]:
    """Comptes vue correspondants : modèle comportemental Symfony."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    logs: list[float] = []
    var_logs: list[float] = []
    previous_log = 0.0

    for index, row in enumerate(M.InputCpteCorr.objects.all()):
        cumul = row.cumul or 0
        if cumul < 0:
            cumul *= -1
        if cumul <= 0:
            continue

        log_value = math.log(cumul)
        var_log = 0.0 if index == 0 else log_value - previous_log
        previous_log = log_value

        row.tableauLog = log_value
        row.tableauVarLog = var_log
        row.save(update_fields=["tableauLog", "tableauVarLog", "updated_at"])

        logs.append(log_value)
        var_logs.append(var_log)

    if not logs or not var_logs:
        return

    max_positive = abs(max(var_logs))
    max_negative = abs(min(var_logs))
    max_value = max_negative if (max_positive - max_negative) < 0 else max_positive
    n = int((2 * max_value) / 0.05) + 2

    values: list[float] = []
    frequencies: list[int] = []
    for i in range(n):
        value = max_value - (i * 0.05)
        values.append(value)
        frequencies.append(var_logs.count(value))

    max_frequency = max(frequencies)
    beta = 0.0
    for i in range(1, n):
        if frequencies[i] == max_frequency:
            beta = abs(values[i] - 0.008892)
            break

    if math.exp(beta) < 0.02:
        stable = math.exp(-beta)
        var = 1 - stable
    else:
        beta = 0.028892
        stable = math.exp(-0.02)
        var = 1 - stable

    param.beta_corr = beta
    param.stable_corr = stable
    param.var_corr = var
    param.save(update_fields=["beta_corr", "stable_corr", "var_corr", "updated_at"])

    initial_count = len(logs)
    for _ in range(30):
        avg = sum(logs) / len(logs)
        logs.append(avg - 0.3)

    for day_offset, log_index in ((0, 0), (7, 6), (15, 14), (30, 29)):
        due_date = ref + dt.timedelta(days=day_offset)
        amount = math.exp(logs[initial_count + log_index]) * var
        yield _make_output("compte_vue_cor", due_date, amount)


def _behavioral_volatile_override(product_kind: str, computed_var: float) -> float:
    """
    Retourne le taux de volatilité (part sortante) à utiliser pour un produit NMD.

    Priorité :
    1. BehavioralDistributionParam actif pour ce product_type → volatile_pct / 100
    2. Valeur calculée statistiquement (algorithme Symfony) → computed_var

    Ce mécanisme permet à la banque de valider et d'activer ses propres hypothèses
    comportementales par segment (directive de la directrice ALM) tout en conservant
    l'algorithme Symfony comme fallback.
    """
    try:
        params = resolve_behavioral_params(product_kind)
        if params.get("source") == "behavioral_param":
            return params["volatile_pct"] / 100.0
    except Exception:
        pass
    return computed_var


def _gen_compte_371(ref: dt.datetime) -> Iterable[M.Output]:
    """Comptes courants 371 : modèle comportemental Symfony avec surcharge BehavioralDistributionParam."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    logs: list[float] = []
    var_logs: list[float] = []
    previous_log = 0.0

    for index, row in enumerate(M.InputCompteCourant.objects.all()):
        cumul = row.cumul or 0
        if cumul < 0:
            cumul *= -1
        if cumul <= 0:
            continue

        log_value = math.log(cumul)
        var_log = 0.0 if index == 0 else log_value - previous_log
        previous_log = log_value

        row.tableauLog = log_value
        row.tableauVarLog = var_log
        row.save(update_fields=["tableauLog", "tableauVarLog", "updated_at"])

        logs.append(log_value)
        var_logs.append(var_log)

    if not logs or not var_logs:
        return

    max_positive = abs(max(var_logs))
    max_negative = abs(min(var_logs))
    max_value = max_negative if (max_positive - max_negative) < 0 else max_positive
    n = int((2 * max_value) / 0.05) + 2

    values: list[float] = []
    frequencies: list[int] = []
    for i in range(n):
        value = max_value - (i * 0.05)
        values.append(value)
        frequencies.append(var_logs.count(value))

    max_frequency = max(frequencies)
    beta = 0.0
    for i in range(1, n):
        if frequencies[i] == max_frequency:
            beta = abs(values[i] - 0.008892)
            break

    if math.exp(beta) < 0.02:
        stable = math.exp(-beta)
        var = 1 - stable
    else:
        beta = 0.028892
        stable = math.exp(-0.02)
        var = 1 - stable

    param.beta_courant = beta
    param.stable_courant = stable
    param.var_courant = var
    param.save(update_fields=["beta_courant", "stable_courant", "var_courant", "updated_at"])

    # Surcharge par BehavioralDistributionParam si un paramètre actif existe
    var = _behavioral_volatile_override("compte_courant", var)

    initial_count = len(logs)
    for _ in range(30):
        avg = sum(logs) / len(logs)
        logs.append(avg - 0.3)

    for day_offset, log_index in ((0, 0), (7, 6), (15, 14), (30, 29)):
        due_date = ref + dt.timedelta(days=day_offset)
        amount = math.exp(logs[initial_count + log_index]) * var
        yield _make_output("compte_371", due_date, amount)


def _gen_compte_372(ref: dt.datetime) -> Iterable[M.Output]:
    """Comptes chèques 372 : modèle comportemental Symfony."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    logs: list[float] = []
    var_logs: list[float] = []
    previous_log = 0.0

    for index, row in enumerate(M.InputCompteCheque.objects.all()):
        cumul = row.cumul or 0
        if cumul < 0:
            cumul *= -1
        if cumul <= 0:
            continue

        log_value = math.log(cumul)
        var_log = 0.0 if index == 0 else log_value - previous_log
        previous_log = log_value

        row.tableauLog = log_value
        row.tableauVarLog = var_log
        row.save(update_fields=["tableauLog", "tableauVarLog", "updated_at"])

        logs.append(log_value)
        var_logs.append(var_log)

    if not logs or not var_logs:
        return

    max_positive = abs(max(var_logs))
    max_negative = abs(min(var_logs))
    max_value = max_negative if (max_positive - max_negative) < 0 else max_positive
    n = int((2 * max_value) / 0.05) + 2

    values: list[float] = []
    frequencies: list[int] = []
    for i in range(n):
        value = max_value - (i * 0.05)
        values.append(value)
        frequencies.append(var_logs.count(value))

    max_frequency = max(frequencies)
    beta = 0.0
    for i in range(1, n):
        if frequencies[i] == max_frequency:
            beta = abs(values[i] - 0.008892)
            break

    if math.exp(beta) < 0.02:
        stable = math.exp(-beta)
        var = 1 - stable
    else:
        beta = 0.028892
        stable = math.exp(-0.02)
        var = 1 - stable

    param.beta_cheque = beta
    param.stable_cheque = stable
    param.var_cheque = var
    param.save(update_fields=["beta_cheque", "stable_cheque", "var_cheque", "updated_at"])

    # Surcharge par BehavioralDistributionParam si un paramètre actif existe
    var = _behavioral_volatile_override("compte_cheque", var)

    initial_count = len(logs)
    for _ in range(30):
        avg = sum(logs) / len(logs)
        logs.append(avg - 0.3)

    for day_offset, log_index in ((0, 0), (7, 6), (15, 14), (30, 29)):
        due_date = ref + dt.timedelta(days=day_offset)
        amount = math.exp(logs[initial_count + log_index]) * var
        yield _make_output("compte_372", due_date, amount)


def _gen_compte_373(ref: dt.datetime) -> Iterable[M.Output]:
    """Comptes livrets 373 : modèle comportemental Symfony."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    logs: list[float] = []
    var_logs: list[float] = []
    previous_log = 0.0

    for index, row in enumerate(M.InputCompteLivret.objects.all()):
        cumul = row.cumul or 0
        if cumul < 0:
            cumul *= -1
        if cumul <= 0:
            continue

        log_value = math.log(cumul)
        var_log = 0.0 if index == 0 else log_value - previous_log
        previous_log = log_value

        row.tableauLog = log_value
        row.tableauVarLog = var_log
        row.save(update_fields=["tableauLog", "tableauVarLog", "updated_at"])

        logs.append(log_value)
        var_logs.append(var_log)

    if not logs or not var_logs:
        return

    max_positive = abs(max(var_logs))
    max_negative = abs(min(var_logs))
    max_value = max_negative if (max_positive - max_negative) < 0 else max_positive
    n = int((2 * max_value) / 0.05) + 2

    values: list[float] = []
    frequencies: list[int] = []
    for i in range(n):
        value = max_value - (i * 0.05)
        values.append(value)
        frequencies.append(var_logs.count(value))

    max_frequency = max(frequencies)
    beta = 0.0
    for i in range(1, n):
        if frequencies[i] == max_frequency:
            beta = abs(values[i] - 0.008892)
            break

    if math.exp(beta) < 0.02:
        stable = math.exp(-beta)
        var = 1 - stable
    else:
        beta = 0.028892
        stable = math.exp(-0.02)
        var = 1 - stable

    param.beta_livret = beta
    param.stable_livret = stable
    param.var_livret = var
    param.save(update_fields=["beta_livret", "stable_livret", "var_livret", "updated_at"])

    # Surcharge par BehavioralDistributionParam si un paramètre actif existe
    var = _behavioral_volatile_override("compte_livret", var)

    initial_count = len(logs)
    for _ in range(30):
        avg = sum(logs) / len(logs)
        logs.append(avg - 0.3)

    for day_offset, log_index in ((0, 0), (7, 6), (15, 14), (30, 29)):
        due_date = ref + dt.timedelta(days=day_offset)
        amount = math.exp(logs[initial_count + log_index]) * var
        yield _make_output("compte_373", due_date, amount)


# ----------------------------------------------------------------------------
# Mapping centralisé
# ----------------------------------------------------------------------------

GENERATORS = {
    # Actifs
    "credit":         _gen_credit,
    "pret_cor":       _gen_pret_cor,
    "pret_ter_cor":   _gen_terme,
    "decouvert":      _gen_decouvert,
    "bta":            lambda r: _gen_treasury_security(M.InputBta, "bta", r),
    "ota":            lambda r: _gen_treasury_security(M.InputOta, "ota", r),
    "emprunt_obl":    _gen_emprunt_obl,
    "pret_titre":     _gen_pret_titre,
    "inter_blanc":    _gen_inter_blanc,
    "billet":         _gen_billet,
    "beac":           _gen_beac,
    # Passifs
    "pension_livree": _gen_pension_livree,
    "emprunt_inter_banc": _gen_emprunt_inter_banc,
    "depot_terme":    _gen_depot_terme,
    "emprunt_instit_etran": _gen_emprunt_instit_etran,
    "bon":            _gen_bon,
    "avance_beac":    _gen_avance_beac,
    "emprunt_titre":  _gen_emprunt_titre,
    "compte_371":     _gen_compte_371,
    "compte_372":     _gen_compte_372,
    "compte_373":     _gen_compte_373,
    "compte_vue_cor": _gen_compte_vue_cor,
}

OUTPUT_TYPES = list(GENERATORS.keys())


# ----------------------------------------------------------------------------
# Orchestrateur
# ----------------------------------------------------------------------------

class OutputRegenerationAlreadyRunning(RuntimeError):
    """Une régénération est déjà en cours dans un autre worker/processus."""


@contextmanager
def _regeneration_lock(timeout_seconds: int = 5):
    """Evite deux remplacements concurrents de la table Output.

    MySQL pose un verrou applicatif partagé entre connexions. Les autres bases
    gardent le comportement habituel, utile pour SQLite en local/PythonAnywhere.
    """
    if connection.vendor != "mysql":
        yield
        return

    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", ["moranjealm_regenerate_outputs", timeout_seconds])
        acquired = cursor.fetchone()[0] == 1
    if not acquired:
        raise OutputRegenerationAlreadyRunning(
            "Une régénération des outputs est déjà en cours. Réessayez dans quelques secondes."
        )

    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", ["moranjealm_regenerate_outputs"])


def regenerate_outputs(reference_date: dt.datetime | None = None) -> dict:
    """Recalcule la totalité des Output à partir des inputs.
    Retourne un récapitulatif {type_output: nb_lignes_créées}."""
    from apps.parameters.models import Parameter

    param = Parameter.get_solo()
    if reference_date is None:
        reference_date = param.dateMajCore or timezone.now()
    if timezone.is_naive(reference_date):
        reference_date = timezone.make_aware(reference_date)

    summary: dict[str, int] = {}
    generated: dict[str, list[M.Output]] = {}

    for type_output, generator in GENERATORS.items():
        objs = list(generator(reference_date))
        generated[type_output] = objs
        summary[type_output] = len(objs)

    with _regeneration_lock():
        with transaction.atomic():
            M.Output.objects.all().delete()
            for objs in generated.values():
                if objs:
                    M.Output.objects.bulk_create(objs, batch_size=1000)

    return {
        "reference_date": reference_date.isoformat(),
        "total": sum(summary.values()),
        "by_type": summary,
    }
