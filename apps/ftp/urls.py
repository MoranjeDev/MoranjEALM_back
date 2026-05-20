from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FtpCurveViewSet, FtpMarginBreakdownView, FtpPointViewSet

router = DefaultRouter()
router.register(r"curves", FtpCurveViewSet, basename="ftp-curve")
router.register(r"points", FtpPointViewSet, basename="ftp-point")

urlpatterns = [
    path("breakdown/", FtpMarginBreakdownView.as_view(), name="ftp-breakdown"),
] + router.urls
