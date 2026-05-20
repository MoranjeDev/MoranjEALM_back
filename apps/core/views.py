"""Vues utilitaires : health check, info."""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class InfoView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "app": "MoranjEALM",
            "version": "1.0.0",
            "language": settings.LANGUAGE_CODE,
            "timezone": settings.TIME_ZONE,
        })
