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


class BalanceSheetByCurrencyView(APIView):
    """GET ?date_arrete=YYYY-MM-DD : bilan FCY/LCY/consolidé."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .balance_sheet_currency import compute_balance_sheet_by_currency
        date_arrete = request.query_params.get("date_arrete")
        return Response(compute_balance_sheet_by_currency(date_arrete=date_arrete))


class FxPositionView(APIView):
    """GET ?date_arrete=YYYY-MM-DD : position FX nette par devise."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .balance_sheet_currency import compute_fx_position
        date_arrete = request.query_params.get("date_arrete")
        return Response(compute_fx_position(date_arrete=date_arrete))
