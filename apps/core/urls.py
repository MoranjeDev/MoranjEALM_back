from django.urls import path
from .views import HealthView, InfoView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("info/", InfoView.as_view(), name="info"),
]
