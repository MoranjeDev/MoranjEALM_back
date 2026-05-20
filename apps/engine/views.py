"""Vues API du moteur de calcul."""
from django.db.models import Count, Max, Min, Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from apps.inputs.models import Output
from apps.tracking.models import Tracking

from .lcr import compute_lcr_all
from .output_generators import regenerate_outputs
from .rate_gap import compute_rate_gap
from .synthesis import build_charts_payload, compute_all_scenarios, compute_synthesis, SCENARIOS


class RegenerateOutputsView(APIView):
    """POST : recalcule les Output à partir des inputs courants."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def post(self, request):
        result = regenerate_outputs()
        Tracking.objects.create(
            libelle="Régénération des outputs",
            description=(
                f"{result['total']} outputs créés à partir de la date de référence "
                f"{result['reference_date']}."
            ),
            utilisateur=request.user,
        )
        return Response(result)


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


class ChartsView(APIView):
    """Données prêtes pour Chart.js (gap, profil de funding, cumul)."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Graphes"

    def get(self, request):
        return Response(build_charts_payload())
