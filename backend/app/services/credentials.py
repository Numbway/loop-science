"""Encrypted system credential-profile storage.

The database only receives an authenticated encrypted blob. API keys, SSH
passwords, private keys, and passphrases are never included in API responses.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CredentialError(RuntimeError):
    """Raised when saved profile credentials cannot be decrypted."""


def _cipher() -> Fernet:
    source = settings.CREDENTIAL_ENCRYPTION_KEY or settings.JWT_SECRET
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credentials(credentials: dict[str, Any]) -> str:
    """Encrypt an arbitrary credential mapping."""
    encoded = json.dumps(credentials, ensure_ascii=False).encode("utf-8")
    return _cipher().encrypt(encoded).decode("ascii")


def decrypt_credentials(token: str) -> dict[str, Any]:
    """Decrypt an arbitrary credential mapping."""
    if not token:
        return {}
    try:
        payload = _cipher().decrypt(token.encode("ascii"))
        value = json.loads(payload)
    except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialError(
            "Saved credentials could not be decrypted. Re-enter them."
        ) from exc
    return value if isinstance(value, dict) else {}
