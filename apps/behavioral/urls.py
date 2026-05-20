from rest_framework.routers import DefaultRouter
from .views import (
    EarlyWithdrawalModelViewSet,
    EmbeddedOptionViewSet,
    NmdModelViewSet,
    PrepaymentModelViewSet,
    RolloverModelViewSet,
)

router = DefaultRouter()
router.register(r"nmd", NmdModelViewSet, basename="nmd")
router.register(r"prepayment", PrepaymentModelViewSet, basename="prepayment")
router.register(r"withdrawal", EarlyWithdrawalModelViewSet, basename="withdrawal")
router.register(r"rollover", RolloverModelViewSet, basename="rollover")
router.register(r"options", EmbeddedOptionViewSet, basename="options")

urlpatterns = router.urls
