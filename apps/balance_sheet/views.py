import io

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasHabilitation
from .models import BalanceSheetLine
from .import_service import import_balance_sheet_excel
from .template_service import generate_balance_sheet_template


class BalanceSheetListView(APIView):
    """GET : liste paginée des lignes de bilan GL importées."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        qs = BalanceSheetLine.objects.all()

        date_arrete = request.query_params.get("date_arrete")
        sens = request.query_params.get("sens")
        devise = request.query_params.get("devise")
        business_unit = request.query_params.get("business_unit")
        segment = request.query_params.get("segment")
        sous_segment = request.query_params.get("sous_segment")
        secteur = request.query_params.get("secteur")
        entite = request.query_params.get("entite")
        type_taux = request.query_params.get("type_taux")
        search = request.query_params.get("search")

        if date_arrete:
            qs = qs.filter(date_arrete=date_arrete)
        if sens:
            qs = qs.filter(sens=sens)
        if devise:
            qs = qs.filter(devise=devise)
        if business_unit:
            qs = qs.filter(business_unit=business_unit)
        if segment:
            qs = qs.filter(segment=segment)
        if sous_segment:
            qs = qs.filter(sous_segment=sous_segment)
        if secteur:
            qs = qs.filter(secteur=secteur)
        if entite:
            qs = qs.filter(entite=entite)
        if type_taux:
            qs = qs.filter(type_taux=type_taux)
        if search:
            qs = qs.filter(
                Q(compte_gl__icontains=search)
                | Q(libelle__icontains=search)
                | Q(product_code__icontains=search)
                | Q(client_id__icontains=search)
                | Q(client_name__icontains=search)
            )

        summary = qs.aggregate(
            total_lcy=Sum("montant_lcy"),
            total_fcy=Sum("montant_fcy"),
            lines=Count("id"),
        )
        by_sens = {
            row["sens"]: {
                "montant_lcy": row["montant_lcy"] or 0,
                "montant_fcy": row["montant_fcy"] or 0,
                "lines": row["lines"],
            }
            for row in qs.values("sens").annotate(
                montant_lcy=Sum("montant_lcy"),
                montant_fcy=Sum("montant_fcy"),
                lines=Count("id"),
            )
        }
        by_currency = list(
            qs.values("devise").annotate(
                montant_lcy=Sum("montant_lcy"),
                montant_fcy=Sum("montant_fcy"),
                lines=Count("id"),
            ).order_by("devise")
        )

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
                "total_lcy": summary["total_lcy"] or 0,
                "total_fcy": summary["total_fcy"] or 0,
                "lines": summary["lines"] or 0,
                "by_sens": by_sens,
                "by_currency": by_currency,
            },
            "results": list(page.object_list),
        })


class BalanceSheetImportView(APIView):
    """POST multipart : importe un fichier Excel de bilan GL."""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "Fichier manquant."}, status=400)
        replace = request.data.get("replace", "0") == "1"
        report = import_balance_sheet_excel(file, replace=replace)
        return Response({
            "inserted": report.total_inserted,
            "errors": report.total_errors,
            "sheets": [
                {
                    "kind": sheet.kind,
                    "inserted": sheet.inserted,
                    "skipped": sheet.skipped,
                    "errors": sheet.errors,
                }
                for sheet in report.sheets
            ],
        })


class BalanceSheetTemplateView(APIView):
    """GET : télécharge le template Excel vierge du bilan GL."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wb = generate_balance_sheet_template()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="template_bilan_gl.xlsx"'
        return response


BalanceSheetLineListView = BalanceSheetListView


class BalanceSheetReconciliationView(APIView):
    """GET : rapprochement bilan GL vs inputs ALM."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        from .reconciliation import compute_reconciliation
        date_arrete = request.query_params.get("date_arrete")
        return Response(compute_reconciliation(date_arrete=date_arrete))


class BalanceSheetAverageView(APIView):
    """GET ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD : bilan moyen sur la période."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Résultats"

    def get(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if not date_from or not date_to:
            return Response(
                {"detail": "Paramètres date_from et date_to obligatoires."},
                status=400,
            )
        from .average_service import compute_average_balance_sheet
        return Response(compute_average_balance_sheet(date_from, date_to))
