"""Vues pour le paramètre singleton."""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.accounts.permissions import HasHabilitation
from apps.tracking.models import Tracking
from .models import Parameter
from .serializers import (
    CommentSerializer,
    ParameterSerializer,
    StressParameterSerializer,
)


COMMENT_FIELD_MAP = {
    "alco_base": "commalcobase",
    "alco_modere": "commalcomodere",
    "alco_severe": "commalcosevere",
    "dg_base": "commdgbase",
    "dg_modere": "commdgmodere",
    "dg_severe": "commdgsevere",
}


class ParameterView(APIView):
    """GET / PUT du paramètre singleton."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Paramètre de mot de passe"

    def get(self, request):
        param = Parameter.get_solo()
        return Response(ParameterSerializer(param, context={"request": request}).data)

    def put(self, request):
        param = Parameter.get_solo()
        serializer = ParameterSerializer(param, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        Tracking.objects.create(
            libelle="Mise à jour Paramètre",
            description="Mise à jour des paramètres ALM.",
            utilisateur=request.user,
        )
        return Response(serializer.data)


class ParameterBrandingView(APIView):
    """Mise à jour du nom et du logo de la banque cliente."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Paramètre de mot de passe"
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request):
        param = Parameter.get_solo()
        bank_name = request.data.get("bankName")
        upload = request.FILES.get("bankLogo")
        clear_logo = str(request.data.get("clearLogo", "")).lower() in {"1", "true", "yes", "on"}

        if bank_name is not None:
            param.bankName = str(bank_name).strip()

        if clear_logo and param.bankLogo:
            param.bankLogo.delete(save=False)
            param.bankLogo = None

        if upload is not None:
            content_type = getattr(upload, "content_type", "")
            if content_type and not content_type.startswith("image/"):
                return Response(
                    {"bankLogo": "Le logo doit être un fichier image."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            param.bankLogo = upload

        param.save(update_fields=["bankName", "bankLogo", "updated_at"])
        Tracking.objects.create(
            libelle="Mise à jour identité banque",
            description=f"Identité banque mise à jour : {param.bankName or 'non renseignée'}.",
            utilisateur=request.user,
        )
        return Response(ParameterSerializer(param, context={"request": request}).data)


class StressParameterView(APIView):
    """Endpoint dédié pour la mise à jour des paramètres de stress."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Stress Tests"

    def get(self, request):
        param = Parameter.get_solo()
        return Response({
            f: getattr(param, f)
            for f in ["credMod", "credSev", "banMod", "banSev",
                      "retMod", "retSev", "guiMod", "guiSev"]
        })

    def put(self, request):
        serializer = StressParameterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        param = Parameter.get_solo()
        for k, v in serializer.validated_data.items():
            setattr(param, k, v)
        param.save()
        Tracking.objects.create(
            libelle="Mise à jour stress",
            description=f"Paramètres de stress mis à jour : {serializer.validated_data}",
            utilisateur=request.user,
        )
        return Response(serializer.validated_data)


class CommentView(APIView):
    """Mise à jour d'un commentaire ALCO ou DG."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Paramètre de mot de passe"

    def put(self, request):
        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data["type"]
        text = serializer.validated_data["text"]
        field = COMMENT_FIELD_MAP[kind]

        param = Parameter.get_solo()
        setattr(param, field, text)
        param.save(update_fields=[field, "updated_at"])
        Tracking.objects.create(
            libelle=f"Commentaire {kind}",
            description=f"Mise à jour du commentaire {kind}.",
            utilisateur=request.user,
        )
        return Response({"type": kind, "text": text})
