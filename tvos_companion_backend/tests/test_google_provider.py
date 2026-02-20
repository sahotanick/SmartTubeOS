from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.providers.base import ProviderError
from app.providers.google_provider import GoogleProvider
from app.state_store import StateStore


def _settings(path: Path, client_id: str | None = "id", client_secret: str | None = "secret") -> Settings:
    return Settings(
        provider_mode="google",
        state_file=path,
        youtube_client_id=client_id,
        youtube_client_secret=client_secret,
        youtube_api_key="api-key",
        youtube_region="US",
        request_timeout_sec=20,
    )


def test_google_provider_requires_credentials(tmp_path: Path):
    with pytest.raises(ProviderError) as exc:
        GoogleProvider(settings=_settings(tmp_path / "state.json", client_id=None, client_secret="secret"), state_store=StateStore(tmp_path / "state.json"))
    assert exc.value.code == "GOOGLE_CONFIG_MISSING"


def test_google_device_auth_flow_persists_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    monkeypatch.setattr(
        provider,
        "_request_device_code",
        lambda: {
            "device_code": "dev-123",
            "user_code": "ABCD-EFGH",
            "verification_url": "https://youtube.com/activate",
            "expires_in": 900,
            "interval": 5,
        },
    )

    polls = iter(
        [
            {"status": "PENDING"},
            {
                "status": "SUCCESS",
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "scope": "scope",
            },
        ]
    )
    monkeypatch.setattr(provider, "_poll_device_token", lambda _: next(polls))
    monkeypatch.setattr(
        provider,
        "_fetch_userinfo",
        lambda _: {"sub": "user-1", "name": "John", "email": "john@example.com", "picture": "https://avatar"},
    )

    start = provider.auth_start()
    assert start["status"] == "PENDING"

    poll_1 = provider.auth_poll()
    assert poll_1 == {"status": "PENDING"}

    # move forward to satisfy poll interval gate
    state_store.update(
        lambda state: state["pendingAuth"].__setitem__("nextPollAtEpochSec", 0)  # type: ignore[index]
    )

    poll_2 = provider.auth_poll()
    assert poll_2["status"] == "SIGNED_IN"
    assert poll_2["selectedAccountId"] == "google_user-1"

    accounts = provider.list_accounts()
    assert accounts["selectedAccountId"] == "google_user-1"
    assert len(accounts["accounts"]) == 1
    assert accounts["accounts"][0]["email"] == "john@example.com"


def test_google_select_unknown_account(tmp_path: Path):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    with pytest.raises(ProviderError) as exc:
        provider.select_account("google_missing")
    assert exc.value.code == "ACCOUNT_NOT_FOUND"


def test_google_video_playback_appends_local_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "John",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    }
                ],
                "selectedAccountId": "google_user-1",
            }
        )
    )

    monkeypatch.setattr(provider, "_extract_stream", lambda _: {"streamUrl": "https://stream", "mimeType": "video/mp4"})

    playback = provider.video_playback("abc123")
    assert playback["videoId"] == "abc123"
    assert playback["streamUrl"] == "https://stream"

    state = state_store.read()
    assert state["localHistory"]
    assert state["localHistory"][-1]["videoId"] == "abc123"


def test_google_history_local_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "John",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    }
                ],
                "selectedAccountId": "google_user-1",
                "localHistory": [
                    {"accountId": "google_user-1", "videoId": "v1", "playedAtEpochSec": 200},
                    {"accountId": "google_user-1", "videoId": "v2", "playedAtEpochSec": 300},
                ],
            }
        )
    )

    monkeypatch.setattr(provider, "_history_from_related_playlist", lambda *_: None)
    monkeypatch.setattr(
        provider,
        "_best_effort_video_stub",
        lambda video_id: {
            "videoId": video_id,
            "title": video_id,
            "channelName": "",
            "channelId": "",
            "thumbnailUrl": "",
            "publishedText": "",
            "durationSec": 0,
        },
    )

    history = provider.feed_history(None)
    assert history["title"] == "History"
    assert len(history["items"]) == 2
    assert history["items"][0]["videoId"] == "v2"


def test_google_history_local_continuation_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    history_entries = []
    for index in range(25):
        history_entries.append(
            {
                "accountId": "google_user-1",
                "videoId": f"video-{index}",
                "playedAtEpochSec": 1000 + index,
            }
        )

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "John",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    }
                ],
                "selectedAccountId": "google_user-1",
                "localHistory": history_entries,
            }
        )
    )

    monkeypatch.setattr(provider, "_history_from_related_playlist", lambda *_: None)
    monkeypatch.setattr(
        provider,
        "_best_effort_video_stub",
        lambda video_id: {
            "videoId": video_id,
            "title": video_id,
            "channelName": "",
            "channelId": "",
            "thumbnailUrl": "",
            "publishedText": "",
            "durationSec": 0,
        },
    )

    first = provider.feed_history(None)
    assert first["continuationToken"] is not None
    second = provider.feed_history(first["continuationToken"])
    assert second["items"]
