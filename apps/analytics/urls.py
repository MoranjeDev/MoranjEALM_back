from django.urls import path
from .views import ConcentrationView, EVESensitivityView, NIISensitivityView

urlpatterns = [
    path("nii/", NIISensitivityView.as_view(), name="analytics-nii"),
    path("eve/", EVESensitivityView.as_view(), name="analytics-eve"),
    path("concentration/", ConcentrationView.as_view(), name="analytics-concentration"),
]
