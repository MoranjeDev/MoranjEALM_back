from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ALCOPdfView,
    ALCOPptxExportView,
    GenericReportPdfView,
    ReportRunViewSet,
    ReportTemplateViewSet,
)

router = DefaultRouter()
router.register(r"templates", ReportTemplateViewSet, basename="report-template")
router.register(r"runs", ReportRunViewSet, basename="report-run")

urlpatterns = [
    path("alco-pptx/", ALCOPptxExportView.as_view(), name="alco-pptx"),
    path("alco-pdf/", ALCOPdfView.as_view(), name="alco-pdf"),
    path("pdf/", GenericReportPdfView.as_view(), name="report-pdf"),
] + router.urls
