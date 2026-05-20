from rest_framework.routers import DefaultRouter
from .views import AssumptionViewSet, AssumptionVersionViewSet, ScenarioLibraryViewSet

router = DefaultRouter()
router.register(r"assumptions", AssumptionViewSet, basename="assumption")
router.register(r"versions", AssumptionVersionViewSet, basename="assumption-version")
router.register(r"scenarios", ScenarioLibraryViewSet, basename="scenario")

urlpatterns = router.urls
