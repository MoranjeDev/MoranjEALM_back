"""Vues API du moteur de calcul."""
import time

from django.db import OperationalError
from django.db.models import Count, Max, Min, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from apps.inputs.models import Output
from apps.tracking.models import Tracking

from .data_quality import compute_data_quality, compute_data_quality_detail
from .lcr import compute_lcr_all
from .output_generators import OutputRegenerationAlreadyRunning, regenerate_outputs
from .rate_gap import compute_rate_gap, compute_rate_gap_enriched
from .scenario_analysis import compute_scenario_analysis
from .synthesis import build_charts_payload, compute_all_scenarios, compute_synthesis, SCENARIOS


class RegenerateOutputsView(APIView):
    """POST : recalcule les Output à partir des inputs courants."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def post(self, request):
        result = None
        last_error = None
        for attempt in range(3):
            try:
                result = regenerate_outputs()
                break
            except OutputRegenerationAlreadyRunning as exc:
                return Response(
                    {
                        "detail": str(exc),
                        "code": "regeneration_already_running",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            except OperationalError as exc:
                if not _is_mysql_lock_timeout(exc):
                    raise
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)

        if result is None:
            return Response(
                {
                    "detail": (
                        "La base de données est occupée par une autre opération. "
                        "Relancez la régénération dans quelques secondes."
                    ),
                    "code": "database_lock_timeout",
                    "database_error": str(last_error),
                },
                status=status.HTTP_409_CONFLICT,
            )

        Tracking.objects.create(
            libelle="Régénération des outputs",
            description=(
                f"{result['total']} outputs créés à partir de la date de référence "
                f"{result['reference_date']}."
            ),
            utilisateur=request.user,
        )
        return Response(result)


def _is_mysql_lock_timeout(exc: OperationalError) -> bool:
    return bool(getattr(exc, "args", None)) and exc.args[0] in {1205, 1213}


class SynthesisView(APIView):
    """GET ?scenario=base|modere|severe : retourne la synthèse correspondante.
    GET sans paramètre : retourne les trois scénarios."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        scenario = request.query_params.get("scenario")
        if scenario:
            if scenario not in SCENARIOS:
                return Response({"detail": f"scenario inconnu : {scenario}"}, status=400)
            return Response(compute_synthesis(scenario))
        return Response(compute_all_scenarios())


class OutputsSummaryView(APIView):
    """GET : tableau de contrôle des outputs générés."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        rows = (
            Output.objects.values("type_output")
            .annotate(
                count=Count("id"),
                total_amount=Sum("montant"),
                min_amount=Min("montant"),
                max_amount=Max("montant"),
                first_date=Min("date"),
                last_date=Max("date"),
            )
            .order_by("type_output")
        )
        total_count = Output.objects.count()
        total_amount = Output.objects.aggregate(total=Sum("montant"))["total"] or 0
        return Response({
            "total_count": total_count,
            "total_amount": total_amount,
            "types_count": len(rows),
            "rows": list(rows),
        })


class DataQualityView(APIView):
    """GET : contrôle source importée vs outputs moteur et journal récent."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        return Response(compute_data_quality())


class DataQualityDetailView(APIView):
    """GET : drill-down source, output et lineage pour une famille d'input."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request, kind: str):
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        return Response(compute_data_quality_detail(kind, limit=limit))


class LCRView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Ratio de liquidité"

    def get(self, request):
        return Response(compute_lcr_all())


class RateGapView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gap de taux"

    def get(self, request):
        return Response(compute_rate_gap())


class RateGapByTypeView(APIView):
    """GET : gap de taux enrichi avec ventilation par type de taux (basis risk)."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        return Response(compute_rate_gap_enriched())


class ChartsView(APIView):
    """Données prêtes pour Chart.js (gap, profil de funding, cumul)."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Graphes"

    def get(self, request):
        return Response(build_charts_payload())


class OffBalanceSynthesisView(APIView):
    """GET : flux hors-bilan par bucket pour intégration dans le gap de liquidité."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .off_balance_outputs import get_off_balance_by_bucket
        from django.utils import timezone
        data = get_off_balance_by_bucket(timezone.now())
        return Response({"off_balance_by_bucket": data})


class MCOView(APIView):
    """GET : Maximum Cumulative Outflow pour les 3 scénarios."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .mco import compute_mco
        include_ob = request.query_params.get("include_off_balance", "1") == "1"
        return Response(compute_mco(include_off_balance=include_ob))


class BehavioralParamsDebugView(APIView):
    """GET ?product_kind=compte_371&segment=retail : résout et retourne les paramètres comportementaux."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .behavioral_resolver import resolve_behavioral_params
        product_kind = request.query_params.get("product_kind", "compte_371")
        segment = request.query_params.get("segment", "all")
        bu = request.query_params.get("business_unit", "")
        return Response(resolve_behavioral_params(product_kind, segment, bu))


class ScenarioAnalysisView(APIView):
    """GET ?balance_sheet_mode=static|dynamic : comparaison ALCO des scénarios."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        mode = request.query_params.get("balance_sheet_mode", "static")
        force_refresh = str(request.query_params.get("refresh", "")).lower() in {"1", "true", "yes"}
        return Response(compute_scenario_analysis(balance_sheet_mode=mode, force_refresh=force_refresh))
