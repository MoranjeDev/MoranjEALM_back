from rest_framework.routers import DefaultRouter
from .views import (
    BranchViewSet, CollateralTypeViewSet, CurrencyViewSet, CustomerSegmentViewSet,
    EntityViewSet, FxRateViewSet, OffBalanceCommitmentViewSet,
    ProductMappingViewSet, RepricingBucketViewSet,
)

router = DefaultRouter()
router.register(r"currencies", CurrencyViewSet, basename="currency")
router.register(r"fx-rates", FxRateViewSet, basename="fxrate")
router.register(r"entities", EntityViewSet, basename="entity")
router.register(r"branches", BranchViewSet, basename="branch")
router.register(r"product-mappings", ProductMappingViewSet, basename="product-mapping")
router.register(r"repricing-buckets", RepricingBucketViewSet, basename="repricing-bucket")
router.register(r"segments", CustomerSegmentViewSet, basename="segment")
router.register(r"collaterals", CollateralTypeViewSet, basename="collateral")
router.register(r"off-balance", OffBalanceCommitmentViewSet, basename="off-balance")

urlpatterns = router.urls
