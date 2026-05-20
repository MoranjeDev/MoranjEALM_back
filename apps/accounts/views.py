"""Vues DRF des comptes : login, refresh, profil, mot de passe, CRUD admin."""
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tracking.models import Tracking
from .models import GroupeUser, Habilitation, User
from .permissions import HasHabilitation
from .serializers import (
    ChangePasswordSerializer,
    GroupeUserSerializer,
    HabilitationChoicesSerializer,
    HabilitationSerializer,
    UserCreateSerializer,
    UserSerializer,
)


# ============================================================================
# Authentification
# ============================================================================
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response(
                {"detail": "username et password requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Identifiants invalides."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.status != User.STATUS_ACTIVE:
            return Response(
                {"detail": f"Compte {user.status}."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Vérification expiration mot de passe
        password_expired = False
        if settings.PASSWORD_DELAY_ACTIVATE:
            password_expired = user.password_expired(settings.PASSWORD_DELAY_DAYS)

        # Émission JWT
        refresh = RefreshToken.for_user(user)

        # Mise à jour traçabilité
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at"])
        Tracking.objects.create(
            libelle="Connexion",
            description=f"Connexion de l'utilisateur {user.username}",
            utilisateur=user,
        )

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
            "must_change_password": user.firstconnect or password_expired,
            "password_expired": password_expired,
            "first_connect": user.firstconnect,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh = request.data.get("refresh")
            if refresh:
                token = RefreshToken(refresh)
                token.blacklist()
        except Exception:  # noqa: BLE001
            pass

        Tracking.objects.create(
            libelle="Déconnexion",
            description=f"Déconnexion de l'utilisateur {request.user.username}",
            utilisateur=request.user,
        )
        return Response({"detail": "Déconnecté."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if not request.user.check_password(old_password):
            return Response(
                {"detail": "Ancien mot de passe incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.firstconnect = False
        request.user.save()

        Tracking.objects.create(
            libelle="Changement de mot de passe",
            description=f"L'utilisateur {request.user.username} a changé son mot de passe.",
            utilisateur=request.user,
        )
        return Response({"detail": "Mot de passe mis à jour."})


# ============================================================================
# CRUD administration
# ============================================================================
class GroupeUserViewSet(viewsets.ModelViewSet):
    queryset = GroupeUser.objects.all()
    serializer_class = GroupeUserSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gestion des Groupes Utilisateurs"


class HabilitationViewSet(viewsets.ModelViewSet):
    queryset = Habilitation.objects.all()
    serializer_class = HabilitationSerializer
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gestion des Habilitations"

    @action(detail=False, methods=["get"], url_path="choices")
    def choices(self, request):
        return Response(HabilitationChoicesSerializer.list())


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related("groupe", "groupe__habilitation")
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Gestion des Utilisateurs"

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer
