from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, serializers
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
import io

from apps.accounts.permissions import HasHabilitation
from .models import ClientMapping
from .analysis import compute_mis_analysis, compute_mis_export_excel


class ClientMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientMapping
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ClientMappingViewSet(viewsets.ModelViewSet):
    """CRUD pour le mapping client MIS."""
    queryset = ClientMapping.objects.all().order_by("business_unit", "segment", "client_id")
    serializer_class = ClientMappingSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"
    filterset_fields = ["segment", "business_unit", "secteur", "is_active"]

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def import_excel(self, request):
        """POST multipart : importe un fichier Excel de mapping clients."""
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "Fichier manquant."}, status=400)
        from .import_service import import_client_mapping_excel
        report = import_client_mapping_excel(file)
        return Response({
            "inserted": report.inserted,
            "updated": report.updated,
            "errors": report.errors,
        })

    @action(detail=False, methods=["get"])
    def template(self, request):
        """GET : télécharge le template Excel vierge."""
        from .template_service import generate_client_mapping_template
        wb = generate_client_mapping_template()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            'attachment; filename="template_mapping_clients.xlsx"'
        )
        return response


class MISAnalysisView(APIView):
    """GET : tableau croisé MIS par BU / segment / secteur."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        group_by = request.query_params.get("group_by", "business_unit")
        date_arrete = request.query_params.get("date_arrete")
        business_unit = request.query_params.get("business_unit")
        segment = request.query_params.get("segment")
        devise = request.query_params.get("devise")
        return Response(compute_mis_analysis(
            group_by=group_by,
            date_arrete=date_arrete,
            business_unit=business_unit,
            segment=segment,
            devise=devise,
        ))


class MISExportView(APIView):
    """GET : export Excel du tableau MIS."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        group_by = request.query_params.get("group_by", "business_unit")
        date_arrete = request.query_params.get("date_arrete")
        wb = compute_mis_export_excel(group_by=group_by, date_arrete=date_arrete)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="mis_{group_by}.xlsx"'
        )
        return response
