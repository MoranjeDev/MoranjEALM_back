from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasHabilitation
from .models import Tracking
from .serializers import TrackingSerializer


class TrackingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Lecture seule du journal d'audit."""
    queryset = Tracking.objects.all().select_related("utilisateur")
    serializer_class = TrackingSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["libelle", "utilisateur"]
    search_fields = ["libelle", "description"]
    ordering_fields = ["horodatage"]
