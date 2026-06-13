from django.urls import path
from . import views

urlpatterns = [
    path("",                 views.BalanceSheetListView.as_view(),            name="balance-sheet-list"),
    path("import/",          views.BalanceSheetImportView.as_view(),          name="balance-sheet-import"),
    path("template/",        views.BalanceSheetTemplateView.as_view(),        name="balance-sheet-template"),
    path("reconciliation/",  views.BalanceSheetReconciliationView.as_view(),  name="balance-sheet-reconciliation"),
    path("average/",         views.BalanceSheetAverageView.as_view(),         name="balance-sheet-average"),
]
