"""URLs des modules d'inputs ALM."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .import_views import ExcelImportView, ExcelTemplateView
from .views import INPUT_VIEWSETS, InputsCatalogView, OutputViewSet

router = DefaultRouter()
for kind, viewset_cls in INPUT_VIEWSETS.items():
    router.register(rf"{kind}", viewset_cls, basename=f"input-{kind}")

router.register(r"outputs", OutputViewSet, basename="output")

urlpatterns = [
    path("catalog/", InputsCatalogView.as_view({"get": "list"}), name="inputs-catalog"),
    path("import/", ExcelImportView.as_view(), name="inputs-import"),
    path("template/", ExcelTemplateView.as_view(), name="inputs-template"),
] + router.urls
