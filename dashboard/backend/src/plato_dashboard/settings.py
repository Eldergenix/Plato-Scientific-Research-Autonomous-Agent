from __future__ import annotations
import functools
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the dashboard.

    Driven by environment variables; safe defaults for local-desktop use.
    Pass `PLATO_DEMO_MODE=enabled` for the public-demo deployment shape.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLATO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage
    project_root: Path = Path.home() / ".plato" / "projects"
    keys_path: Path = Path.home() / ".plato" / "keys.json"

    # Server
    host: str = "127.0.0.1"
    port: int = 7878

    # Auth / capabilities flags
    auth: Literal["disabled", "enabled"] = "disabled"
    demo_mode: Literal["disabled", "enabled"] = "disabled"

    # Demo session caps
    demo_session_budget_cents: int = 50  # $0.50 per session
    demo_session_idle_minutes: int = 30
    demo_max_concurrent_runs: int = 1
    # Iter-9: cap the number of projects a single demo user can create
    # so a public-Spaces visitor can't spam project dirs. The limit is
    # a soft guard alongside the disk-cleanup loop; raising it without
    # also raising idle-cleanup is a footgun.
    demo_max_projects: int = 5
    demo_allowed_stages: tuple[str, ...] = ("data", "idea", "method", "literature")

    # Local mode caps
    local_max_concurrent_runs: int = 2

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    # Default ``True`` keeps single-process installs (HF Spaces, Railway,
    # dev, the bundled docker-compose with ``PLATO_USE_FAKEREDIS=true``)
    # working out of the box. Multi-worker production deploys MUST set
    # ``PLATO_USE_FAKEREDIS=false`` AND point ``PLATO_REDIS_URL`` at a
    # real Redis — the in-memory bus is process-local and SSE will drop
    # cross-worker events otherwise. ``events.bus.get_bus`` logs a CRITICAL
    # warning at startup when this combo looks misconfigured.
    use_fakeredis: bool = True

    # Worker
    worker_concurrency: int = 2

    # Frontend (in dev) — a CORS allowlist
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:7878",
    )

    @property
    def is_demo(self) -> bool:
        return self.demo_mode == "enabled"

    @property
    def is_auth_required(self) -> bool:
        return self.auth == "enabled"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Iter-9: cache the singleton. Without ``@lru_cache``, every FastAPI
    # request that depends on ``Settings`` re-reads ``.env`` and every
    # PLATO_* env var, AND re-runs the ``mkdir`` side effects. Cache
    # cleared explicitly via ``get_settings.cache_clear()`` when tests
    # monkey-patch env vars.
    s = Settings()
    s.project_root.mkdir(parents=True, exist_ok=True)
    s.keys_path.parent.mkdir(parents=True, exist_ok=True)
    return s
