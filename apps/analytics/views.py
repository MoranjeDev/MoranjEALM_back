from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from .concentration import compute_concentration
from .eve import compute_eve_sensitivity
from .nii import compute_nii_sensitivity


class NIISensitivityView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "NII Sensitivity"

    def get(self, request):
        horizon = int(request.query_params.get("horizon_days", 365))
        return Response(compute_nii_sensitivity(horizon_days=horizon))


class EVESensitivityView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "EVE Sensitivity"

    def get(self, request):
        return Response(compute_eve_sensitivity())


class ConcentrationView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Concentration"

    def get(self, request):
        n = int(request.query_params.get("n", 20))
        return Response(compute_concentration(n=n))
