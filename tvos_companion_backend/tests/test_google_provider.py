from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.providers.base import ProviderError
from app.providers.google_provider import GoogleProvider
from app.state_store import StateStore
from app.util import now_epoch


def _settings(path: Path, client_id: str | None = "id", client_secret: str | None = "secret") -> Settings:
    return Settings(
        provider_mode="google",
        state_file=path,
        youtube_client_id=client_id,
        youtube_client_secret=client_secret,
        youtube_api_key="api-key",
        youtube_region="US",
        request_timeout_sec=20,
        debug_formats=False,
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
    monkeypatch.setattr(provider, "_fetch_owned_channels", lambda _: [])

    start = provider.auth_start()
    assert start["status"] == "PENDING"
    assert "user_code=ABCD-EFGH" in start["verificationUrlComplete"]

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


def test_google_remove_account_updates_selection_and_history(tmp_path: Path):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "Aamber",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                    {
                        "id": "google_user-1_chan-2",
                        "name": "Harnake",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "channelId": "chan-2",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                ],
                "selectedAccountId": "google_user-1",
                "localHistory": [
                    {"accountId": "google_user-1", "videoId": "v1", "playedAtEpochSec": 10},
                    {"accountId": "google_user-1_chan-2", "videoId": "v2", "playedAtEpochSec": 20},
                ],
            }
        )
    )

    removed = provider.remove_account("google_user-1")
    assert removed["selectedAccountId"] == "google_user-1_chan-2"

    accounts = provider.list_accounts()
    assert [row["id"] for row in accounts["accounts"]] == ["google_user-1_chan-2"]

    state = state_store.read()
    assert all(row["accountId"] != "google_user-1" for row in state["localHistory"])


def test_google_remove_unknown_account_raises_404(tmp_path: Path):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    with pytest.raises(ProviderError) as exc:
        provider.remove_account("google_missing")
    assert exc.value.code == "ACCOUNT_NOT_FOUND"


def test_google_refresh_accounts_preserves_existing_owner_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "Preet",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "channelId": "chan-1",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": now_epoch() + 600,
                            "scope": "scope",
                        },
                    },
                    {
                        "id": "google_user-1_chan-2",
                        "name": "Harnake",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "channelId": "chan-2",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": now_epoch() + 600,
                            "scope": "scope",
                        },
                    },
                ],
                "selectedAccountId": "google_user-1_chan-2",
            }
        )
    )

    monkeypatch.setattr(
        provider,
        "_fetch_userinfo",
        lambda _: {"sub": "user-1", "name": "John", "email": "john@example.com", "picture": "https://avatar"},
    )
    monkeypatch.setattr(
        provider,
        "_fetch_owned_channels",
        lambda _: [{"id": "chan-1", "snippet": {"title": "Preet", "thumbnails": {"high": {"url": "https://p"}}}}],
    )

    refreshed = provider.refresh_accounts()
    assert refreshed["status"] == "REFRESHED"
    assert refreshed["discoveredProfileCount"] == 1
    assert refreshed["totalProfileCount"] == 2
    assert refreshed["selectedAccountId"] == "google_user-1_chan-2"

    accounts = provider.list_accounts()
    assert [row["name"] for row in accounts["accounts"]] == ["Preet", "Harnake"]


def test_google_auth_poll_maps_owned_channel_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setattr(
        provider,
        "_poll_device_token",
        lambda _: {
            "status": "SUCCESS",
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
            "scope": "scope",
        },
    )
    monkeypatch.setattr(
        provider,
        "_fetch_userinfo",
        lambda _: {"sub": "user-1", "name": "John", "email": "john@example.com", "picture": "https://avatar"},
    )
    monkeypatch.setattr(
        provider,
        "_fetch_owned_channels",
        lambda _: [
            {"id": "chan-1", "snippet": {"title": "Aamber", "thumbnails": {"high": {"url": "https://a"}}}},
            {"id": "chan-2", "snippet": {"title": "Harnake", "thumbnails": {"high": {"url": "https://h"}}}},
            {"id": "chan-3", "snippet": {"title": "Preet", "thumbnails": {"high": {"url": "https://p"}}}},
        ],
    )

    provider.auth_start()
    state_store.update(
        lambda state: state["pendingAuth"].__setitem__("nextPollAtEpochSec", 0)  # type: ignore[index]
    )
    poll = provider.auth_poll()
    assert poll["status"] == "SIGNED_IN"
    assert poll["selectedAccountId"] == "google_user-1"

    accounts = provider.list_accounts()
    assert len(accounts["accounts"]) == 3
    assert [row["name"] for row in accounts["accounts"]] == ["Aamber", "Harnake", "Preet"]


def test_google_list_accounts_hides_non_google_entries(tmp_path: Path):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "acc_123",
                        "name": "Mock Account",
                        "email": "mock@example.com",
                        "avatarUrl": None,
                        "tokens": {
                            "accessToken": "legacy-token",
                            "refreshToken": "legacy-refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                    {
                        "id": "google_user-1",
                        "name": "Google Account",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                ],
                "selectedAccountId": "google_user-1",
            }
        )
    )

    accounts = provider.list_accounts()
    assert len(accounts["accounts"]) == 1
    assert accounts["accounts"][0]["id"] == "google_user-1"

    with pytest.raises(ProviderError) as exc:
        provider.select_account("acc_123")
    assert exc.value.code == "ACCOUNT_NOT_FOUND"


def test_google_auth_poll_keeps_existing_profiles_for_same_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "pendingAuth": {
                    "provider": "google",
                    "deviceCode": "device-code",
                    "signInCode": "ABCD-EFGH",
                    "verificationUrl": "https://youtube.com/activate",
                    "expiresAtEpochSec": now_epoch() + 600,
                    "pollIntervalSec": 5,
                    "nextPollAtEpochSec": 0,
                },
                "accounts": [
                    {
                        "id": "google_user-1_chan-1",
                        "name": "Aamber",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "channelId": "chan-1",
                        "tokens": {
                            "accessToken": "old-token",
                            "refreshToken": "refresh-old",
                            "expiresAtEpochSec": now_epoch() + 100,
                        },
                    },
                    {
                        "id": "google_user-1_chan-2",
                        "name": "Harnake",
                        "email": "john@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "channelId": "chan-2",
                        "tokens": {
                            "accessToken": "old-token",
                            "refreshToken": "refresh-old",
                            "expiresAtEpochSec": now_epoch() + 100,
                        },
                    },
                ],
                "selectedAccountId": "google_user-1_chan-2",
            }
        )
    )

    monkeypatch.setattr(
        provider,
        "_poll_device_token",
        lambda _: {
            "status": "SUCCESS",
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "scope": "scope-a scope-b",
        },
    )
    monkeypatch.setattr(
        provider,
        "_fetch_userinfo",
        lambda _: {
            "sub": "user-1",
            "name": "John",
            "email": "john@example.com",
            "picture": "https://example.com/p.jpg",
        },
    )
    monkeypatch.setattr(
        provider,
        "_fetch_owned_channels",
        lambda _: [
            {"id": "chan-1", "snippet": {"title": "Aamber", "thumbnails": {"high": {"url": "https://a"}}}},
        ],
    )

    poll = provider.auth_poll()
    assert poll["status"] == "SIGNED_IN"

    accounts = provider.list_accounts()
    assert [row["name"] for row in accounts["accounts"]] == ["Aamber", "Harnake"]
    for row in state_store.read()["accounts"]:
        if row.get("provider") != "google":
            continue
        assert row["tokens"]["accessToken"] == "new-token"
        assert row["tokens"]["refreshToken"] == "new-refresh"


def test_google_subscriptions_fallback_uses_playlist_items_not_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    seen_paths: list[str] = []

    def fake_youtube_get(path: str, params: dict, account_id: str | None, auth_optional: bool) -> dict:
        seen_paths.append(path)
        assert account_id == "google_user-1"
        assert auth_optional is False

        if path == "subscriptions":
            return {
                "items": [
                    {"snippet": {"resourceId": {"channelId": "chan-a"}}},
                    {"snippet": {"resourceId": {"channelId": "chan-b"}}},
                ]
            }

        if path == "channels":
            return {
                "items": [
                    {
                        "id": "chan-a",
                        "snippet": {"title": "Aamber"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "uploads-a"}},
                    },
                    {
                        "id": "chan-b",
                        "snippet": {"title": "Harnake"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "uploads-b"}},
                    },
                ]
            }

        if path == "playlistItems":
            playlist_id = params.get("playlistId")
            if playlist_id == "uploads-a":
                return {
                    "items": [
                        {
                            "snippet": {
                                "title": "Video A",
                                "channelTitle": "Aamber",
                                "channelId": "chan-a",
                                "resourceId": {"videoId": "video-a"},
                                "publishedAt": "2026-02-20T10:00:00Z",
                                "thumbnails": {"high": {"url": "https://a"}},
                            }
                        }
                    ]
                }
            if playlist_id == "uploads-b":
                return {
                    "items": [
                        {
                            "snippet": {
                                "title": "Video B",
                                "channelTitle": "Harnake",
                                "channelId": "chan-b",
                                "resourceId": {"videoId": "video-b"},
                                "publishedAt": "2026-02-20T11:00:00Z",
                                "thumbnails": {"high": {"url": "https://b"}},
                            }
                        }
                    ]
                }
            return {"items": []}

        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(provider, "_youtube_get", fake_youtube_get)

    payload, items = provider._subscriptions_fallback(selected="google_user-1", page_token=None)
    assert payload.get("items")
    assert [row["videoId"] for row in items] == ["video-b", "video-a"]
    assert "search" not in seen_paths
    assert seen_paths.count("playlistItems") == 2


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

    monkeypatch.setattr(
        provider,
        "_extract_stream",
        lambda _: {
            "streamUrl": "https://stream",
            "mimeType": "video/mp4",
            "qualityLabel": "1080p",
            "isAdaptive": True,
        },
    )

    playback = provider.video_playback("abc123")
    assert playback["videoId"] == "abc123"
    assert playback["streamUrl"] == "https://stream"
    assert playback["qualityLabel"] == "1080p"
    assert playback["isAdaptive"] is True

    state = state_store.read()
    assert state["localHistory"]
    assert state["localHistory"][-1]["videoId"] == "abc123"


def test_google_stream_extraction_attempts_prioritize_default_clients(tmp_path: Path):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    attempts = provider._stream_extraction_attempts()
    assert attempts
    assert "extractor_args" not in attempts[0]

    forced_attempts = [row for row in attempts if row.get("extractor_args")]
    assert forced_attempts
    assert forced_attempts[0]["extractor_args"]["youtube"]["player_client"] == ["web", "ios", "android"]
    assert forced_attempts[-1]["extractor_args"]["youtube"]["player_client"] == ["tv"]


def test_google_extract_stream_falls_back_to_next_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    monkeypatch.setattr(
        provider,
        "_stream_extraction_attempts",
        lambda: [
            {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "format": "best",
            },
            {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "format": "b",
                "extractor_args": {"youtube": {"player_client": ["web", "ios", "android"]}},
            },
        ],
    )

    calls: list[dict] = []

    class FakeYDL:
        def __init__(self, options: dict):
            self._options = options
            calls.append(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, _video_url: str, download: bool):
            assert download is False
            if self._options.get("format") == "best":
                raise RuntimeError("Requested format is not available")
            return {
                "formats": [
                    {
                        "format_id": "22",
                        "url": "https://stream.example/video.mp4",
                        "ext": "mp4",
                        "height": 720,
                        "fps": 30,
                        "tbr": 1200,
                        "vcodec": "avc1.64001F",
                        "acodec": "mp4a.40.2",
                        "protocol": "https",
                    }
                ]
            }

    monkeypatch.setattr("app.providers.google_provider.YoutubeDL", FakeYDL)

    payload = provider._extract_stream("abc123")
    assert payload["streamUrl"] == "https://stream.example/video.mp4"
    assert payload["mimeType"] == "video/mp4"
    assert payload["qualityLabel"] == "720p"
    assert len(calls) == 2
    assert "extractor_args" not in calls[0]
    assert calls[1]["extractor_args"]["youtube"]["player_client"] == ["web", "ios", "android"]


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


def test_google_history_is_scoped_to_selected_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "Preet",
                        "email": "preet@example.com",
                        "provider": "google",
                        "tokens": {
                            "accessToken": "token-1",
                            "refreshToken": "refresh-1",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                    {
                        "id": "google_user-2",
                        "name": "Harnake",
                        "email": "harnake@example.com",
                        "provider": "google",
                        "tokens": {
                            "accessToken": "token-2",
                            "refreshToken": "refresh-2",
                            "expiresAtEpochSec": 9999999999,
                        },
                    },
                ],
                "selectedAccountId": "google_user-1",
                "localHistory": [
                    {"accountId": "google_user-1", "videoId": "preet-1", "playedAtEpochSec": 1001},
                    {"accountId": "google_user-2", "videoId": "harnake-1", "playedAtEpochSec": 1002},
                    {"accountId": "google_user-1", "videoId": "preet-2", "playedAtEpochSec": 1003},
                ],
            }
        )
    )

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
    monkeypatch.setattr(provider, "_history_from_related_playlist", lambda *_: (_ for _ in ()).throw(AssertionError("remote history should not be used")))

    history_preet = provider.feed_history(None)
    assert [row["videoId"] for row in history_preet["items"]] == ["preet-2", "preet-1"]

    provider.select_account("google_user-2")
    history_harnake = provider.feed_history(None)
    assert [row["videoId"] for row in history_harnake["items"]] == ["harnake-1"]


def test_google_youtube_get_uses_response_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)
    provider._quota_saver_enabled = True
    provider._cache_ttl_sec = 300

    calls = {"count": 0}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"items": [{"id": "video-1"}]}

    def fake_get(*_args, **_kwargs):
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr(provider, "_valid_access_token", lambda _: "token")
    monkeypatch.setattr(provider._client, "get", fake_get)

    first = provider._youtube_get(
        path="videos",
        params={"part": "snippet", "id": "video-1", "maxResults": 1},
        account_id="google_user-1",
        auth_optional=True,
    )
    second = provider._youtube_get(
        path="videos",
        params={"part": "snippet", "id": "video-1", "maxResults": 1},
        account_id="google_user-1",
        auth_optional=True,
    )

    assert first == second
    assert calls["count"] == 1


def test_google_youtube_get_quota_cooldown_blocks_repeated_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)
    provider._quota_saver_enabled = True
    provider._quota_error_ttl_sec = 120

    calls = {"count": 0}

    class QuotaResponse:
        status_code = 403

        @staticmethod
        def json() -> dict:
            return {
                "error": {
                    "message": "The request cannot be completed because you have exceeded your quota.",
                }
            }

    def fake_get(*_args, **_kwargs):
        calls["count"] += 1
        return QuotaResponse()

    monkeypatch.setattr(provider, "_valid_access_token", lambda _: "token")
    monkeypatch.setattr(provider._client, "get", fake_get)

    with pytest.raises(ProviderError) as first:
        provider._youtube_get(
            path="videos",
            params={"part": "snippet", "id": "video-1", "maxResults": 1},
            account_id="google_user-1",
            auth_optional=True,
        )
    assert first.value.code == "GOOGLE_API_ERROR"

    with pytest.raises(ProviderError) as second:
        provider._youtube_get(
            path="videos",
            params={"part": "snippet", "id": "video-1", "maxResults": 1},
            account_id="google_user-1",
            auth_optional=True,
        )
    assert second.value.code == "GOOGLE_API_ERROR"
    assert calls["count"] == 1


def test_google_search_suggestions_parses_youtube_suggest_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    class SuggestResponse:
        status_code = 200

        @staticmethod
        def json() -> list:
            return ["smart", ["smarttube", "smarttube tvos", "smart tube profile switch"]]

    monkeypatch.setattr(provider._client, "get", lambda *_args, **_kwargs: SuggestResponse())

    payload = provider.search_suggestions("smart")
    assert payload["query"] == "smart"
    assert payload["suggestions"][:2] == ["smarttube", "smarttube tvos"]


def test_google_related_and_channel_videos_map_search_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    def fake_youtube_get(path: str, params: dict, account_id: str | None, auth_optional: bool) -> dict:
        assert path == "search"
        assert auth_optional is True
        if params.get("relatedToVideoId") == "v1":
            return {
                "items": [
                    {
                        "id": {"videoId": "v2"},
                        "snippet": {
                            "title": "Related Video",
                            "channelTitle": "Channel A",
                            "channelId": "chan-a",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://i.example/v2.jpg"}},
                        },
                    }
                ]
            }
        if params.get("channelId") == "chan-a":
            return {
                "items": [
                    {
                        "id": {"videoId": "v3"},
                        "snippet": {
                            "title": "Channel Upload",
                            "channelTitle": "Channel A",
                            "channelId": "chan-a",
                            "publishedAt": "2026-01-02T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://i.example/v3.jpg"}},
                        },
                    }
                ]
            }
        raise AssertionError("Unexpected params")

    monkeypatch.setattr(provider, "_youtube_get", fake_youtube_get)

    related = provider.video_related("v1", None)
    assert related["title"] == "Up Next"
    assert related["items"][0]["videoId"] == "v2"

    channel = provider.channel_videos("chan-a", None)
    assert channel["items"][0]["videoId"] == "v3"
    assert channel["title"] == "Channel: Channel A"


def test_google_music_feed_personalized_and_popular_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_store = StateStore(tmp_path / "state.json")
    provider = GoogleProvider(settings=_settings(tmp_path / "state.json"), state_store=state_store)

    state_store.update(
        lambda state: state.update(
            {
                "accounts": [
                    {
                        "id": "google_user-1",
                        "name": "Preet",
                        "email": "preet@example.com",
                        "avatarUrl": None,
                        "provider": "google",
                        "ownerSub": "user-1",
                        "tokens": {
                            "accessToken": "token",
                            "refreshToken": "refresh",
                            "expiresAtEpochSec": now_epoch() + 600,
                        },
                    }
                ],
                "selectedAccountId": "google_user-1",
            }
        )
    )

    def personalized_get(path: str, params: dict, account_id: str | None, auth_optional: bool) -> dict:
        assert account_id == "google_user-1"
        if path == "channels":
            return {"items": [{"contentDetails": {"relatedPlaylists": {"likes": "LL"}}}]}
        if path == "playlistItems":
            return {
                "items": [
                    {
                        "contentDetails": {"videoId": "seed1"},
                        "snippet": {"resourceId": {"videoId": "seed1"}},
                    }
                ]
            }
        if path == "activities":
            return {
                "items": [
                    {
                        "contentDetails": {"upload": {"videoId": "m1"}},
                        "snippet": {},
                    }
                ]
            }
        if path == "videos" and params.get("id") == "seed1":
            return {
                "items": [
                    {
                        "id": "seed1",
                        "snippet": {
                            "title": "Latest Punjabi Song Official Video",
                            "channelTitle": "Punjabi Records",
                            "channelId": "chan-seed",
                            "categoryId": "24",
                            "publishedAt": "2026-01-03T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://i.example/seed1.jpg"}},
                        },
                    }
                ]
            }
        if path == "videos" and params.get("id") == "m1":
            return {
                "items": [
                    {
                        "id": "m1",
                        "snippet": {
                            "title": "Music Track",
                            "channelTitle": "Artist",
                            "channelId": "chan-music",
                            "categoryId": "10",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://i.example/m1.jpg"}},
                        },
                    }
                ]
            }
        if path == "videos" and params.get("chart") == "mostPopular":
            return {"items": []}
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(provider, "_youtube_get", personalized_get)
    personalized = provider.feed_music(None)
    assert personalized["title"] == "Music"
    assert personalized["items"][0]["videoId"] == "seed1"
    assert personalized["items"][1]["videoId"] == "m1"

    def popular_get(path: str, params: dict, account_id: str | None, auth_optional: bool) -> dict:
        if path == "channels":
            return {"items": []}
        if path == "activities":
            return {"items": []}
        if path == "videos" and params.get("chart") == "mostPopular":
            return {
                "items": [
                    {
                        "id": "p1",
                        "snippet": {
                            "title": "Popular Music",
                            "channelTitle": "Hit Channel",
                            "channelId": "chan-pop",
                            "categoryId": "10",
                            "publishedAt": "2026-01-02T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://i.example/p1.jpg"}},
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(provider, "_youtube_get", popular_get)
    fallback = provider.feed_music(None)
    assert fallback["items"][0]["videoId"] == "p1"
