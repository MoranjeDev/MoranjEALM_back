"""
Agent de licence côté client.

Responsabilités :
1. Vérifier la licence locale au démarrage (signature, expiration, fingerprint).
2. Effectuer un phone-home périodique vers le License Server (Celery beat).
3. Mettre à jour l'état local et basculer en mode dégradé/blocage.
4. Vérifier les jetons à chaque requête HTTP via un middleware.

La clé publique Ed25519 est embarquée à un chemin connu du runtime
(`/app/license/public_key.pem` par défaut).
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.conf import settings
from django.utils import timezone as django_tz

from .fingerprint import compute_fingerprint
from .models import LicenseState

logger = logging.getLogger("alm.licensing")


# ----------------------------------------------------------------------------
# Vérification de signature (clé publique embarquée)
# ----------------------------------------------------------------------------
_public_key: Ed25519PublicKey | None = None


def _load_public_key() -> Ed25519PublicKey:
    global _public_key
    if _public_key is None:
        path = getattr(settings, "LICENSE_PUBLIC_KEY_PATH", "/app/license/public_key.pem")
        with open(path, "rb") as f:
            _public_key = serialization.load_pem_public_key(f.read())
    return _public_key


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_token(token: str) -> dict:
    """Décode et vérifie un jeton signé. Retourne le payload ou lève."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Jeton mal formé")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = (header_b64 + "." + payload_b64).encode()
    sig = _b64decode(sig_b64)
    _load_public_key().verify(sig, signing_input)
    payload = json.loads(_b64decode(payload_b64))
    if "exp" in payload and payload["exp"] < int(datetime.now(tz=timezone.utc).timestamp()):
        raise ValueError("Jeton expiré")
    return payload


# ----------------------------------------------------------------------------
# Phone-home
# ----------------------------------------------------------------------------
def phone_home() -> dict:
    """Appel HTTP vers le License Server. Met à jour LicenseState."""
    state = LicenseState.get_solo()

    server_url = getattr(settings, "LICENSE_SERVER_URL", "")
    license_key = getattr(settings, "LICENSE_KEY", state.license_key)

    if not server_url or not license_key:
        state.last_contact_error = "License server URL ou clé manquante."
        state.state = LicenseState.STATE_UNCONFIGURED
        state.save()
        return {"status": "unconfigured"}

    fp = compute_fingerprint()
    try:
        resp = requests.post(
            f"{server_url.rstrip('/')}/verify/",
            json={
                "license_key": license_key,
                "fingerprint": fp,
                "client_version": getattr(settings, "APP_VERSION", "1.0.0"),
            },
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:  # noqa: BLE001
        state.last_contact_error = str(e)
        # On ne change pas l'état (reste en grâce si autorisé)
        state = _refresh_state_after_offline(state)
        state.save()
        return {"status": "offline", "error": str(e)}

    status_str = body.get("status")
    state.last_contact_error = ""
    state.license_key = license_key
    state.fingerprint = fp

    if status_str == "ok":
        token = body.get("token", "")
        # Vérification de signature locale (zéro confiance dans le réseau)
        try:
            verify_token(token)
        except Exception as e:  # noqa: BLE001
            state.last_contact_error = f"Jeton invalide : {e}"
            state.state = LicenseState.STATE_BLOCKED
            state.save()
            return {"status": "invalid_token"}

        state.last_token = token
        state.last_token_iat = django_tz.now()
        state.last_contact_ok_at = django_tz.now()
        state.enabled_modules = body.get("enabled_modules", [])
        state.grace_period_days = body.get("grace_period_days", 30)
        if body.get("expires_at"):
            try:
                state.expires_at = datetime.fromisoformat(body["expires_at"])
            except Exception:  # noqa: BLE001
                pass
        state.state = LicenseState.STATE_OK
    elif status_str == "expired":
        state.state = LicenseState.STATE_BLOCKED
        state.last_contact_error = body.get("message", "")
    elif status_str == "revoked":
        state.state = LicenseState.STATE_BLOCKED
        state.last_contact_error = body.get("message", "")
    elif status_str == "fingerprint_mismatch":
        state.state = LicenseState.STATE_BLOCKED
        state.last_contact_error = body.get("message", "")
    else:
        state.state = LicenseState.STATE_BLOCKED
        state.last_contact_error = body.get("message", str(body))

    state.save()
    return {"status": status_str}


def _refresh_state_after_offline(state: LicenseState) -> LicenseState:
    """Met à jour l'état local quand le serveur est injoignable."""
    days = state.days_since_last_contact()
    if days is None:
        return state
    if days < 7:
        state.state = LicenseState.STATE_OK
    elif days < state.grace_period_days:
        state.state = LicenseState.STATE_GRACE
    elif days < state.grace_period_days * 2:
        state.state = LicenseState.STATE_READONLY
    else:
        state.state = LicenseState.STATE_BLOCKED
    return state


# ----------------------------------------------------------------------------
# Vérification au démarrage (à appeler depuis manage.py / wsgi)
# ----------------------------------------------------------------------------
def verify_at_startup() -> bool:
    """Vérifie la licence locale au démarrage. Retourne True si autorisée."""
    state = LicenseState.get_solo()
    if not state.last_token:
        # Première installation — la licence n'a jamais été contactée
        try:
            phone_home()
            state.refresh_from_db()
        except Exception:  # noqa: BLE001
            pass
    if state.state == LicenseState.STATE_BLOCKED:
        logger.error("LICENCE BLOQUÉE — l'application démarre en mode lecture seule.")
        return False
    return True
