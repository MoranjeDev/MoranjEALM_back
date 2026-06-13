from django.urls import path
from .views import (
    ConcentrationEnrichedView,
    ConcentrationView,
    EVEEnrichedView,
    EVESensitivityView,
    NIISensitivityView,
    NIMView,
    ProfitabilityRatiosView,
)

urlpatterns = [
    path("nii/", NIISensitivityView.as_view(), name="analytics-nii"),
    path("eve/", EVESensitivityView.as_view(), name="analytics-eve"),
    path("eve-enriched/", EVEEnrichedView.as_view(), name="analytics-eve-enriched"),
    path("concentration/", ConcentrationView.as_view(), name="analytics-concentration"),
    path("concentration-enriched/", ConcentrationEnrichedView.as_view(), name="analytics-concentration-enriched"),
    path("nim/", NIMView.as_view(), name="analytics-nim"),
    path("profitability/", ProfitabilityRatiosView.as_view(), name="analytics-profitability"),
]
