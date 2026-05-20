from rest_framework import serializers
from .models import (
    EarlyWithdrawalModel,
    EmbeddedOption,
    NmdModel,
    PrepaymentModel,
    RolloverModel,
)


def _factory(model_cls):
    Meta = type("Meta", (), {
        "model": model_cls,
        "fields": "__all__",
        "read_only_fields": ("created_at", "updated_at"),
    })
    return type(f"{model_cls.__name__}Serializer",
                (serializers.ModelSerializer,),
                {"Meta": Meta})


NmdModelSerializer = _factory(NmdModel)
PrepaymentModelSerializer = _factory(PrepaymentModel)
EarlyWithdrawalModelSerializer = _factory(EarlyWithdrawalModel)
RolloverModelSerializer = _factory(RolloverModel)
EmbeddedOptionSerializer = _factory(EmbeddedOption)
