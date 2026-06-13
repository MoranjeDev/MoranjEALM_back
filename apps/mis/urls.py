from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ClientMappingViewSet, MISAnalysisView, MISExportView

router = DefaultRouter()
router.register(r"clients", ClientMappingViewSet, basename="client-mapping")

urlpatterns = [
    path("analysis/", MISAnalysisView.as_view(), name="mis-analysis"),
    path("export/", MISExportView.as_view(), name="mis-export"),
] + router.urls
