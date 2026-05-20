from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from .models import FtpCurve, FtpPoint
from .serializers import FtpCurveSerializer, FtpPointSerializer
from .services import compute_margin_breakdown


class FtpCurveViewSet(viewsets.ModelViewSet):
    queryset = FtpCurve.objects.all().prefetch_related("points")
    serializer_class = FtpCurveSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "FTP"
    filterset_fields = ["currency", "is_active"]


class FtpPointViewSet(viewsets.ModelViewSet):
    queryset = FtpPoint.objects.all()
    serializer_class = FtpPointSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "FTP"
    filterset_fields = ["curve"]


class FtpMarginBreakdownView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "FTP"

    def get(self, request):
        currency = request.query_params.get("currency", "XAF")
        return Response(compute_margin_breakdown(currency_code=currency))
