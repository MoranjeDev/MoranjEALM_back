from django.urls import path
from .views import LicenseStatusView, TriggerPhoneHomeView

urlpatterns = [
    path("status/", LicenseStatusView.as_view(), name="license-status"),
    path("phone-home/", TriggerPhoneHomeView.as_view(), name="license-phone-home"),
]
