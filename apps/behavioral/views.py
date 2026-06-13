from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import HasHabilitation
from .models import (
    BehavioralDistributionParam,
    EarlyWithdrawalModel, EmbeddedOption, NmdModel, PrepaymentModel, RolloverModel,
)
from .serializers import (
    BehavioralDistributionParamSerializer,
    EarlyWithdrawalModelSerializer, EmbeddedOptionSerializer,
    NmdModelSerializer, PrepaymentModelSerializer, RolloverModelSerializer,
)


class _BaseBehavioralViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Modélisation comportementale"


class NmdModelViewSet(_BaseBehavioralViewSet):
    queryset = NmdModel.objects.all()
    serializer_class = NmdModelSerializer
    filterset_fields = ["product", "segment", "is_active"]


class PrepaymentModelViewSet(_BaseBehavioralViewSet):
    queryset = PrepaymentModel.objects.all()
    serializer_class = PrepaymentModelSerializer
    filterset_fields = ["product", "is_active"]


class EarlyWithdrawalModelViewSet(_BaseBehavioralViewSet):
    queryset = EarlyWithdrawalModel.objects.all()
    serializer_class = EarlyWithdrawalModelSerializer
    filterset_fields = ["product", "is_active"]


class RolloverModelViewSet(_BaseBehavioralViewSet):
    queryset = RolloverModel.objects.all()
    serializer_class = RolloverModelSerializer
    filterset_fields = ["product", "is_active"]


class EmbeddedOptionViewSet(_BaseBehavioralViewSet):
    queryset = EmbeddedOption.objects.all()
    serializer_class = EmbeddedOptionSerializer
    filterset_fields = ["option_type", "is_active"]


class BehavioralDistributionParamViewSet(viewsets.ModelViewSet):
    """CRUD pour les paramètres comportementaux par segment."""
    queryset = BehavioralDistributionParam.objects.all().order_by("product_type", "segment")
    serializer_class = BehavioralDistributionParamSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Modélisation comportementale"

    @action(detail=False, methods=["get"], url_path="resolve")
    def resolve(self, request):
        """GET /api/behavioral/distribution/resolve/?product_type=compte_courant&segment=retail
        Retourne le paramètre le plus spécifique actif pour la combinaison donnée."""
        product_type = request.query_params.get("product_type", "")
        segment = request.query_params.get("segment", "all")
        bu = request.query_params.get("business_unit", "")
        secteur = request.query_params.get("secteur", "")
        devise = request.query_params.get("devise", "")
        param = BehavioralDistributionParam.resolve(
            product_type=product_type, segment=segment,
            business_unit=bu, secteur=secteur, devise=devise
        )
        if param is None:
            return Response({"detail": "Aucun paramètre actif trouvé."}, status=404)
        return Response(BehavioralDistributionParamSerializer(param).data)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """POST : activer un paramètre (le rend utilisable dans le moteur)."""
        param = self.get_object()
        param.is_active = True
        param.save()
        return Response({"detail": f"Paramètre {param.code} activé.", "id": param.pk})

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """POST : désactiver un paramètre."""
        param = self.get_object()
        param.is_active = False
        param.save()
        return Response({"detail": f"Paramètre {param.code} désactivé.", "id": param.pk})

    @action(detail=False, methods=["get"], url_path="active")
    def active_params(self, request):
        """GET : liste de tous les paramètres actifs."""
        qs = BehavioralDistributionParam.objects.filter(is_active=True)
        return Response(BehavioralDistributionParamSerializer(qs, many=True).data)
