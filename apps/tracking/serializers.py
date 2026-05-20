from rest_framework import serializers

from .models import Tracking


class TrackingSerializer(serializers.ModelSerializer):
    utilisateur_nom = serializers.CharField(source="utilisateur.username", read_only=True)

    class Meta:
        model = Tracking
        fields = [
            "id",
            "libelle",
            "description",
            "utilisateur",
            "utilisateur_nom",
            "horodatage",
            "ip_address",
            "user_agent",
        ]
        read_only_fields = fields
