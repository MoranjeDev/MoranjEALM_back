from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.http import HttpResponse
import io

from apps.accounts.permissions import HasHabilitation
from .models import OffBalanceSheetItem
from .import_service import import_off_balance_excel
from .template_service import generate_off_balance_template


class OffBalanceImportView(APIView):
    """POST multipart : importe un fichier Excel d'engagements hors-bilan."""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "Fichier manquant."}, status=400)
        replace = request.data.get("replace", "0") == "1"
        report = import_off_balance_excel(file, replace=replace)
        return Response({
            "inserted": report.total_inserted,
            "errors": report.total_errors,
            "sheets": [
                {
                    "kind": s.kind,
                    "inserted": s.inserted,
                    "skipped": s.skipped,
                    "errors": s.errors,
                }
                for s in report.sheets
            ],
        })


class OffBalanceTemplateView(APIView):
    """GET : télécharge le template Excel vierge."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wb = generate_off_balance_template()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(buf.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="template_hors_bilan.xlsx"'
        return response


class OffBalanceListView(APIView):
    """GET : liste paginée des engagements hors-bilan importés."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from django.core.paginator import Paginator
        date_arrete = request.query_params.get("date_arrete")
        type_engagement = request.query_params.get("type_engagement")
        devise = request.query_params.get("devise")
        segment = request.query_params.get("segment")
        business_unit = request.query_params.get("business_unit")
        search = request.query_params.get("search")
        qs = OffBalanceSheetItem.objects.all()
        if date_arrete:
            qs = qs.filter(date_arrete=date_arrete)
        if type_engagement:
            qs = qs.filter(type_engagement=type_engagement)
        if devise:
            qs = qs.filter(devise=devise)
        if segment:
            qs = qs.filter(segment=segment)
        if business_unit:
            qs = qs.filter(business_unit=business_unit)
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(description__icontains=search)
                | Q(client_id__icontains=search)
                | Q(client_name__icontains=search)
            )
        summary_qs = qs
        summary = summary_qs.aggregate(
            total_notionnel=Sum("notionnel"),
            total_utilise=Sum("montant_utilise"),
        )
        weighted_drawdown = 0
        for item in summary_qs.only("notionnel", "prob_tirage_pct"):
            weighted_drawdown += int(item.notionnel * item.prob_tirage_pct / 100)

        page_num = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 100)), 500)
        paginator = Paginator(qs.values(), page_size)
        page = paginator.get_page(page_num)
        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "page": page.number,
            "page_size": page_size,
            "summary": {
                "total_notionnel": summary["total_notionnel"] or 0,
                "total_utilise": summary["total_utilise"] or 0,
                "total_pondere_tirage": weighted_drawdown,
            },
            "results": list(page.object_list)
        })
