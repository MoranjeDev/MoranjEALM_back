"""Serializers DRF générés automatiquement pour chaque modèle d'input."""
from rest_framework import serializers

from .models import INPUT_MODELS, Output


def _make_serializer(model_cls):
    """Fabrique dynamiquement un ModelSerializer exposant tous les champs."""
    Meta = type("Meta", (), {
        "model": model_cls,
        "fields": "__all__",
        "read_only_fields": ("id", "created_at", "updated_at"),
    })
    return type(
        f"{model_cls.__name__}Serializer",
        (serializers.ModelSerializer,),
        {"Meta": Meta},
    )


# Construit un mapping kind -> Serializer pour les ViewSets
INPUT_SERIALIZERS = {
    kind: _make_serializer(model)
    for kind, model in INPUT_MODELS.items()
}


class OutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Output
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
