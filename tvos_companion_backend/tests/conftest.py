from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.state_store import StateStore


@pytest.fixture()
def app_client(tmp_path: Path) -> TestClient:
    state_file = tmp_path / "state.json"
    settings = Settings(
        provider_mode="mock",
        state_file=state_file,
        youtube_client_id=None,
        youtube_client_secret=None,
        youtube_api_key=None,
        youtube_region="US",
        request_timeout_sec=20,
    )
    state_store = StateStore(state_file)
    app = create_app(settings=settings, state_store=state_store)
    return TestClient(app)
