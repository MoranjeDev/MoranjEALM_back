from django.urls import path
from .views import OffBalanceImportView, OffBalanceTemplateView, OffBalanceListView

urlpatterns = [
    path("import/", OffBalanceImportView.as_view(), name="off-balance-import"),
    path("template/", OffBalanceTemplateView.as_view(), name="off-balance-template"),
    path("", OffBalanceListView.as_view(), name="off-balance-list"),
]
