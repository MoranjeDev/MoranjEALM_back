from django.urls import path

from .views import (
    BehavioralParamsDebugView,
    DataQualityDetailView,
    ChartsView,
    DataQualityView,
    LCRView,
    MCOView,
    OffBalanceSynthesisView,
    OutputsSummaryView,
    RateGapByTypeView,
    RateGapView,
    RegenerateOutputsView,
    SynthesisView,
    ScenarioAnalysisView,
)

urlpatterns = [
    path("regenerate/", RegenerateOutputsView.as_view(), name="engine-regenerate"),
    path("data-quality/", DataQualityView.as_view(), name="engine-data-quality"),
    path("data-quality/<str:kind>/", DataQualityDetailView.as_view(), name="engine-data-quality-detail"),
    path("outputs-summary/", OutputsSummaryView.as_view(), name="engine-outputs-summary"),
    path("synthesis/", SynthesisView.as_view(), name="engine-synthesis"),
    path("lcr/", LCRView.as_view(), name="engine-lcr"),
    path("rate-gap/", RateGapView.as_view(), name="engine-rate-gap"),
    path("rate-gap-by-type/", RateGapByTypeView.as_view(), name="engine-rate-gap-by-type"),
    path("charts/", ChartsView.as_view(), name="engine-charts"),
    path("off-balance-flows/", OffBalanceSynthesisView.as_view(), name="engine-off-balance-flows"),
    path("mco/", MCOView.as_view(), name="engine-mco"),
    path("behavioral-params/", BehavioralParamsDebugView.as_view(), name="engine-behavioral-params"),
    path("scenario-analysis/", ScenarioAnalysisView.as_view(), name="engine-scenario-analysis"),
]
