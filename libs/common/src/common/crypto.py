"""Envelope encryption service for sensitive credential storage.

Scheme:
  MASTER_KEY (env)
       |
       v
  DEK (random per record) — encrypts the plaintext
  MASTER_KEY             — encrypts the DEK

DB stores: encrypted_data + encrypted_dek (both Fernet tokens, base64-safe).
To decrypt: MASTER_KEY → DEK → plaintext.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from pydantic import BaseModel


class EncryptedPayload(BaseModel):
    encrypted_data: str
    encrypted_dek: str


class EnvelopeEncryption:
    """Fernet-based envelope encryption.

    Each record gets a unique DEK. The DEK encrypts the data, the MASTER_KEY
    encrypts the DEK. Compromising one record's DEK doesn't expose others.
    """

    def __init__(self, master_key: str) -> None:
        self._master_fernet = Fernet(self._ensure_fernet_key(master_key))

    def encrypt(self, plaintext: bytes) -> EncryptedPayload:
        dek = Fernet.generate_key()
        data_fernet = Fernet(dek)
        encrypted_data = data_fernet.encrypt(plaintext)
        encrypted_dek = self._master_fernet.encrypt(dek)
        return EncryptedPayload(
            encrypted_data=base64.urlsafe_b64encode(encrypted_data).decode(),
            encrypted_dek=base64.urlsafe_b64encode(encrypted_dek).decode(),
        )

    def decrypt(self, payload: EncryptedPayload) -> bytes:
        encrypted_dek = base64.urlsafe_b64decode(payload.encrypted_dek)
        dek = self._master_fernet.decrypt(encrypted_dek)
        data_fernet = Fernet(dek)
        encrypted_data = base64.urlsafe_b64decode(payload.encrypted_data)
        return data_fernet.decrypt(encrypted_data)

    def rotate_master_key(self, payload: EncryptedPayload, new_master_key: str) -> EncryptedPayload:
        """Re-encrypt the DEK with a new master key without touching the data."""
        encrypted_dek_bytes = base64.urlsafe_b64decode(payload.encrypted_dek)
        dek = self._master_fernet.decrypt(encrypted_dek_bytes)

        new_master_fernet = Fernet(self._ensure_fernet_key(new_master_key))
        new_encrypted_dek = new_master_fernet.encrypt(dek)

        return EncryptedPayload(
            encrypted_data=payload.encrypted_data,
            encrypted_dek=base64.urlsafe_b64encode(new_encrypted_dek).decode(),
        )

    @staticmethod
    def _ensure_fernet_key(key: str) -> bytes:
        """Accept a raw 32-byte key or a valid Fernet (url-safe base64) key."""
        raw = key.encode() if isinstance(key, str) else key
        if len(raw) == 32:
            return base64.urlsafe_b64encode(raw)
        return raw
