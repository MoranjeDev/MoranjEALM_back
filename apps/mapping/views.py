from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasHabilitation

from .models import (
    Branch, CollateralType, Currency, CustomerSegment, Entity, FxRate,
    OffBalanceCommitment, ProductMapping, RepricingBucket,
)
from .serializers import (
    BranchSerializer, CollateralTypeSerializer, CurrencySerializer,
    CustomerSegmentSerializer, EntitySerializer, FxRateSerializer,
    OffBalanceCommitmentSerializer, ProductMappingSerializer,
    RepricingBucketSerializer,
)


class _Base(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Liquidity Gap"


class CurrencyViewSet(_Base):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = ["is_active", "is_base"]


class FxRateViewSet(_Base):
    queryset = FxRate.objects.all()
    serializer_class = FxRateSerializer
    filterset_fields = ["currency", "date"]


class EntityViewSet(_Base):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    required_habilitation = "Vue consolidée groupe"


class BranchViewSet(_Base):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    filterset_fields = ["entity", "is_active"]


class ProductMappingViewSet(_Base):
    queryset = ProductMapping.objects.all()
    serializer_class = ProductMappingSerializer
    filterset_fields = ["source_system", "target_kind", "is_active"]


class RepricingBucketViewSet(_Base):
    queryset = RepricingBucket.objects.all()
    serializer_class = RepricingBucketSerializer


class CustomerSegmentViewSet(_Base):
    queryset = CustomerSegment.objects.all()
    serializer_class = CustomerSegmentSerializer


class CollateralTypeViewSet(_Base):
    queryset = CollateralType.objects.all()
    serializer_class = CollateralTypeSerializer


class OffBalanceCommitmentViewSet(_Base):
    queryset = OffBalanceCommitment.objects.all()
    serializer_class = OffBalanceCommitmentSerializer
    filterset_fields = ["type", "currency", "is_active"]
