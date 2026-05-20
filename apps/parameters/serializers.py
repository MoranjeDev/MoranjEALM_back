from rest_framework import serializers
from .models import Parameter


class ParameterSerializer(serializers.ModelSerializer):
    bankLogoUrl = serializers.SerializerMethodField()

    class Meta:
        model = Parameter
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def get_bankLogoUrl(self, obj):
        if not obj.bankLogo:
            return ""
        url = obj.bankLogo.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class StressParameterSerializer(serializers.Serializer):
    credMod = serializers.IntegerField()
    credSev = serializers.IntegerField()
    banMod = serializers.IntegerField()
    banSev = serializers.IntegerField()
    retMod = serializers.IntegerField()
    retSev = serializers.IntegerField()
    guiMod = serializers.IntegerField()
    guiSev = serializers.IntegerField()


class CommentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=["alco_base", "alco_modere", "alco_severe",
                 "dg_base", "dg_modere", "dg_severe"]
    )
    text = serializers.CharField(allow_blank=True)
