"""Per-installation API key store.

- Lives at ``~/.plato/keys.json`` (mode 0600).
- Encrypted at rest with a Fernet key derived from a machine-local salt
  stored alongside the file. This is *obfuscation*, not strong protection;
  on a single-user desktop it's enough to keep keys out of accidental git
  commits or screen-sharing slip-ups.
- Environment variables (``OPENAI_API_KEY`` etc.) take precedence over
  in-app values, mirroring Plato's KeyManager semantics.
"""

from __future__ import annotations
import base64
import json
import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..domain.models import KeysPayload, KeysStatus

ENV_KEYS = {
    "OPENAI": "OPENAI_API_KEY",
    "GEMINI": "GOOGLE_API_KEY",
    "ANTHROPIC": "ANTHROPIC_API_KEY",
    "PERPLEXITY": "PERPLEXITY_API_KEY",
    "SEMANTIC_SCHOLAR": "SEMANTIC_SCHOLAR_KEY",
    # R8 — observability. The dashboard's Langfuse integration reads
    # these env-vars (or the in-app store as a fallback) so users can
    # opt into traces without exporting shell variables.
    "LANGFUSE_PUBLIC": "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET": "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST": "LANGFUSE_HOST",
}


def _derive_key(salt: bytes) -> bytes:
    seed = (os.uname().nodename + ":" + os.environ.get("USER", "user")).encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(seed))


class KeyStore:
    def __init__(self, path: Path):
        self.path = path
        self.salt_path = path.with_suffix(".salt")

    def _fernet(self) -> Fernet:
        if not self.salt_path.exists():
            self.salt_path.write_bytes(os.urandom(16))
            self.salt_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return Fernet(_derive_key(self.salt_path.read_bytes()))

    def load(self) -> KeysPayload:
        if not self.path.exists():
            return KeysPayload()
        try:
            data = self._fernet().decrypt(self.path.read_bytes())
            return KeysPayload.model_validate_json(data)
        except (InvalidToken, ValueError):
            # Corrupted; pretend empty rather than crash.
            return KeysPayload()

    def save(self, payload: KeysPayload) -> None:
        # Merge: never overwrite a previously-stored key with None.
        existing = self.load()
        merged = existing.model_copy(update={k: v for k, v in payload.model_dump().items() if v is not None})
        encrypted = self._fernet().encrypt(merged.model_dump_json().encode())
        self.path.write_bytes(encrypted)
        self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def status(self) -> KeysStatus:
        stored = self.load()
        result: dict[str, str] = {}
        for k, env_var in ENV_KEYS.items():
            if os.environ.get(env_var):
                result[k] = "from_env"
            elif getattr(stored, k):
                result[k] = "in_app"
            else:
                result[k] = "unset"
        return KeysStatus(**result)

    def resolve(self, provider: str) -> Optional[str]:
        env_var = ENV_KEYS.get(provider)
        if env_var and os.environ.get(env_var):
            return os.environ[env_var]
        stored = self.load()
        return getattr(stored, provider, None)
