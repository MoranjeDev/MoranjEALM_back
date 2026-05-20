from django.urls import path

from .views import (
    ChartsView,
    LCRView,
    OutputsSummaryView,
    RateGapView,
    RegenerateOutputsView,
    SynthesisView,
)

urlpatterns = [
    path("regenerate/", RegenerateOutputsView.as_view(), name="engine-regenerate"),
    path("outputs-summary/", OutputsSummaryView.as_view(), name="engine-outputs-summary"),
    path("synthesis/", SynthesisView.as_view(), name="engine-synthesis"),
    path("lcr/", LCRView.as_view(), name="engine-lcr"),
    path("rate-gap/", RateGapView.as_view(), name="engine-rate-gap"),
    path("charts/", ChartsView.as_view(), name="engine-charts"),
]
