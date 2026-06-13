from django.urls import path
from .views import PositionsByCurrencyView, BalanceSheetByCurrencyView, FxPositionView

urlpatterns = [
    path("positions/", PositionsByCurrencyView.as_view(), name="multicurrency-positions"),
    path("balance-sheet/", BalanceSheetByCurrencyView.as_view(), name="multicurrency-balance-sheet"),
    path("fx-position/", FxPositionView.as_view(), name="multicurrency-fx-position"),
]
