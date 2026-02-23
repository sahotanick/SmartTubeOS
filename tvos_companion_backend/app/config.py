from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    provider_mode: str
    state_file: Path
    youtube_client_id: str | None
    youtube_client_secret: str | None
    youtube_api_key: str | None
    youtube_region: str
    request_timeout_sec: float
    debug_formats: bool

    @staticmethod
    def from_env() -> "Settings":
        root = Path(__file__).resolve().parents[1]
        default_state_file = root / "data" / "state.json"
        debug_formats = os.getenv("SMARTTUBE_DEBUG_FORMATS", "").strip().lower() in {"1", "true", "yes", "on"}
        return Settings(
            provider_mode=os.getenv("COMPANION_PROVIDER", "mock").strip().lower(),
            state_file=Path(os.getenv("COMPANION_STATE_FILE", str(default_state_file))).expanduser().resolve(),
            youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID"),
            youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
            youtube_region=os.getenv("YOUTUBE_REGION", "US"),
            request_timeout_sec=float(os.getenv("COMPANION_HTTP_TIMEOUT_SEC", "20")),
            debug_formats=debug_formats,
        )
