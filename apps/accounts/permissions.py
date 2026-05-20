"""Permissions DRF custom — vérifient les habilitations applicatives."""
from rest_framework.permissions import BasePermission


class HasHabilitation(BasePermission):
    """
    Vérifie que l'utilisateur connecté possède l'habilitation `required_habilitation`
    définie sur la vue.
    """

    def has_permission(self, request, view):
        required = getattr(view, "required_habilitation", None)
        if required is None:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.has_habilitation(required)


class IsValidator(BasePermission):
    """Vérifie que l'utilisateur appartient à un groupe avec is_validator=True."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.groupe and u.groupe.is_validator)


class IsExtractor(BasePermission):
    """Vérifie que l'utilisateur appartient à un groupe avec is_extractor=True."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.groupe and u.groupe.is_extractor)
