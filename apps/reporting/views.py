from datetime import datetime

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from apps.tracking.models import Tracking

from .alco_pdf import build_alco_pdf
from .models import ReportRun, ReportTemplate
from .pptx_export import DEFAULT_SECTIONS, build_alco_pptx
from .report_pdf import REPORTS, build_report_pdf
from .serializers import ReportRunSerializer, ReportTemplateSerializer


class ReportTemplateViewSet(viewsets.ModelViewSet):
    queryset = ReportTemplate.objects.all()
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"
    filterset_fields = ["scope", "is_active"]


class ReportRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReportRun.objects.all().select_related("template", "requested_by")
    serializer_class = ReportRunSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Tableaux de bord ALCO"


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
                template = ReportTemplate.objects.get(pk=template_id)
                if template.sections:
                    sections = template.sections
            except ReportTemplate.DoesNotExist:
                return HttpResponse(status=404)

        try:
            content = build_alco_pptx(sections)
            ReportRun.objects.create(
                template=template,
                requested_by=request.user,
                parameters={"sections": sections},
                status="success",
            )
            Tracking.objects.create(
                libelle="Export ALCO PPTX",
                description=f"Export ALCO ({len(sections)} sections).",
                utilisateur=request.user,
            )
        except Exception as e:  # noqa: BLE001
            ReportRun.objects.create(
                template=template,
                requested_by=request.user,
                status="error",
                error=str(e),
            )
            return HttpResponse(f"Erreur génération : {e}", status=500)

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

        try:
            content = build_alco_pdf(scenario, user_label=user_label)
        except Exception as e:  # noqa: BLE001
            Tracking.objects.create(
                libelle="Export ALCO PDF échec",
                description=f"Erreur génération PDF ({scenario}) : {e}",
                utilisateur=user,
            )
            return HttpResponse(f"Erreur génération PDF : {e}", status=500)

        Tracking.objects.create(
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

        try:
            content = build_report_pdf(
                report_type,
                dict(request.query_params.items()),
                user_label=user_label,
            )
        except Exception as e:  # noqa: BLE001
            Tracking.objects.create(
                libelle="Export PDF échec",
                description=f"Erreur génération PDF ({report_type}) : {e}",
                utilisateur=user,
            )
            return HttpResponse(f"Erreur génération PDF : {e}", status=500)

        Tracking.objects.create(
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
