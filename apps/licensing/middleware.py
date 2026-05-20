"""
Middleware Django : impose le statut de licence sur chaque requête API.

- Si state == OK ou GRACE : laisse passer.
- Si state == READONLY : autorise GET, refuse POST/PUT/PATCH/DELETE (403).
- Si state == BLOCKED : 423 Locked sur toutes les routes API sauf /licensing/.
- Si state == UNCONFIGURED : 503 sauf sur /admin et /licensing.

Bypass : si settings.LICENSE_BYPASS=True (typiquement en développement),
toutes les requêtes passent. À ne JAMAIS activer en production.
"""
from django.conf import settings
from django.http import JsonResponse

from .models import LicenseState


# Chemins toujours autorisés (auth, licence, santé)
ALLOWED_ALWAYS = (
    "/api/health/",
    "/api/info/",
    "/api/licensing/",
    "/api/auth/",
    "/admin/",
    "/static/",
)


class LicenseEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass complet en dev (settings.LICENSE_BYPASS = True)
        if getattr(settings, "LICENSE_BYPASS", False):
            return self.get_response(request)

        path = request.path
        if any(path.startswith(p) for p in ALLOWED_ALWAYS):
            return self.get_response(request)
        if not path.startswith("/api/"):
            return self.get_response(request)

        try:
            state = LicenseState.get_solo()
        except Exception:  # noqa: BLE001 — table pas encore migrée
            return self.get_response(request)

        if state.state in (LicenseState.STATE_OK, LicenseState.STATE_GRACE):
            return self.get_response(request)

        if state.state == LicenseState.STATE_READONLY:
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return self.get_response(request)
            return JsonResponse(
                {"detail": "Licence en mode lecture seule. Contactez l'éditeur."},
                status=403,
            )

        if state.state == LicenseState.STATE_BLOCKED:
            return JsonResponse(
                {"detail": "Licence bloquée. " + (state.last_contact_error or "")},
                status=423,
            )

        # UNCONFIGURED
        return JsonResponse(
            {"detail": "Licence non configurée. Contactez l'éditeur."},
            status=503,
        )
