from datetime import datetime
import logging

from django.db import DatabaseError
from django.db.models import Q
from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from apps.tracking.models import Tracking

from .alco_pdf import build_alco_pdf
from .models import ReportAnnotation, ReportRun, ReportTemplate
from .pptx_export import DEFAULT_SECTIONS, build_alco_pptx
from .report_pdf import REPORTS, build_report_pdf
from .serializers import ReportAnnotationSerializer, ReportRunSerializer, ReportTemplateSerializer
from .template_pdf import build_template_pdf
from .versioning import report_version_snapshot


logger = logging.getLogger(__name__)


def _safe_report_run_create(**kwargs):
    """Ne jamais bloquer un export si la table d'historique reporting est indisponible."""
    try:
        return ReportRun.objects.create(**kwargs)
    except DatabaseError as exc:
        logger.warning("Historique ReportRun indisponible: %s", exc)
    return None


def _safe_tracking_create(**kwargs):
    """L'audit est utile, mais ne doit pas empêcher une action métier."""
    try:
        return Tracking.objects.create(**kwargs)
    except DatabaseError as exc:
        logger.warning("Journal Tracking indisponible: %s", exc)
    return None


def _audit_parameters(
    *,
    report_kind: str,
    file_format: str,
    params: dict | None = None,
    sections: list[str] | None = None,
    template: ReportTemplate | None = None,
) -> dict:
    """Paramètres figés dans ReportRun pour expliquer un export a posteriori."""
    params = params or {}
    try:
        snapshot = report_version_snapshot(report_kind, params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Snapshot de version reporting indisponible: %s", exc)
        snapshot = {}
    return {
        **params,
        "report_kind": report_kind,
        "file_format": file_format,
        "sections": sections or [],
        "template_code": template.code if template else "",
        "template_label": template.label if template else "",
        "model_version": snapshot.get("app_version"),
        "assumptions_digest": snapshot.get("assumptions_digest"),
        "assumptions_count": snapshot.get("assumptions_count"),
        "scenarios_count": snapshot.get("scenarios_count"),
        "active_assumptions": snapshot.get("assumptions", []),
        "active_scenarios": snapshot.get("scenarios", []),
    }


class ReportTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"
    filterset_fields = ["scope", "is_active"]

    def get_queryset(self):
        queryset = ReportTemplate.objects.select_related("created_by")
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset
        return queryset.filter(Q(created_by=user) | Q(is_shared=True) | Q(created_by__isnull=True))

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _ensure_template_editable(self, template):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return
        if template.created_by_id != user.id:
            raise PermissionDenied("Ce template appartient à un autre utilisateur.")

    def perform_update(self, serializer):
        self._ensure_template_editable(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_template_editable(instance)
        instance.delete()


class ReportRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReportRun.objects.all().select_related(
        "template",
        "requested_by",
        "submitted_by",
        "certified_by",
        "rejected_by",
    )
    serializer_class = ReportRunSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"

    def _comment(self):
        return (self.request.data.get("comment") or "").strip()

    def _serialize(self, run):
        return Response(self.get_serializer(run).data)

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except DatabaseError as exc:
            logger.warning("Historique des rapports indisponible: %s", exc)
            return Response({"count": 0, "next": None, "previous": None, "results": []})

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        run = self.get_object()
        try:
            run.submit(request.user, self._comment())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _safe_tracking_create(
            libelle="Rapport soumis",
            description=f"Rapport #{run.id} soumis pour validation.",
            utilisateur=request.user,
        )
        return self._serialize(run)

    @action(detail=True, methods=["post"], url_path="certify")
    def certify(self, request, pk=None):
        run = self.get_object()
        if (
            run.requested_by_id == request.user.id
            and not (request.user.is_staff or request.user.is_superuser)
        ):
            return Response(
                {"detail": "Maker-checker : le générateur ne peut pas valider son propre rapport."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            run.certify(request.user, self._comment())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _safe_tracking_create(
            libelle="Rapport validé",
            description=f"Rapport #{run.id} validé/certifié.",
            utilisateur=request.user,
        )
        return self._serialize(run)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        run = self.get_object()
        if (
            run.requested_by_id == request.user.id
            and not (request.user.is_staff or request.user.is_superuser)
        ):
            return Response(
                {"detail": "Maker-checker : le générateur ne peut pas rejeter son propre rapport."},
                status=status.HTTP_403_FORBIDDEN,
            )
        comment = self._comment()
        if not comment:
            return Response(
                {"detail": "Le motif de rejet est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            run.reject(request.user, comment)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _safe_tracking_create(
            libelle="Rapport rejeté",
            description=f"Rapport #{run.id} rejeté : {comment}",
            utilisateur=request.user,
        )
        return self._serialize(run)


class ReportAnnotationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Commentaires versionnés par section de rapport."""

    serializer_class = ReportAnnotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ReportAnnotation.objects.select_related("created_by")
        section = (self.request.query_params.get("section") or "").strip()
        scenario = self.request.query_params.get("scenario")
        if section:
            queryset = queryset.filter(section=section)
        if scenario is not None:
            queryset = queryset.filter(scenario=scenario.strip())
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except DatabaseError as exc:
            logger.warning("Annotations reporting indisponibles: %s", exc)
            return Response({"count": 0, "next": None, "previous": None, "results": []})

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except DatabaseError as exc:
            logger.warning("Création annotation reporting indisponible: %s", exc)
            return Response(
                {
                    "detail": (
                        "Les commentaires de rapport sont indisponibles. "
                        "Appliquez les migrations reporting pour activer l'historique."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    def perform_create(self, serializer):
        annotation = serializer.save(created_by=self.request.user)
        _safe_tracking_create(
            libelle="Annotation rapport",
            description=(
                f"Annotation créée pour {annotation.section}"
                f"{' / ' + annotation.scenario if annotation.scenario else ''}."
            ),
            utilisateur=self.request.user,
        )


class ALCOPptxExportView(APIView):
    """Génère et télécharge un .pptx ALCO."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"

    def get(self, request):
        template_id = request.query_params.get("template")
        sections = DEFAULT_SECTIONS
        template = None
        if template_id:
            try:
                template_qs = ReportTemplate.objects.all()
                if not (request.user.is_staff or request.user.is_superuser):
                    template_qs = template_qs.filter(
                        Q(created_by=request.user) | Q(is_shared=True) | Q(created_by__isnull=True)
                    )
                template = template_qs.get(pk=template_id)
                if template.sections:
                    sections = template.sections
            except ReportTemplate.DoesNotExist:
                return HttpResponse(status=404)

        audit_params = _audit_parameters(
            report_kind="alco_pptx",
            file_format="pptx",
            sections=sections,
            template=template,
        )
        try:
            content = build_alco_pptx(sections)
        except Exception as e:  # noqa: BLE001
            _safe_report_run_create(
                template=template,
                requested_by=request.user,
                parameters=audit_params,
                file_format="pptx",
                status="error",
                error=str(e),
            )
            return HttpResponse(f"Erreur génération : {e}", status=500)

        _safe_report_run_create(
            template=template,
            requested_by=request.user,
            parameters=audit_params,
            file_format="pptx",
            status="success",
        )
        _safe_tracking_create(
            libelle="Export ALCO PPTX",
            description=f"Export ALCO ({len(sections)} sections).",
            utilisateur=request.user,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        response["Content-Disposition"] = f'attachment; filename="alco_{ts}.pptx"'
        return response


class ALCOPdfView(APIView):
    """
    Génère et télécharge un PDF du rapport ALCO pour un scénario donné.
    Le PDF inclut un watermark avec le nom de l'utilisateur et la date,
    ce qui permet de tracer l'exemplaire si une copie circule en dehors
    de l'organisation cliente.
    """
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Rapports"

    def get(self, request):
        scenario = request.query_params.get("scenario", "base")
        if scenario not in ("base", "modere", "severe"):
            return HttpResponse(
                f"Scénario inconnu : {scenario}",
                status=400,
            )

        # Identifiant traçable de l'utilisateur (nom complet ou username)
        user = request.user
        full_name = (f"{user.first_name} {user.last_name}").strip()
        user_label = full_name or user.username or "utilisateur inconnu"

        audit_params = _audit_parameters(
            report_kind="alco_pdf",
            file_format="pdf",
            params={"scenario": scenario},
        )
        try:
            content = build_alco_pdf(scenario, user_label=user_label)
        except Exception as e:  # noqa: BLE001
            _safe_report_run_create(
                requested_by=user,
                parameters=audit_params,
                file_format="pdf",
                status="error",
                error=str(e),
            )
            _safe_tracking_create(
                libelle="Export ALCO PDF échec",
                description=f"Erreur génération PDF ({scenario}) : {e}",
                utilisateur=user,
            )
            return HttpResponse(f"Erreur génération PDF : {e}", status=500)

        _safe_report_run_create(
            requested_by=user,
            parameters=audit_params,
            file_format="pdf",
            status="success",
        )
        _safe_tracking_create(
            libelle="Export ALCO PDF",
            description=f"Téléchargement PDF ALCO scénario={scenario}.",
            utilisateur=user,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="alco_{scenario}_{ts}.pdf"'
        )
        # Empêche la mise en cache du navigateur (chaque PDF est unique au user)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response


class GenericReportPdfView(APIView):
    """Génère un PDF pour les rapports analytiques de l'application."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        report_type = request.query_params.get("type", "")
        if report_type not in REPORTS:
            return HttpResponse(f"Type de rapport inconnu : {report_type}", status=400)

        required = REPORTS[report_type]["permission"]
        if not request.user.has_habilitation(required):
            return HttpResponse("Habilitation insuffisante.", status=403)

        user = request.user
        full_name = (f"{user.first_name} {user.last_name}").strip()
        user_label = full_name or user.username or "utilisateur inconnu"

        params = dict(request.query_params.items())
        audit_params = _audit_parameters(
            report_kind=report_type,
            file_format="pdf",
            params=params,
        )
        try:
            content = build_report_pdf(
                report_type,
                params,
                user_label=user_label,
            )
        except Exception as e:  # noqa: BLE001
            _safe_report_run_create(
                requested_by=user,
                parameters=audit_params,
                file_format="pdf",
                status="error",
                error=str(e),
            )
            _safe_tracking_create(
                libelle="Export PDF échec",
                description=f"Erreur génération PDF ({report_type}) : {e}",
                utilisateur=user,
            )
            return HttpResponse(f"Erreur génération PDF : {e}", status=500)

        _safe_report_run_create(
            requested_by=user,
            parameters=audit_params,
            file_format="pdf",
            status="success",
        )
        _safe_tracking_create(
            libelle="Export PDF",
            description=f"Téléchargement PDF rapport={report_type}.",
            utilisateur=user,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{report_type}_{ts}.pdf"'
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response


class TemplatePdfExportView(APIView):
    """Génère un PDF multi-sections depuis un ReportTemplate sauvegardé."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"

    def get(self, request):
        template_id = request.query_params.get("template")
        if not template_id:
            return HttpResponse("Paramètre template obligatoire.", status=400)

        template_qs = ReportTemplate.objects.all()
        if not (request.user.is_staff or request.user.is_superuser):
            template_qs = template_qs.filter(
                Q(created_by=request.user) | Q(is_shared=True) | Q(created_by__isnull=True)
            )
        try:
            template = template_qs.get(pk=template_id)
        except ReportTemplate.DoesNotExist:
            return HttpResponse(status=404)

        user = request.user
        full_name = (f"{user.first_name} {user.last_name}").strip()
        user_label = full_name or user.username or "utilisateur inconnu"
        params = dict(request.query_params.items())

        audit_params = _audit_parameters(
            report_kind="template_pdf",
            file_format="pdf",
            params=params,
            sections=template.sections,
            template=template,
        )
        try:
            content = build_template_pdf(template, params, user_label=user_label)
        except Exception as e:  # noqa: BLE001
            _safe_report_run_create(
                template=template,
                requested_by=user,
                parameters=audit_params,
                file_format="pdf",
                status="error",
                error=str(e),
            )
            _safe_tracking_create(
                libelle="Export template PDF échec",
                description=f"Erreur génération template PDF ({template.code}) : {e}",
                utilisateur=user,
            )
            return HttpResponse(f"Erreur génération PDF template : {e}", status=500)

        _safe_report_run_create(
            template=template,
            requested_by=user,
            parameters=audit_params,
            file_format="pdf",
            status="success",
        )
        _safe_tracking_create(
            libelle="Export template PDF",
            description=f"Téléchargement PDF template={template.code}.",
            utilisateur=user,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{template.code}_{ts}.pdf"'
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response
