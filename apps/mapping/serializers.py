from rest_framework import serializers
from .models import (
    Branch, CollateralType, Currency, CustomerSegment, Entity, FxRate,
    OffBalanceCommitment, ProductMapping, RepricingBucket,
)


def _factory(model_cls):
    Meta = type("Meta", (), {"model": model_cls, "fields": "__all__"})
    return type(f"{model_cls.__name__}Serializer",
                (serializers.ModelSerializer,),
                {"Meta": Meta})


CurrencySerializer = _factory(Currency)
FxRateSerializer = _factory(FxRate)
EntitySerializer = _factory(Entity)
BranchSerializer = _factory(Branch)
ProductMappingSerializer = _factory(ProductMapping)
RepricingBucketSerializer = _factory(RepricingBucket)
CustomerSegmentSerializer = _factory(CustomerSegment)
CollateralTypeSerializer = _factory(CollateralType)
OffBalanceCommitmentSerializer = _factory(OffBalanceCommitment)
