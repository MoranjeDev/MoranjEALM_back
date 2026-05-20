"""Configuration de deploiement pour PythonAnywhere."""
import os

from .base import *  # noqa: F401,F403

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS")

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# PythonAnywhere sert /static/ et /media/ via les mappings de l'onglet Web.
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

# Pour une demo PythonAnywhere, SQLite peut remplacer MySQL afin d'economiser
# le quota disque et simplifier l'installation. MySQL reste le comportement
# par defaut des que DJANGO_DB_ENGINE n'est pas "sqlite".
if os.environ.get("DJANGO_DB_ENGINE", "mysql").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

# Autorise un deploiement de demonstration sans serveur de licence.
# En production commerciale, mettre LICENSE_BYPASS=0 et configurer LICENSE_*.
LICENSE_BYPASS = os.environ.get("LICENSE_BYPASS", "0") == "1"
