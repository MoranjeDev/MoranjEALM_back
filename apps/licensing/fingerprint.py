"""
Fingerprint matériel/serveur — empreinte stable d'une installation.

Combine plusieurs caractéristiques de la machine pour produire un identifiant
unique qui ne change pas au redémarrage mais empêche la duplication
d'une installation sur un autre serveur.

Sources combinées :
- /etc/machine-id (Linux) ou équivalent.
- Adresse MAC primaire.
- Hostname.
- ID CPU (psutil) si disponible.
"""
from __future__ import annotations

import hashlib
import platform
import subprocess
import uuid
from pathlib import Path


def _machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        p = Path(path)
        if p.exists():
            try:
                return p.read_text().strip()
            except Exception:  # noqa: BLE001
                pass
    return ""


def _primary_mac() -> str:
    try:
        return f"{uuid.getnode():012x}"
    except Exception:  # noqa: BLE001
        return ""


def _cpu_info() -> str:
    try:
        return platform.processor() or ""
    except Exception:  # noqa: BLE001
        return ""


def compute_fingerprint() -> str:
    """Retourne un fingerprint stable de l'hôte (sha256 hexa 64 chars)."""
    parts = [
        platform.node() or "",
        _machine_id(),
        _primary_mac(),
        _cpu_info(),
        platform.system(),
        platform.machine(),
    ]
    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()
