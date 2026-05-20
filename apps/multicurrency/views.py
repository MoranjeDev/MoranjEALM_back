from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from .services import compute_positions_by_currency


class PositionsByCurrencyView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Multi-devises"

    def get(self, request):
        return Response(compute_positions_by_currency())
