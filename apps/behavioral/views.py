from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasHabilitation
from .models import (
    EarlyWithdrawalModel, EmbeddedOption, NmdModel, PrepaymentModel, RolloverModel,
)
from .serializers import (
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
