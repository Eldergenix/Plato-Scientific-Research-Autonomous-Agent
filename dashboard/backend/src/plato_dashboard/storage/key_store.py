"""Encrypted dashboard API key store.

- Single-user deployments use ``~/.plato/keys.json`` (mode 0600).
- Multi-tenant deployments store in-app keys under
  ``<project_root>/users/<tenant_id>/keys.json`` so personal and Lab
  workspaces do not share provider credentials.
- Encrypted at rest with a Fernet key derived from a machine-local salt
  stored alongside the file. This is *obfuscation*, not strong protection;
  on a single-user desktop it's enough to keep keys out of accidental git
  commits or screen-sharing slip-ups.
- Environment variables (``OPENAI_API_KEY`` etc.) take precedence over
  in-app values, mirroring Plato's KeyManager semantics.
"""

from __future__ import annotations
import base64
import os
import stat
from pathlib import Path
from typing import Literal, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..domain.models import KeysPayload, KeysStatus

ENV_KEYS = {
    "OPENAI": "OPENAI_API_KEY",
    "GEMINI": "GOOGLE_API_KEY",
    "ANTHROPIC": "ANTHROPIC_API_KEY",
    "HUGGINGFACE": "HUGGINGFACE_API_KEY",
    "PERPLEXITY": "PERPLEXITY_API_KEY",
    "SEMANTIC_SCHOLAR": "SEMANTIC_SCHOLAR_KEY",
    # R8 — observability. The dashboard's Langfuse integration reads
    # these env-vars (or the in-app store as a fallback) so users can
    # opt into traces without exporting shell variables.
    "LANGFUSE_PUBLIC": "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET": "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST": "LANGFUSE_HOST",
}

ENV_KEY_ALIASES = {
    "HUGGINGFACE": (
        "HUGGINGFACE_API_KEY",
        "HUGGINGFACE_HUB_TOKEN",
        "HF_TOKEN",
    ),
}


def _env_names(provider: str) -> tuple[str, ...]:
    if provider in ENV_KEY_ALIASES:
        return ENV_KEY_ALIASES[provider]
    env_var = ENV_KEYS.get(provider)
    return (env_var,) if env_var else ()


def _env_value(provider: str) -> str | None:
    for env_var in _env_names(provider):
        value = os.environ.get(env_var)
        if value:
            return value
    return None


def _derive_key(salt: bytes) -> bytes:
    seed = (os.uname().nodename + ":" + os.environ.get("USER", "user")).encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(seed))


def key_store_path_for_user(
    project_root: Path,
    fallback_keys_path: Path,
    user_id: str | None,
) -> Path:
    if user_id:
        return project_root / "users" / user_id / "keys.json"
    return fallback_keys_path


def key_store_path_for_project_dir(
    project_root: Path,
    fallback_keys_path: Path,
    project_dir: Path,
) -> Path:
    try:
        relative = project_dir.resolve().relative_to((project_root / "users").resolve())
    except ValueError:
        return fallback_keys_path
    if not relative.parts:
        return fallback_keys_path
    return key_store_path_for_user(project_root, fallback_keys_path, relative.parts[0])


class KeyStore:
    def __init__(self, path: Path):
        self.path = path
        self.salt_path = path.with_suffix(".salt")

    def _fernet(self) -> Fernet:
        if not self.salt_path.exists():
            self.salt_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic salt creation via O_CREAT|O_EXCL: two concurrent
            # callers can't both decide to write a fresh salt and have
            # the second overwrite the first. If two processes race,
            # one wins the create and the other gets FileExistsError;
            # we then re-read the canonical salt.
            try:
                fd = os.open(
                    self.salt_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                with os.fdopen(fd, "wb") as f:
                    f.write(os.urandom(16))
            except FileExistsError:
                pass
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.load()
        merged = existing.model_copy(update={k: v for k, v in payload.model_dump().items() if v is not None})
        encrypted = self._fernet().encrypt(merged.model_dump_json().encode())
        # Atomic write: a crash mid-flush previously left a 0-byte
        # ``keys.json`` that subsequently load()'d as ``InvalidToken``,
        # silently wiping every stored key.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_bytes(encrypted)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, self.path)

    def status(self) -> KeysStatus:
        stored = self.load()
        result: dict[str, Literal["unset", "from_env", "in_app"]] = {}
        for k in ENV_KEYS:
            if _env_value(k):
                result[k] = "from_env"
            elif getattr(stored, k):
                result[k] = "in_app"
            else:
                result[k] = "unset"
        return KeysStatus(**result)

    def resolve(self, provider: str) -> Optional[str]:
        env_value = _env_value(provider)
        if env_value:
            return env_value
        stored = self.load()
        return getattr(stored, provider, None)
