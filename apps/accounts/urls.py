"""URLs CRUD administration utilisateurs/groupes/habilitations."""
from rest_framework.routers import DefaultRouter

from .views import GroupeUserViewSet, HabilitationViewSet, UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"groupes", GroupeUserViewSet, basename="groupe")
router.register(r"habilitations", HabilitationViewSet, basename="habilitation")

urlpatterns = router.urls
