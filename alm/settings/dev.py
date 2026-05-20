"""Configuration de développement."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Console email backend en dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CORS open en dev
CORS_ALLOW_ALL_ORIGINS = True

# Bypass de la licence en dev (pas de License Server requis pour tester en local).
# JAMAIS true en production.
LICENSE_BYPASS = True
