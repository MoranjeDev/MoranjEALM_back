"""Signaux : log automatique de la création / modification d'utilisateurs."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tracking.models import Tracking
from .models import User


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    if created:
        Tracking.objects.create(
            libelle="Création utilisateur",
            description=f"Création de l'utilisateur {instance.username}.",
            utilisateur=None,
        )
