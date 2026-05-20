"""ViewSets pour tous les modules d'inputs.

Une seule classe générique InputViewSet, instanciée pour chaque modèle.
Les routes URL sont assemblées dans urls.py.
"""
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import HasHabilitation
from apps.tracking.models import Tracking

from .models import INPUT_MODELS, INPUT_LABELS, Output
from .sample_data import SAMPLE_DATA
from .serializers import INPUT_SERIALIZERS, OutputSerializer


class InputViewSet(viewsets.ModelViewSet):
    """
    ViewSet générique pour les inputs ALM.
    Configurer la sous-classe avec :
      - kind = "credit" / "bta" / ...
    """
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Liquidity Gap"  # Habilitation minimale pour CRUD inputs
    filter_backends = []  # Ajouté dynamiquement par get_queryset/filter

    kind: str = ""

    def get_queryset(self):
        return INPUT_MODELS[self.kind].objects.all().order_by("-created_at")

    def get_serializer_class(self):
        return INPUT_SERIALIZERS[self.kind]

    def perform_create(self, serializer):
        instance = serializer.save()
        Tracking.objects.create(
            libelle=f"Création {self.kind}",
            description=f"Création d'un input {self.kind} (id={instance.pk}).",
            utilisateur=self.request.user,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        Tracking.objects.create(
            libelle=f"Modification {self.kind}",
            description=f"Modification d'un input {self.kind} (id={instance.pk}).",
            utilisateur=self.request.user,
        )

    def perform_destroy(self, instance):
        pk = instance.pk
        instance.delete()
        Tracking.objects.create(
            libelle=f"Suppression {self.kind}",
            description=f"Suppression d'un input {self.kind} (id={pk}).",
            utilisateur=self.request.user,
        )

    @action(detail=False, methods=["post"], url_path="load-sample")
    def load_sample(self, request):
        """Charge le jeu de données de test pour ce module uniquement.
        Body optionnel : {"reset": true} pour vider d'abord la table.
        """
        if self.kind not in SAMPLE_DATA:
            return Response(
                {"detail": f"Aucun échantillon disponible pour « {self.kind} »."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        model = INPUT_MODELS[self.kind]
        samples = SAMPLE_DATA[self.kind]
        reset = bool(request.data.get("reset", False))

        with transaction.atomic():
            deleted = 0
            if reset:
                deleted, _ = model.objects.all().delete()
            objs = [model(**s) for s in samples]
            model.objects.bulk_create(objs, batch_size=500)

        Tracking.objects.create(
            libelle=f"Chargement données test {self.kind}",
            description=(
                f"{len(objs)} ligne(s) de test chargée(s) pour {self.kind}, "
                f"{deleted} ligne(s) supprimée(s) au préalable."
            ),
            utilisateur=request.user,
        )
        return Response({
            "kind": self.kind,
            "inserted": len(objs),
            "deleted": deleted,
        })


def make_input_viewset(kind: str) -> type[InputViewSet]:
    """Fabrique une sous-classe InputViewSet liée à un type d'input."""
    return type(
        f"{kind.capitalize()}ViewSet",
        (InputViewSet,),
        {"kind": kind},
    )


# Mapping kind -> ViewSet class
INPUT_VIEWSETS = {kind: make_input_viewset(kind) for kind in INPUT_MODELS}


# ============================================================================
# Catalogue des inputs (pour le dashboard)
# ============================================================================
class InputsCatalogView(viewsets.ViewSet):
    """Expose la liste des inputs disponibles avec leurs métadonnées."""
    permission_classes = [IsAuthenticated]

    def list(self, request):
        result = []
        for kind, model in INPUT_MODELS.items():
            label, side = INPUT_LABELS.get(kind, (kind, "actif"))
            result.append({
                "kind": kind,
                "label": label,
                "side": side,            # "actif" ou "passif"
                "category": getattr(model, "CATEGORY", "core"),
                "count": model.objects.count(),
                "endpoint": f"/api/inputs/{kind}/",
            })
        return Response(result)


# ============================================================================
# Output (lecture seule pour la phase 2 ; écriture en phase 3 par le moteur)
# ============================================================================
class OutputViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Output.objects.all()
    serializer_class = OutputSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["type_output"]
    ordering = ["-date"]

    @action(detail=False, methods=["get"], url_path="types")
    def types(self, request):
        types = list(Output.objects.values_list("type_output", flat=True).distinct())
        return Response(sorted(types))
