"""Tâches Celery pour le phone-home périodique."""
from celery import shared_task

from .agent import phone_home


@shared_task(name="licensing.phone_home")
def task_phone_home():
    return phone_home()
