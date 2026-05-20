"""Vues API : statut de licence et déclenchement manuel du phone-home."""
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent import phone_home
from .models import LicenseState


class LicenseStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        s = LicenseState.get_solo()
        return Response({
            "state": s.state,
            "license_key": (s.license_key[:6] + "…") if s.license_key else "",
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "enabled_modules": s.enabled_modules,
            "fingerprint": s.fingerprint,
            "last_contact_ok_at": s.last_contact_ok_at.isoformat() if s.last_contact_ok_at else None,
            "last_contact_error": s.last_contact_error,
            "days_since_last_contact": s.days_since_last_contact(),
        })


class TriggerPhoneHomeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        return Response(phone_home())
