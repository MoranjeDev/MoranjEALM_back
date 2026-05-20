from django.urls import path
from .views import PositionsByCurrencyView

urlpatterns = [
    path("positions/", PositionsByCurrencyView.as_view(), name="multicurrency-positions"),
]
