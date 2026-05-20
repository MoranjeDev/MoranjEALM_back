"""Vues DRF pour la gouvernance des hypothèses et la bibliothèque de scénarios."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from apps.accounts.permissions import HasHabilitation, IsValidator
from apps.tracking.models import Tracking
from .models import Assumption, AssumptionVersion, ScenarioLibrary
from .serializers import (
    AssumptionSerializer,
    AssumptionVersionSerializer,
    ScenarioLibrarySerializer,
)
from .services import ensure_standard_assumptions


class AssumptionViewSet(viewsets.ModelViewSet):
    queryset = Assumption.objects.all().prefetch_related("versions")
    serializer_class = AssumptionSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gouvernance hypothèses"
    filterset_fields = ["category", "owner"]
    search_fields = ["code", "label", "description"]

    def get_queryset(self):
        ensure_standard_assumptions()
        return Assumption.objects.all().prefetch_related("versions")

    @action(detail=True, methods=["post"], url_path="set-active-value")
    def set_active_value(self, request, pk=None):
        """Crée et active directement une nouvelle valeur depuis l'écran Hypothèses.

        Le workflow complet maker/checker reste disponible via les versions, mais
        cet endpoint rend les hypothèses standards réellement pilotables depuis le
        front pour les usages opérationnels.
        """
        assumption = self.get_object()
        raw_value = request.data.get("value")
        if raw_value in ("", None):
            return Response({"detail": "La valeur est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return Response({"detail": "La valeur doit être numérique."}, status=status.HTTP_400_BAD_REQUEST)

        last = assumption.versions.order_by("-version_number").first()
        next_n = (last.version_number + 1) if last else 1
        now = timezone.now()
        AssumptionVersion.objects.filter(
            assumption=assumption,
            state=AssumptionVersion.STATE_ACTIVE,
        ).update(state=AssumptionVersion.STATE_RETIRED, retired_at=now)
        version = AssumptionVersion.objects.create(
            assumption=assumption,
            version_number=next_n,
            value=value,
            payload=request.data.get("payload") or {},
            state=AssumptionVersion.STATE_ACTIVE,
            maker=request.user,
            approver=request.user,
            rationale=request.data.get("rationale") or "Mise à jour directe depuis la page Hypothèses.",
            approved_at=now,
            activated_at=now,
        )
        Tracking.objects.create(
            libelle="Activation hypothèse",
            description=f"{assumption.code} v{next_n} activée directement depuis le front.",
            utilisateur=request.user,
        )
        assumption.refresh_from_db()
        return Response(AssumptionSerializer(assumption).data)


class AssumptionVersionViewSet(viewsets.ModelViewSet):
    queryset = AssumptionVersion.objects.all().select_related(
        "assumption", "maker", "checker", "approver"
    )
    serializer_class = AssumptionVersionSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gouvernance hypothèses"
    filterset_fields = ["assumption", "state"]

    def perform_create(self, serializer):
        # Auto-numérotation
        ass = serializer.validated_data["assumption"]
        last = AssumptionVersion.objects.filter(assumption=ass).order_by(
            "-version_number"
        ).first()
        next_n = (last.version_number + 1) if last else 1
        version = serializer.save(
            version_number=next_n,
            maker=self.request.user,
        )
        Tracking.objects.create(
            libelle="Nouvelle hypothèse (brouillon)",
            description=f"{ass.code} v{next_n} créée par {self.request.user.username}.",
            utilisateur=self.request.user,
        )
        return version

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="submit")
    def submit_action(self, request, pk=None):
        v = self.get_object()
        try:
            v.submit(request.user)
            v.save()
        except Exception as e:  # noqa: BLE001
            return Response({"detail": str(e)}, status=400)
        Tracking.objects.create(
            libelle="Soumission hypothèse",
            description=f"{v.assumption.code} v{v.version_number} soumise pour revue.",
            utilisateur=request.user,
        )
        return Response(AssumptionVersionSerializer(v).data)

    @action(detail=True, methods=["post"], url_path="approve",
            permission_classes=[IsAuthenticated, IsValidator])
    def approve_action(self, request, pk=None):
        v = self.get_object()
        if v.maker_id == request.user.id:
            return Response(
                {"detail": "Le rédacteur ne peut pas approuver sa propre hypothèse."},
                status=400,
            )
        try:
            v.approve(request.user)
            v.save()
        except Exception as e:  # noqa: BLE001
            return Response({"detail": str(e)}, status=400)
        Tracking.objects.create(
            libelle="Approbation hypothèse",
            description=f"{v.assumption.code} v{v.version_number} approuvée.",
            utilisateur=request.user,
        )
        return Response(AssumptionVersionSerializer(v).data)

    @action(detail=True, methods=["post"], url_path="reject",
            permission_classes=[IsAuthenticated, IsValidator])
    def reject_action(self, request, pk=None):
        v = self.get_object()
        reason = request.data.get("reason", "")
        try:
            v.reject(request.user, reason=reason)
            v.save()
        except Exception as e:  # noqa: BLE001
            return Response({"detail": str(e)}, status=400)
        Tracking.objects.create(
            libelle="Rejet hypothèse",
            description=f"{v.assumption.code} v{v.version_number} rejetée : {reason}",
            utilisateur=request.user,
        )
        return Response(AssumptionVersionSerializer(v).data)

    @action(detail=True, methods=["post"], url_path="activate",
            permission_classes=[IsAuthenticated, IsValidator])
    def activate_action(self, request, pk=None):
        v = self.get_object()
        try:
            v.activate(request.user)
            v.save()
        except Exception as e:  # noqa: BLE001
            return Response({"detail": str(e)}, status=400)
        Tracking.objects.create(
            libelle="Activation hypothèse",
            description=f"{v.assumption.code} v{v.version_number} activée.",
            utilisateur=request.user,
        )
        return Response(AssumptionVersionSerializer(v).data)


class ScenarioLibraryViewSet(viewsets.ModelViewSet):
    queryset = ScenarioLibrary.objects.all()
    serializer_class = ScenarioLibrarySerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Stress Tests"
    filterset_fields = ["scope", "is_active"]
    search_fields = ["code", "label"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
