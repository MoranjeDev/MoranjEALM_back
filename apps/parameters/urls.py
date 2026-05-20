from django.urls import path
from .views import CommentView, ParameterBrandingView, ParameterView, StressParameterView

urlpatterns = [
    path("", ParameterView.as_view(), name="parameter"),
    path("branding/", ParameterBrandingView.as_view(), name="parameter-branding"),
    path("stress/", StressParameterView.as_view(), name="parameter-stress"),
    path("comment/", CommentView.as_view(), name="parameter-comment"),
]
