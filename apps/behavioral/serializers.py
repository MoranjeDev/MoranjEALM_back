from rest_framework import serializers
from .models import (
    BehavioralDistributionParam,
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


class BehavioralDistributionParamSerializer(serializers.ModelSerializer):
    class Meta:
        model = BehavioralDistributionParam
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, data):
        total = data.get("stable_core_pct", 0) + data.get("stable_non_core_pct", 0) + data.get("volatile_pct", 0)
        if abs(total - 100.0) > 0.01:
            raise serializers.ValidationError(
                f"stable_core_pct + stable_non_core_pct + volatile_pct = {total:.1f}% (doit être 100%)"
            )
        return data
