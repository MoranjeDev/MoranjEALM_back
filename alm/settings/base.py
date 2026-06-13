"""
Configuration Django commune (dev / prod).
Toutes les valeurs sensibles sont lues depuis les variables d'environnement.
"""

import os
from datetime import timedelta
from pathlib import Path


def csv_env(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a clean list."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]

# ============================================================================
# Chemins
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ============================================================================
# Sécurité
# ============================================================================
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "insecure-dev-only-change-in-production-please-please-please",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS", "*")

# ============================================================================
# Applications
# ============================================================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "simple_history",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.tracking",
    "apps.inputs",
    "apps.parameters",
    "apps.engine",
    "apps.governance",
    "apps.behavioral",
    "apps.mapping",
    "apps.multicurrency",
    "apps.analytics",
    "apps.ftp",
    "apps.reporting",
    "apps.licensing",
    "apps.balance_sheet",
    "apps.off_balance",
    "apps.mis",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ============================================================================
# Middlewares
# ============================================================================
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.licensing.middleware.LicenseEnforcementMiddleware",
]

ROOT_URLCONF = "alm.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "alm.wsgi.application"
ASGI_APPLICATION = "alm.asgi.application"

# ============================================================================
# Base de données — MySQL / MariaDB
# ============================================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DB", "moranjealm"),
        "USER": os.environ.get("MYSQL_USER", "root"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {
            # charset gère SET NAMES utf8mb4 automatiquement (PyMySQL et mysqlclient)
            "charset": "utf8mb4",
            # init_command : UNE SEULE instruction
            # (PyMySQL refuse les multi-statements par défaut, sécurité)
            "init_command": (
                "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,"
                "NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO'"
            ),
        },
    }
}

# ============================================================================
# Modèle utilisateur custom
# ============================================================================
AUTH_USER_MODEL = "accounts.User"

# ============================================================================
# Validation des mots de passe
# ============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================================
# Internationalisation
# ============================================================================
LANGUAGE_CODE = os.environ.get("DJANGO_LANGUAGE_CODE", "fr-fr")
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Africa/Douala")
USE_I18N = True
USE_TZ = True

# ============================================================================
# Static / Media
# ============================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# REST Framework
# ============================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ============================================================================
# JWT
# ============================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 30))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ============================================================================
# CORS
# ============================================================================
CORS_ALLOWED_ORIGINS = csv_env(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
CSRF_TRUSTED_ORIGINS = csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ============================================================================
# OpenAPI (Spectacular)
# ============================================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "MoranjEALM API",
    "DESCRIPTION": "API REST de l'application ALM",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ============================================================================
# Celery
# ============================================================================
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ============================================================================
# Application — paramètres métier
# ============================================================================
PASSWORD_DELAY_DAYS = int(os.environ.get("PASSWORD_DELAY_DAYS", 90))
PASSWORD_DELAY_ACTIVATE = os.environ.get("PASSWORD_DELAY_ACTIVATE", "1") == "1"

# ============================================================================
# Licensing (phase 5)
# ============================================================================
LICENSE_SERVER_URL = os.environ.get("LICENSE_SERVER_URL", "")
LICENSE_KEY = os.environ.get("LICENSE_KEY", "")
LICENSE_PUBLIC_KEY_PATH = os.environ.get(
    "LICENSE_PUBLIC_KEY_PATH", "/app/license/public_key.pem"
)
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

# Phone-home programmé toutes les 4 heures via Celery beat
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "license-phone-home": {
        "task": "licensing.phone_home",
        "schedule": crontab(minute=0, hour="*/4"),
    },
}

# ============================================================================
# LDAP / Active Directory (optionnel)
# ============================================================================
LDAP_SERVER_URI = os.environ.get("LDAP_SERVER_URI", "")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")

if LDAP_SERVER_URI:
    import ldap
    from django_auth_ldap.config import LDAPSearch, GroupOfNamesType

    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]
    AUTH_LDAP_SERVER_URI = LDAP_SERVER_URI
    AUTH_LDAP_BIND_DN = LDAP_BIND_DN
    AUTH_LDAP_BIND_PASSWORD = LDAP_BIND_PASSWORD
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        os.environ.get("LDAP_USER_SEARCH_BASE", ""),
        ldap.SCOPE_SUBTREE,
        "(sAMAccountName=%(user)s)",
    )
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }
else:
    AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# ============================================================================
# Logging
# ============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", '
                      '"name": "%(name)s", "message": "%(message)s"}',
        },
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "alm": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
