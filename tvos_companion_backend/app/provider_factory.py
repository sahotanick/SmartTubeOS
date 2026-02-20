from __future__ import annotations

from app.config import Settings
from app.providers.base import CompanionProvider, ProviderError
from app.providers.mock_provider import MockProvider
from app.state_store import StateStore


def create_provider(settings: Settings, state_store: StateStore) -> CompanionProvider:
    mode = settings.provider_mode
    if mode == "mock":
        return MockProvider(state_store=state_store)
    if mode == "google":
        from app.providers.google_provider import GoogleProvider

        return GoogleProvider(settings=settings, state_store=state_store)
    raise ProviderError("INVALID_PROVIDER", f"Unsupported provider mode: {mode}", status_code=500)
