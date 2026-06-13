"""URLs racine du projet MoranjEALM."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # API
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls_auth")),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/tracking/", include("apps.tracking.urls")),
    path("api/inputs/", include("apps.inputs.urls")),
    path("api/parameters/", include("apps.parameters.urls")),
    path("api/engine/", include("apps.engine.urls")),
    path("api/governance/", include("apps.governance.urls")),
    path("api/behavioral/", include("apps.behavioral.urls")),
    path("api/mapping/", include("apps.mapping.urls")),
    path("api/multicurrency/", include("apps.multicurrency.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/ftp/", include("apps.ftp.urls")),
    path("api/reporting/", include("apps.reporting.urls")),
    path("api/licensing/", include("apps.licensing.urls")),
    path("api/balance-sheet/", include("apps.balance_sheet.urls")),
    path("api/off-balance/", include("apps.off_balance.urls")),
    path("api/mis/", include("apps.mis.urls")),

    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
