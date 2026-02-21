from __future__ import annotations

import copy
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.config import Settings
from app.providers.base import CompanionProvider, ProviderError
from app.state_store import StateStore
from app.util import decode_cursor, encode_cursor, now_epoch

try:
    from yt_dlp import YoutubeDL
except Exception:  # noqa: BLE001
    YoutubeDL = None


DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
GOOGLE_SCOPE = "openid email profile https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_SUGGEST_API = "https://suggestqueries.google.com/complete/search"


class GoogleProvider(CompanionProvider):
    def __init__(self, settings: Settings, state_store: StateStore):
        self._settings = settings
        self._state_store = state_store
        self._client = httpx.Client(timeout=settings.request_timeout_sec)
        self._quota_saver_enabled = os.getenv("YOUTUBE_QUOTA_SAVER", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        self._youtube_response_cache: dict[str, tuple[int, dict[str, Any]]] = {}
        self._cache_ttl_sec = max(int(os.getenv("YOUTUBE_QUOTA_CACHE_TTL_SEC", "180")), 0)
        self._quota_error_ttl_sec = max(int(os.getenv("YOUTUBE_QUOTA_ERROR_TTL_SEC", "60")), 0)
        self._quota_block_until: dict[str, int] = {}

        if not settings.youtube_client_id or not settings.youtube_client_secret:
            raise ProviderError(
                "GOOGLE_CONFIG_MISSING",
                "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are required for google provider",
                status_code=500,
            )

    def get_session(self) -> dict[str, Any]:
        state = self._state_store.read()
        visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
        selected = state.get("selectedAccountId")
        if selected not in visible_ids:
            selected = None
        return {
            "signedIn": selected is not None,
            "selectedAccountId": selected,
        }

    def auth_start(self) -> dict[str, Any]:
        payload = self._request_device_code()
        expires_in = int(payload.get("expires_in", 900))
        interval = int(payload.get("interval", 5))
        verification_url = payload.get("verification_url") or payload.get("verification_uri") or "https://youtube.com/activate"
        verification_url_complete = self._build_verification_url_with_code(verification_url, payload["user_code"])

        pending_auth = {
            "provider": "google",
            "deviceCode": payload["device_code"],
            "signInCode": payload["user_code"],
            "verificationUrl": verification_url,
            "verificationUrlComplete": verification_url_complete,
            "expiresAtEpochSec": now_epoch() + expires_in,
            "pollIntervalSec": interval,
            "nextPollAtEpochSec": now_epoch(),
        }

        def updater(state: dict[str, Any]) -> None:
            state["pendingAuth"] = pending_auth
            state.setdefault("accounts", [])

        self._state_store.update(updater)
        return {
            "status": "PENDING",
            "signInCode": pending_auth["signInCode"],
            "verificationUrl": pending_auth["verificationUrl"],
            "verificationUrlComplete": pending_auth["verificationUrlComplete"],
            "expiresInSec": expires_in,
            "pollIntervalSec": interval,
        }

    def auth_poll(self) -> dict[str, Any]:
        state = self._state_store.read()
        pending = state.get("pendingAuth")

        if not pending:
            visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
            selected = state.get("selectedAccountId")
            if selected not in visible_ids:
                selected = None
            if selected:
                return {
                    "status": "SIGNED_IN",
                    "selectedAccountId": selected,
                }
            return {"status": "PENDING"}

        if pending.get("provider") != "google":
            raise ProviderError("AUTH_STATE_INVALID", "Pending auth exists for another provider", status_code=409)

        now = now_epoch()
        if now > int(pending.get("expiresAtEpochSec", 0)):
            self._state_store.update(lambda s: s.__setitem__("pendingAuth", None))
            raise ProviderError("AUTH_EXPIRED", "Device sign-in flow expired. Start again.", status_code=401)

        if now < int(pending.get("nextPollAtEpochSec", 0)):
            return {"status": "PENDING"}

        token_result = self._poll_device_token(pending["deviceCode"])
        status = token_result.get("status")

        if status == "PENDING":
            wait_sec = int(token_result.get("pollIntervalSec", pending.get("pollIntervalSec", 5)))

            def updater_wait(state_mut: dict[str, Any]) -> None:
                current = state_mut.get("pendingAuth")
                if not current:
                    return
                current["pollIntervalSec"] = wait_sec
                current["nextPollAtEpochSec"] = now_epoch() + wait_sec
                state_mut["pendingAuth"] = current

            self._state_store.update(updater_wait)
            return {"status": "PENDING"}

        if status != "SUCCESS":
            code = token_result.get("code", "AUTH_FAILED")
            message = token_result.get("message", "Auth failed")
            http_status = int(token_result.get("statusCode", 401))
            self._state_store.update(lambda s: s.__setitem__("pendingAuth", None))
            raise ProviderError(code, message, status_code=http_status)

        access_token = token_result["access_token"]
        refresh_token = token_result.get("refresh_token")
        expires_in = int(token_result.get("expires_in", 3600))

        user_info = self._fetch_userinfo(access_token)
        owner_sub = str(user_info["sub"])
        base_account_id = f"google_{owner_sub}"
        scope_value = token_result.get("scope", GOOGLE_SCOPE)

        owned_channels = self._fetch_owned_channels(access_token)
        account_rows = self._build_owner_account_rows(
            owner_sub=owner_sub,
            base_account_id=base_account_id,
            user_info=user_info,
            owned_channels=owned_channels,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope_value=scope_value,
        )
        selected_account_id = self._persist_owner_accounts(
            owner_sub=owner_sub,
            account_rows=account_rows,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope_value=scope_value,
            preferred_selected_id=account_rows[0]["id"] if account_rows else None,
            clear_pending=True,
        )
        return {
            "status": "SIGNED_IN",
            "selectedAccountId": selected_account_id,
        }

    def auth_signout(self) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            state["selectedAccountId"] = None
            state["pendingAuth"] = None

        self._state_store.update(updater)
        return {"status": "SIGNED_OUT"}

    def list_accounts(self) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        visible_accounts = self._visible_accounts(state)
        visible_ids = {str(row.get("id")) for row in visible_accounts}
        if selected not in visible_ids:
            selected = None

        accounts = []
        for row in visible_accounts:
            sanitized = {
                "id": row.get("id"),
                "name": row.get("name"),
                "email": row.get("email"),
                "avatarUrl": row.get("avatarUrl"),
                "selected": row.get("id") == selected,
            }
            accounts.append(sanitized)

        return {
            "selectedAccountId": selected,
            "accounts": accounts,
        }

    def select_account(self, account_id: str | None) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            if account_id is None:
                state["selectedAccountId"] = None
                return
            ids = {str(row.get("id")) for row in self._visible_accounts(state)}
            if account_id not in ids:
                raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)
            state["selectedAccountId"] = account_id

        state = self._state_store.update(updater)
        return {"selectedAccountId": state.get("selectedAccountId")}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
            if account_id not in visible_ids:
                raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)

            state["accounts"] = [row for row in state.get("accounts", []) if str(row.get("id")) != account_id]
            state["localHistory"] = [row for row in state.get("localHistory", []) if str(row.get("accountId")) != account_id]

            if state.get("selectedAccountId") == account_id:
                visible_after = self._visible_accounts(state)
                state["selectedAccountId"] = visible_after[0]["id"] if visible_after else None

        state = self._state_store.update(updater)
        visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
        selected = state.get("selectedAccountId")
        if selected not in visible_ids:
            selected = None
        return {"selectedAccountId": selected}

    def refresh_accounts(self) -> dict[str, Any]:
        state = self._state_store.read()
        visible_accounts = self._visible_accounts(state)
        if not visible_accounts:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)

        selected = state.get("selectedAccountId")
        visible_ids = {str(row.get("id")) for row in visible_accounts}
        anchor_account_id = selected if selected in visible_ids else str(visible_accounts[0].get("id"))
        if not anchor_account_id:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)

        access_token = self._valid_access_token(anchor_account_id)
        anchor = self._get_account_with_token(anchor_account_id)
        tokens = anchor.get("tokens", {})

        user_info = self._fetch_userinfo(access_token)
        owner_sub = str(user_info["sub"])
        base_account_id = f"google_{owner_sub}"
        scope_value = tokens.get("scope") or GOOGLE_SCOPE
        refresh_token = tokens.get("refreshToken")
        expires_at = int(tokens.get("expiresAtEpochSec", now_epoch() + 3600) or 0)
        expires_in = max(expires_at - now_epoch(), 60)

        owned_channels = self._fetch_owned_channels(access_token)
        account_rows = self._build_owner_account_rows(
            owner_sub=owner_sub,
            base_account_id=base_account_id,
            user_info=user_info,
            owned_channels=owned_channels,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope_value=scope_value,
        )
        selected_account_id = self._persist_owner_accounts(
            owner_sub=owner_sub,
            account_rows=account_rows,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope_value=scope_value,
            preferred_selected_id=selected if selected in visible_ids else None,
            clear_pending=False,
        )

        total_profiles = len(self._visible_accounts(self._state_store.read()))
        return {
            "status": "REFRESHED",
            "selectedAccountId": selected_account_id,
            "discoveredProfileCount": len(account_rows),
            "totalProfileCount": total_profiles,
        }

    def feed_home(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._get_selected_account_id(required=False)
        page_token = self._decode_continuation(continuation_token, expected_type="google_home")

        params = {
            "part": "snippet,contentDetails",
            "chart": "mostPopular",
            "regionCode": self._settings.youtube_region,
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="videos",
            params=params,
            account_id=selected,
            auth_optional=True,
        )

        items = [self._feed_item_from_video_resource(item) for item in payload.get("items", [])]
        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_home", "pageToken": next_token}) if next_token else None

        return {
            "title": "Home",
            "continuationToken": continuation,
            "items": [item for item in items if item],
        }

    def feed_music(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._get_selected_account_id(required=False)
        cursor_type: str | None = None
        page_token: str | None = None

        if continuation_token:
            try:
                cursor = decode_cursor(continuation_token)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("INVALID_CONTINUATION", "Invalid continuation token", status_code=400) from exc
            cursor_type = str(cursor.get("type") or "")
            if cursor_type not in {"google_music_personalized", "google_music_popular"}:
                raise ProviderError("INVALID_CONTINUATION", "Continuation token does not match endpoint", status_code=400)
            page_token = cursor.get("pageToken")

        if cursor_type == "google_music_personalized":
            if not selected:
                return self._music_from_popular(page_token=None, account_id=None)
            return self._music_from_personalized(selected, page_token)

        if cursor_type == "google_music_popular":
            return self._music_from_popular(page_token, selected)

        if selected:
            personalized = self._music_from_personalized(selected, page_token=None)
            if personalized["items"]:
                return personalized

        return self._music_from_popular(page_token=None, account_id=selected)

    def feed_subscriptions(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._get_selected_account_id(required=True)
        page_token = self._decode_continuation(continuation_token, expected_type="google_subscriptions")

        params = {
            "part": "snippet,contentDetails",
            "home": "true",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="activities",
            params=params,
            account_id=selected,
            auth_optional=False,
        )

        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            mapped = self._feed_item_from_activity_resource(row)
            if mapped:
                items.append(mapped)

        if not items:
            fallback_payload, items = self._subscriptions_fallback(selected, page_token)
            payload = fallback_payload

        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_subscriptions", "pageToken": next_token}) if next_token else None

        return {
            "title": "Subscriptions",
            "continuationToken": continuation,
            "items": items,
        }

    def feed_history(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._get_selected_account_id(required=True)

        playlist_token = None
        if continuation_token:
            try:
                cursor = decode_cursor(continuation_token)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("INVALID_CONTINUATION", "Invalid continuation token", status_code=400) from exc

            cursor_type = cursor.get("type")
            if cursor_type == "google_history":
                playlist_token = cursor.get("pageToken")
            elif cursor_type == "google_history_local":
                return self._history_from_local_store(selected, continuation_token)
            else:
                raise ProviderError("INVALID_CONTINUATION", "Continuation token does not match endpoint", status_code=400)

        try:
            remote = self._history_from_related_playlist(selected, playlist_token)
            if remote is not None:
                return remote
        except ProviderError:
            pass

        return self._history_from_local_store(selected, continuation_token)

    def search(self, query: str, continuation_token: str | None) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ProviderError("INVALID_QUERY", "q must not be empty", status_code=400)

        selected = self._get_selected_account_id(required=False)
        page_token = self._decode_continuation(continuation_token, expected_type="google_search")

        params = {
            "part": "snippet",
            "q": cleaned_query,
            "type": "video",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="search",
            params=params,
            account_id=selected,
            auth_optional=True,
        )

        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            mapped = self._feed_item_from_search_resource(row)
            if mapped:
                items.append(mapped)

        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_search", "pageToken": next_token}) if next_token else None

        return {
            "title": f"Search: {cleaned_query}",
            "continuationToken": continuation,
            "items": items,
        }

    def search_suggestions(self, query: str) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ProviderError("INVALID_QUERY", "q must not be empty", status_code=400)

        suggestions: list[str] = []
        try:
            response = self._client.get(
                YOUTUBE_SUGGEST_API,
                params={
                    "client": "firefox",
                    "ds": "yt",
                    "q": cleaned_query,
                },
            )
            if response.status_code < 400:
                payload = response.json()
                if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                    for row in payload[1]:
                        if not isinstance(row, str):
                            continue
                        text = row.strip()
                        if text:
                            suggestions.append(text)
        except Exception:  # noqa: BLE001
            suggestions = []

        if not suggestions:
            suggestions = [cleaned_query]

        return {
            "query": cleaned_query,
            "suggestions": suggestions[:10],
        }

    def video_metadata(self, video_id: str) -> dict[str, Any]:
        if not video_id.strip():
            raise ProviderError("VIDEO_NOT_FOUND", "Video id is empty", status_code=404)

        selected = self._get_selected_account_id(required=False)
        payload = self._youtube_get(
            path="videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "maxResults": 1,
            },
            account_id=selected,
            auth_optional=True,
        )

        rows = payload.get("items", [])
        if not rows:
            raise ProviderError("VIDEO_NOT_FOUND", f"Unknown video: {video_id}", status_code=404)

        row = rows[0]
        snippet = row.get("snippet", {})
        stats = row.get("statistics", {})

        comment_count = int(stats.get("commentCount", 0)) if str(stats.get("commentCount", "0")).isdigit() else 0
        comments_key = None
        if comment_count > 0:
            comments_key = encode_cursor(
                {
                    "type": "google_comments",
                    "videoId": video_id,
                    "pageToken": None,
                }
            )

        return {
            "videoId": video_id,
            "title": snippet.get("title") or "",
            "channelName": snippet.get("channelTitle") or "",
            "channelId": snippet.get("channelId") or "",
            "publishedText": self._published_text(snippet.get("publishedAt")),
            "viewCountText": self._count_text(stats.get("viewCount"), suffix=" views"),
            "description": snippet.get("description") or "",
            "commentsKey": comments_key,
            "liveChatKey": None,
        }

    def video_playback(self, video_id: str) -> dict[str, Any]:
        if not video_id.strip():
            raise ProviderError("VIDEO_NOT_FOUND", "Video id is empty", status_code=404)

        stream_data = self._extract_stream(video_id)
        selected = self._get_selected_account_id(required=False)
        if selected:
            self._append_local_history(selected, video_id)

        return {
            "videoId": video_id,
            "streamUrl": stream_data["streamUrl"],
            "mimeType": stream_data["mimeType"],
            "qualityLabel": stream_data.get("qualityLabel"),
            "isAdaptive": stream_data.get("isAdaptive", False),
            "availableStreams": stream_data.get("availableStreams", []),
            "subtitleTracks": stream_data.get("subtitleTracks", []),
            "expiresAtEpochSec": now_epoch() + 3600,
        }

    def video_related(self, video_id: str, continuation_token: str | None) -> dict[str, Any]:
        if not video_id.strip():
            raise ProviderError("VIDEO_NOT_FOUND", "Video id is empty", status_code=404)

        selected = self._get_selected_account_id(required=False)
        page_token = self._decode_continuation(continuation_token, expected_type="google_related")
        params = {
            "part": "snippet",
            "relatedToVideoId": video_id,
            "type": "video",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="search",
            params=params,
            account_id=selected,
            auth_optional=True,
        )
        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            mapped = self._feed_item_from_search_resource(row)
            if mapped and mapped.get("videoId") != video_id:
                items.append(mapped)

        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_related", "videoId": video_id, "pageToken": next_token}) if next_token else None
        return {
            "title": "Up Next",
            "continuationToken": continuation,
            "items": items,
        }

    def channel_videos(self, channel_id: str, continuation_token: str | None) -> dict[str, Any]:
        cleaned = channel_id.strip()
        if not cleaned:
            raise ProviderError("CHANNEL_NOT_FOUND", "Channel id is empty", status_code=404)

        selected = self._get_selected_account_id(required=False)
        page_token = self._decode_continuation(continuation_token, expected_type="google_channel_videos")
        params = {
            "part": "snippet",
            "channelId": cleaned,
            "type": "video",
            "order": "date",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="search",
            params=params,
            account_id=selected,
            auth_optional=True,
        )

        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            mapped = self._feed_item_from_search_resource(row)
            if mapped:
                items.append(mapped)

        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_channel_videos", "channelId": cleaned, "pageToken": next_token}) if next_token else None
        channel_name = items[0].get("channelName") if items else cleaned
        return {
            "title": f"Channel: {channel_name}",
            "continuationToken": continuation,
            "items": items,
        }

    def comments(self, comments_key: str) -> dict[str, Any]:
        cursor = self._decode_comments_cursor(comments_key, expected_type="google_comments")
        video_id = cursor["videoId"]
        page_token = cursor.get("pageToken")

        selected = self._get_selected_account_id(required=False)
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 20,
            "textFormat": "plainText",
            "order": "relevance",
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get_with_public_fallback(
            path="commentThreads",
            params=params,
            account_id=selected,
        )

        items = []
        for row in payload.get("items", []):
            snippet = row.get("snippet", {})
            comment = snippet.get("topLevelComment", {})
            comment_id = comment.get("id") or row.get("id")
            comment_snippet = comment.get("snippet", {})

            nested_key = None
            total_replies = int(snippet.get("totalReplyCount", 0) or 0)
            if comment_id and total_replies > 0:
                nested_key = encode_cursor(
                    {
                        "type": "google_replies",
                        "videoId": video_id,
                        "parentId": comment_id,
                        "pageToken": None,
                    }
                )

            items.append(
                {
                    "id": comment_id,
                    "authorName": comment_snippet.get("authorDisplayName") or "",
                    "authorPhotoUrl": comment_snippet.get("authorProfileImageUrl") or "",
                    "publishedText": self._published_text(comment_snippet.get("publishedAt")),
                    "message": comment_snippet.get("textDisplay") or "",
                    "likeCountText": self._count_text(comment_snippet.get("likeCount")),
                    "replyCountText": str(total_replies),
                    "nestedCommentsKey": nested_key,
                }
            )

        next_token = payload.get("nextPageToken")
        next_key = None
        if next_token:
            next_key = encode_cursor(
                {
                    "type": "google_comments",
                    "videoId": video_id,
                    "pageToken": next_token,
                }
            )

        return {
            "nextCommentsKey": next_key,
            "items": items,
        }

    def comment_replies(self, nested_comments_key: str) -> dict[str, Any]:
        cursor = self._decode_comments_cursor(nested_comments_key, expected_type="google_replies")
        video_id = cursor["videoId"]
        parent_id = cursor["parentId"]
        page_token = cursor.get("pageToken")

        selected = self._get_selected_account_id(required=False)
        params = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": 20,
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get_with_public_fallback(
            path="comments",
            params=params,
            account_id=selected,
        )

        items = []
        for row in payload.get("items", []):
            snippet = row.get("snippet", {})
            items.append(
                {
                    "id": row.get("id"),
                    "authorName": snippet.get("authorDisplayName") or "",
                    "authorPhotoUrl": snippet.get("authorProfileImageUrl") or "",
                    "publishedText": self._published_text(snippet.get("publishedAt")),
                    "message": snippet.get("textDisplay") or "",
                    "likeCountText": self._count_text(snippet.get("likeCount")),
                    "replyCountText": "0",
                    "nestedCommentsKey": None,
                }
            )

        next_token = payload.get("nextPageToken")
        next_key = None
        if next_token:
            next_key = encode_cursor(
                {
                    "type": "google_replies",
                    "videoId": video_id,
                    "parentId": parent_id,
                    "pageToken": next_token,
                }
            )

        return {
            "nextCommentsKey": next_key,
            "items": items,
        }

    def _request_device_code(self) -> dict[str, Any]:
        response = self._client.post(
            DEVICE_CODE_URL,
            data={
                "client_id": self._settings.youtube_client_id,
                "scope": GOOGLE_SCOPE,
            },
        )
        payload = self._json_or_error(response, "GOOGLE_AUTH_START_FAILED", "Could not start device sign-in")
        if "device_code" not in payload or "user_code" not in payload:
            raise ProviderError("GOOGLE_AUTH_START_FAILED", "Device auth response missing required fields", status_code=502)
        return payload

    def _build_verification_url_with_code(self, verification_url: str, user_code: str) -> str:
        parts = urlsplit(verification_url)
        query_items = dict(parse_qsl(parts.query, keep_blank_values=True))
        query_items["user_code"] = user_code
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))

    def _poll_device_token(self, device_code: str) -> dict[str, Any]:
        response = self._client.post(
            TOKEN_URL,
            data={
                "client_id": self._settings.youtube_client_id,
                "client_secret": self._settings.youtube_client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

        if response.status_code == 200:
            payload = self._json_or_error(response, "GOOGLE_AUTH_POLL_FAILED", "Invalid token response")
            return {
                "status": "SUCCESS",
                **payload,
            }

        payload = self._safe_json(response)
        error_code = payload.get("error")
        if error_code == "authorization_pending":
            return {"status": "PENDING"}
        if error_code == "slow_down":
            return {"status": "PENDING", "pollIntervalSec": 10}
        if error_code == "access_denied":
            return {
                "status": "ERROR",
                "code": "AUTH_DENIED",
                "message": "Sign-in was denied in browser",
                "statusCode": 401,
            }
        if error_code == "expired_token":
            return {
                "status": "ERROR",
                "code": "AUTH_EXPIRED",
                "message": "Device sign-in flow expired",
                "statusCode": 401,
            }
        message = payload.get("error_description") or payload.get("error") or "Unknown auth poll error"
        return {
            "status": "ERROR",
            "code": "GOOGLE_AUTH_POLL_FAILED",
            "message": message,
            "statusCode": 502,
        }

    def _fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        response = self._client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        payload = self._json_or_error(response, "GOOGLE_USERINFO_FAILED", "Failed to load account profile")
        if "sub" not in payload:
            raise ProviderError("GOOGLE_USERINFO_FAILED", "User profile payload missing account identifier", status_code=502)
        return payload

    def _fetch_owned_channels(self, access_token: str) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{YOUTUBE_API_BASE}/channels",
            params={
                "part": "snippet",
                "mine": "true",
                "maxResults": 50,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            return []
        payload = self._safe_json(response)
        items = payload.get("items")
        if isinstance(items, list):
            return [row for row in items if isinstance(row, dict)]
        return []

    def _build_owner_account_rows(
        self,
        owner_sub: str,
        base_account_id: str,
        user_info: dict[str, Any],
        owned_channels: list[dict[str, Any]],
        access_token: str,
        refresh_token: str | None,
        expires_in: int,
        scope_value: str,
    ) -> list[dict[str, Any]]:
        account_rows: list[dict[str, Any]] = []
        if owned_channels:
            for index, channel in enumerate(owned_channels):
                channel_id = channel.get("id")
                if not channel_id:
                    continue
                snippet = channel.get("snippet", {})
                account_rows.append(
                    {
                        "id": base_account_id if index == 0 else f"{base_account_id}_{channel_id}",
                        "name": snippet.get("title") or user_info.get("name") or user_info.get("email") or "Google Account",
                        "email": user_info.get("email"),
                        "avatarUrl": self._thumbnail_url(snippet) or user_info.get("picture"),
                        "provider": "google",
                        "ownerSub": owner_sub,
                        "channelId": channel_id,
                        "tokens": {
                            "accessToken": access_token,
                            "refreshToken": refresh_token,
                            "expiresAtEpochSec": now_epoch() + expires_in,
                            "scope": scope_value,
                        },
                    }
                )

        if account_rows:
            return account_rows

        return [
            {
                "id": base_account_id,
                "name": user_info.get("name") or user_info.get("email") or "Google Account",
                "email": user_info.get("email"),
                "avatarUrl": user_info.get("picture"),
                "provider": "google",
                "ownerSub": owner_sub,
                "channelId": None,
                "tokens": {
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                    "expiresAtEpochSec": now_epoch() + expires_in,
                    "scope": scope_value,
                },
            }
        ]

    def _persist_owner_accounts(
        self,
        owner_sub: str,
        account_rows: list[dict[str, Any]],
        access_token: str,
        refresh_token: str | None,
        expires_in: int,
        scope_value: str,
        preferred_selected_id: str | None,
        clear_pending: bool,
    ) -> str | None:
        def updater(state_mut: dict[str, Any]) -> None:
            accounts = state_mut.setdefault("accounts", [])
            previous_refresh = None
            same_owner_rows: list[dict[str, Any]] = []
            filtered: list[dict[str, Any]] = []
            for row in accounts:
                if self._owner_sub_from_row(row) == owner_sub:
                    if not previous_refresh:
                        previous_refresh = row.get("tokens", {}).get("refreshToken")
                    same_owner_rows.append(copy.deepcopy(row))
                    continue
                filtered.append(row)

            by_channel: dict[str, dict[str, Any]] = {}
            for row in account_rows:
                key = str(row.get("channelId") or "")
                by_channel[key] = copy.deepcopy(row)

            for row in same_owner_rows:
                if not self._is_google_account_row(row):
                    continue
                key = str(row.get("channelId") or "")
                if key and key not in by_channel:
                    row["provider"] = "google"
                    row["ownerSub"] = owner_sub
                    by_channel[key] = row

            merged_owner_rows: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for row in by_channel.values():
                row_id = str(row.get("id") or "")
                if not row_id or row_id in seen_ids:
                    continue
                seen_ids.add(row_id)

                row["provider"] = "google"
                row["ownerSub"] = owner_sub
                tokens = row.setdefault("tokens", {})
                tokens["accessToken"] = access_token
                tokens["expiresAtEpochSec"] = now_epoch() + expires_in
                tokens["scope"] = scope_value
                if refresh_token:
                    tokens["refreshToken"] = refresh_token
                elif previous_refresh and not tokens.get("refreshToken"):
                    tokens["refreshToken"] = previous_refresh
                row["tokens"] = tokens
                merged_owner_rows.append(row)

            filtered.extend(merged_owner_rows)
            state_mut["accounts"] = filtered
            selected = state_mut.get("selectedAccountId")
            selected_ids = {str(row.get("id")) for row in self._visible_accounts(state_mut)}
            if selected not in selected_ids:
                selected = preferred_selected_id if preferred_selected_id in selected_ids else None
                if not selected:
                    selected = merged_owner_rows[0]["id"] if merged_owner_rows else None
            state_mut["selectedAccountId"] = selected
            if clear_pending:
                state_mut["pendingAuth"] = None

        state = self._state_store.update(updater)
        visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
        selected = state.get("selectedAccountId")
        if selected not in visible_ids:
            return None
        return selected

    def _refresh_access_token(self, account_id: str, refresh_token: str) -> str:
        account = self._get_account_with_token(account_id)
        owner_sub = self._owner_sub_from_row(account)
        response = self._client.post(
            TOKEN_URL,
            data={
                "client_id": self._settings.youtube_client_id,
                "client_secret": self._settings.youtube_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

        payload = self._json_or_error(response, "AUTH_EXPIRED", "Failed to refresh account token")
        access_token = payload.get("access_token")
        if not access_token:
            raise ProviderError("AUTH_EXPIRED", "Token refresh response missing access token", status_code=401)
        expires_in = int(payload.get("expires_in", 3600))

        def updater(state: dict[str, Any]) -> None:
            for row in state.get("accounts", []):
                same_owner = owner_sub and self._owner_sub_from_row(row) == owner_sub
                if row.get("id") != account_id and not same_owner:
                    continue
                tokens = row.setdefault("tokens", {})
                tokens["accessToken"] = access_token
                tokens["expiresAtEpochSec"] = now_epoch() + expires_in
                if payload.get("refresh_token"):
                    tokens["refreshToken"] = payload["refresh_token"]
                row["tokens"] = tokens

        self._state_store.update(updater)
        return access_token

    def _get_account_with_token(self, account_id: str) -> dict[str, Any]:
        state = self._state_store.read()
        for row in state.get("accounts", []):
            if row.get("id") == account_id:
                return copy.deepcopy(row)
        raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)

    def _valid_access_token(self, account_id: str) -> str:
        account = self._get_account_with_token(account_id)
        tokens = account.get("tokens", {})
        access_token = tokens.get("accessToken")
        expires_at = int(tokens.get("expiresAtEpochSec", 0) or 0)

        if access_token and expires_at > now_epoch() + 30:
            return access_token

        refresh_token = tokens.get("refreshToken")
        if not refresh_token:
            raise ProviderError("AUTH_EXPIRED", "Account token expired and has no refresh token", status_code=401)
        return self._refresh_access_token(account_id, refresh_token)

    def _youtube_get(self, path: str, params: dict[str, Any], account_id: str | None, auth_optional: bool) -> dict[str, Any]:
        query = dict(params)
        headers: dict[str, str] = {}
        cache_key = self._request_cache_key(path=path, params=query, account_id=account_id)
        quota_bucket = self._quota_bucket_key(path=path, account_id=account_id)

        if self._quota_saver_enabled:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
            if self._is_quota_blocked(quota_bucket):
                stale = self._cache_get(cache_key, allow_stale=True)
                if stale is not None:
                    return stale
                raise ProviderError(
                    "GOOGLE_API_ERROR",
                    "Quota recently exceeded for this endpoint; retry after cooldown to avoid burning more requests.",
                    status_code=502,
                )

        if account_id:
            headers["Authorization"] = f"Bearer {self._valid_access_token(account_id)}"
        elif self._settings.youtube_api_key:
            query["key"] = self._settings.youtube_api_key
        elif not auth_optional:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)
        else:
            raise ProviderError(
                "GOOGLE_API_KEY_REQUIRED",
                "YOUTUBE_API_KEY is required for anonymous calls when no account is selected",
                status_code=500,
            )

        response = self._client.get(f"{YOUTUBE_API_BASE}/{path}", params=query, headers=headers)

        if response.status_code == 401:
            raise ProviderError("AUTH_EXPIRED", "Google access token expired or revoked", status_code=401)
        if response.status_code >= 400:
            payload = self._safe_json(response)
            message = payload.get("error", {}).get("message") or payload.get("error_description") or "Google API request failed"
            if self._quota_saver_enabled and self._is_quota_message(message):
                self._mark_quota_blocked(quota_bucket)
                stale = self._cache_get(cache_key, allow_stale=True)
                if stale is not None:
                    return stale
            raise ProviderError("GOOGLE_API_ERROR", message, status_code=502)

        payload = self._safe_json(response)
        if self._quota_saver_enabled:
            self._cache_put(cache_key, payload)
            self._clear_quota_block(quota_bucket)
        return payload

    def _youtube_get_with_public_fallback(self, path: str, params: dict[str, Any], account_id: str | None) -> dict[str, Any]:
        """
        For some endpoints (notably comments), OAuth tokens can still be rejected with
        scope-specific policy errors even when read-only scopes are present. Since these
        reads are public with API key, retry via key to preserve V1 functionality.
        """
        try:
            return self._youtube_get(
                path=path,
                params=params,
                account_id=account_id,
                auth_optional=True,
            )
        except ProviderError as exc:
            if (
                account_id
                and self._settings.youtube_api_key
                and exc.code == "GOOGLE_API_ERROR"
                and "insufficient authentication scopes" in exc.message.lower()
            ):
                return self._youtube_get(
                    path=path,
                    params=params,
                    account_id=None,
                    auth_optional=True,
                )
            raise

    def _decode_continuation(self, token: str | None, expected_type: str) -> str | None:
        if not token:
            return None
        try:
            payload = decode_cursor(token)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("INVALID_CONTINUATION", "Invalid continuation token", status_code=400) from exc

        if payload.get("type") != expected_type:
            raise ProviderError("INVALID_CONTINUATION", "Continuation token does not match endpoint", status_code=400)
        return payload.get("pageToken")

    def _decode_comments_cursor(self, key: str, expected_type: str) -> dict[str, Any]:
        try:
            payload = decode_cursor(key)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("INVALID_COMMENTS_KEY", "Invalid comments key", status_code=400) from exc
        if payload.get("type") != expected_type:
            raise ProviderError("INVALID_COMMENTS_KEY", "Comments key type mismatch", status_code=400)
        return payload

    def _get_selected_account_id(self, required: bool) -> str | None:
        state = self._state_store.read()
        visible_ids = {str(row.get("id")) for row in self._visible_accounts(state)}
        selected = state.get("selectedAccountId")
        if selected not in visible_ids:
            selected = None
        if required and not selected:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)
        return selected

    def _is_google_account_row(self, row: dict[str, Any]) -> bool:
        if row.get("provider") == "google":
            return True
        row_id = str(row.get("id", ""))
        if row_id.startswith("google_"):
            return True
        if row.get("ownerSub"):
            return True
        return False

    def _visible_accounts(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        rows = state.get("accounts", [])
        if not isinstance(rows, list):
            return []
        return [copy.deepcopy(row) for row in rows if isinstance(row, dict) and self._is_google_account_row(row)]

    def _owner_sub_from_row(self, row: dict[str, Any]) -> str | None:
        owner_sub = row.get("ownerSub")
        if owner_sub:
            return str(owner_sub)
        row_id = str(row.get("id", ""))
        if row_id.startswith("google_"):
            remainder = row_id[len("google_") :]
            if remainder:
                return remainder.split("_", 1)[0]
        return None

    def _subscriptions_fallback(self, selected: str, page_token: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        params = {
            "part": "snippet",
            "mine": "true",
            "maxResults": 10,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="subscriptions",
            params=params,
            account_id=selected,
            auth_optional=False,
        )

        channel_ids: list[str] = []
        for row in payload.get("items", []):
            channel_id = row.get("snippet", {}).get("resourceId", {}).get("channelId")
            if channel_id:
                channel_ids.append(str(channel_id))

        if not channel_ids:
            return payload, []

        channels_payload = self._youtube_get(
            path="channels",
            params={
                "part": "snippet,contentDetails",
                "id": ",".join(channel_ids[:50]),
                "maxResults": 50,
            },
            account_id=selected,
            auth_optional=False,
        )

        items: list[dict[str, Any]] = []
        for row in channels_payload.get("items", []):
            channel_id = str(row.get("id") or "")
            uploads_playlist = row.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not channel_id or not uploads_playlist:
                continue

            latest_uploads = self._youtube_get(
                path="playlistItems",
                params={
                    "part": "snippet",
                    "playlistId": uploads_playlist,
                    "maxResults": 1,
                },
                account_id=selected,
                auth_optional=False,
            )

            latest_rows = latest_uploads.get("items", [])
            if not latest_rows:
                continue
            snippet = latest_rows[0].get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue
            items.append(
                {
                    "videoId": video_id,
                    "title": snippet.get("title") or "",
                    "channelName": snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or row.get("snippet", {}).get("title") or "",
                    "channelId": snippet.get("videoOwnerChannelId") or snippet.get("channelId") or channel_id,
                    "thumbnailUrl": self._thumbnail_url(snippet),
                    "publishedText": self._published_text(snippet.get("publishedAt")),
                    "durationSec": 0,
                    "_publishedAt": snippet.get("publishedAt") or "",
                }
            )

        items.sort(key=lambda item: str(item.get("_publishedAt", "")), reverse=True)
        for item in items:
            item.pop("_publishedAt", None)

        return payload, items

    def _history_from_related_playlist(self, selected: str, page_token: str | None) -> dict[str, Any] | None:
        channels = self._youtube_get(
            path="channels",
            params={
                "part": "contentDetails",
                "mine": "true",
                "maxResults": 1,
            },
            account_id=selected,
            auth_optional=False,
        )

        rows = channels.get("items", [])
        if not rows:
            return None

        related = rows[0].get("contentDetails", {}).get("relatedPlaylists", {})
        playlist_id = related.get("watchHistory")
        if not playlist_id:
            return None

        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="playlistItems",
            params=params,
            account_id=selected,
            auth_optional=False,
        )

        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            snippet = row.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue
            items.append(
                {
                    "videoId": video_id,
                    "title": snippet.get("title") or "",
                    "channelName": snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or "",
                    "channelId": snippet.get("videoOwnerChannelId") or "",
                    "thumbnailUrl": self._thumbnail_url(snippet),
                    "publishedText": self._published_text(snippet.get("publishedAt")),
                    "durationSec": 0,
                }
            )

        next_token = payload.get("nextPageToken")
        continuation = encode_cursor({"type": "google_history", "pageToken": next_token}) if next_token else None

        return {
            "title": "History",
            "continuationToken": continuation,
            "items": items,
        }

    def _history_from_local_store(self, selected: str, continuation_token: str | None) -> dict[str, Any]:
        offset = 0
        if continuation_token:
            try:
                payload = decode_cursor(continuation_token)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("INVALID_CONTINUATION", "Invalid continuation token", status_code=400) from exc
            if payload.get("type") != "google_history_local":
                raise ProviderError("INVALID_CONTINUATION", "Continuation token does not match endpoint", status_code=400)
            offset = int(payload.get("offset", 0))

        state = self._state_store.read()
        entries = [row for row in state.get("localHistory", []) if row.get("accountId") == selected]
        entries.sort(key=lambda row: int(row.get("playedAtEpochSec", 0)), reverse=True)

        page = entries[offset : offset + 20]
        items = []
        seen: set[str] = set()
        for row in page:
            video_id = str(row.get("videoId"))
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            items.append(self._best_effort_video_stub(video_id))

        next_offset = offset + 20
        continuation = None
        if next_offset < len(entries):
            continuation = encode_cursor({"type": "google_history_local", "offset": next_offset})

        return {
            "title": "History",
            "continuationToken": continuation,
            "items": items,
        }

    def _best_effort_video_stub(self, video_id: str) -> dict[str, Any]:
        try:
            payload = self.video_metadata(video_id)
            return {
                "videoId": video_id,
                "title": payload.get("title") or "",
                "channelName": payload.get("channelName") or "",
                "channelId": payload.get("channelId") or "",
                "thumbnailUrl": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "publishedText": payload.get("publishedText") or "",
                "durationSec": 0,
            }
        except ProviderError:
            return {
                "videoId": video_id,
                "title": f"Video {video_id}",
                "channelName": "",
                "channelId": "",
                "thumbnailUrl": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "publishedText": "",
                "durationSec": 0,
            }

    def _append_local_history(self, account_id: str, video_id: str) -> None:
        def updater(state: dict[str, Any]) -> None:
            history = state.setdefault("localHistory", [])
            history.append(
                {
                    "accountId": account_id,
                    "videoId": video_id,
                    "playedAtEpochSec": now_epoch(),
                }
            )
            state["localHistory"] = history[-500:]

        self._state_store.update(updater)

    def _feed_item_from_video_resource(self, row: dict[str, Any]) -> dict[str, Any] | None:
        video_id = row.get("id")
        snippet = row.get("snippet", {})
        if not video_id:
            return None
        return {
            "videoId": video_id,
            "title": snippet.get("title") or "",
            "channelName": snippet.get("channelTitle") or "",
            "channelId": snippet.get("channelId") or "",
            "thumbnailUrl": self._thumbnail_url(snippet),
            "publishedText": self._published_text(snippet.get("publishedAt")),
            "durationSec": 0,
        }

    def _feed_item_from_search_resource(self, row: dict[str, Any]) -> dict[str, Any] | None:
        video_id = row.get("id", {}).get("videoId")
        snippet = row.get("snippet", {})
        if not video_id:
            return None
        return {
            "videoId": video_id,
            "title": snippet.get("title") or "",
            "channelName": snippet.get("channelTitle") or "",
            "channelId": snippet.get("channelId") or "",
            "thumbnailUrl": self._thumbnail_url(snippet),
            "publishedText": self._published_text(snippet.get("publishedAt")),
            "durationSec": 0,
        }

    def _feed_item_from_activity_resource(self, row: dict[str, Any]) -> dict[str, Any] | None:
        content = row.get("contentDetails", {})
        video_id = (
            content.get("upload", {}).get("videoId")
            or content.get("playlistItem", {}).get("resourceId", {}).get("videoId")
            or content.get("recommendation", {}).get("resourceId", {}).get("videoId")
        )
        if not video_id:
            return None

        snippet = row.get("snippet", {})
        return {
            "videoId": video_id,
            "title": snippet.get("title") or "",
            "channelName": snippet.get("channelTitle") or "",
            "channelId": snippet.get("channelId") or "",
            "thumbnailUrl": self._thumbnail_url(snippet),
            "publishedText": self._published_text(snippet.get("publishedAt")),
            "durationSec": 0,
        }

    def _music_from_personalized(self, account_id: str, page_token: str | None) -> dict[str, Any]:
        preferred_terms: set[str] = set()
        candidate_rows: list[dict[str, Any]] = []
        if not page_token:
            liked_rows = self._music_seed_rows_from_likes(account_id)
            preferred_terms = self._music_preference_terms_from_rows(liked_rows)
            candidate_rows.extend(liked_rows)

        params = {
            "part": "snippet,contentDetails",
            "home": "true",
            "maxResults": 25,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="activities",
            params=params,
            account_id=account_id,
            auth_optional=False,
        )

        ordered_video_ids = self._video_ids_from_activities(payload.get("items", []))
        items: list[dict[str, Any]] = []
        if ordered_video_ids:
            videos_payload = self._youtube_get(
                path="videos",
                params={
                    "part": "snippet,contentDetails",
                    "id": ",".join(ordered_video_ids[:50]),
                    "maxResults": 50,
                },
                account_id=account_id,
                auth_optional=False,
            )
            by_id = {str(row.get("id") or ""): row for row in videos_payload.get("items", []) if isinstance(row, dict)}
            for video_id in ordered_video_ids:
                row = by_id.get(video_id)
                if row:
                    candidate_rows.append(row)

        seen_video_ids: set[str] = set()
        for row in candidate_rows:
            video_id = str(row.get("id") or "")
            if not video_id or video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)
            if not self._looks_like_music_video(row, preferred_terms=preferred_terms):
                continue
            mapped = self._feed_item_from_video_resource(row)
            if mapped:
                items.append(mapped)

        if not page_token and preferred_terms and len(items) < 20:
            region_override = self._music_region_override_from_preferences(preferred_terms)
            popular_rows, _ = self._music_popular_rows(
                page_token=None,
                account_id=account_id,
                region_override=region_override,
            )
            for row in popular_rows:
                video_id = str(row.get("id") or "")
                if not video_id or video_id in seen_video_ids:
                    continue
                seen_video_ids.add(video_id)
                if not self._looks_like_music_video(row, preferred_terms=preferred_terms):
                    continue
                mapped = self._feed_item_from_video_resource(row)
                if not mapped:
                    continue
                items.append(mapped)
                if len(items) >= 20:
                    break

        next_token = payload.get("nextPageToken")
        continuation = (
            encode_cursor({"type": "google_music_personalized", "pageToken": next_token}) if next_token else None
        )
        return {
            "title": "Music",
            "continuationToken": continuation,
            "items": items,
        }

    def _music_from_popular(self, page_token: str | None, account_id: str | None) -> dict[str, Any]:
        popular_rows, next_token = self._music_popular_rows(
            page_token=page_token,
            account_id=account_id,
            region_override=None,
        )
        items = [self._feed_item_from_video_resource(item) for item in popular_rows]
        continuation = encode_cursor({"type": "google_music_popular", "pageToken": next_token}) if next_token else None
        return {
            "title": "Music",
            "continuationToken": continuation,
            "items": [item for item in items if item],
        }

    def _music_popular_rows(
        self,
        page_token: str | None,
        account_id: str | None,
        region_override: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params = {
            "part": "snippet,contentDetails",
            "chart": "mostPopular",
            "regionCode": region_override or self._settings.youtube_region,
            "videoCategoryId": "10",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = self._youtube_get(
            path="videos",
            params=params,
            account_id=account_id,
            auth_optional=True,
        )
        rows = [item for item in payload.get("items", []) if isinstance(item, dict)]
        next_token = payload.get("nextPageToken")
        return rows, next_token

    def _music_seed_rows_from_likes(self, account_id: str) -> list[dict[str, Any]]:
        channels_payload = self._youtube_get(
            path="channels",
            params={
                "part": "contentDetails",
                "mine": "true",
                "maxResults": 1,
            },
            account_id=account_id,
            auth_optional=False,
        )
        channel_rows = [row for row in channels_payload.get("items", []) if isinstance(row, dict)]
        if not channel_rows:
            return []

        likes_playlist_id = (
            channel_rows[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("likes")
        )
        if not likes_playlist_id:
            return []

        playlist_payload = self._youtube_get(
            path="playlistItems",
            params={
                "part": "snippet,contentDetails",
                "playlistId": likes_playlist_id,
                "maxResults": 25,
            },
            account_id=account_id,
            auth_optional=False,
        )
        ordered_video_ids = self._video_ids_from_playlist_items(playlist_payload.get("items", []))
        if not ordered_video_ids:
            return []

        videos_payload = self._youtube_get(
            path="videos",
            params={
                "part": "snippet,contentDetails",
                "id": ",".join(ordered_video_ids[:50]),
                "maxResults": 50,
            },
            account_id=account_id,
            auth_optional=False,
        )
        by_id = {str(row.get("id") or ""): row for row in videos_payload.get("items", []) if isinstance(row, dict)}
        rows: list[dict[str, Any]] = []
        for video_id in ordered_video_ids:
            row = by_id.get(video_id)
            if row:
                rows.append(row)
        return rows

    def _video_ids_from_activities(self, activity_rows: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for row in activity_rows:
            content = row.get("contentDetails", {})
            video_id = (
                content.get("upload", {}).get("videoId")
                or content.get("playlistItem", {}).get("resourceId", {}).get("videoId")
                or content.get("recommendation", {}).get("resourceId", {}).get("videoId")
            )
            if not video_id:
                continue
            string_id = str(video_id)
            if string_id in seen:
                continue
            seen.add(string_id)
            ids.append(string_id)
        return ids

    def _video_ids_from_playlist_items(self, playlist_rows: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for row in playlist_rows:
            snippet = row.get("snippet", {})
            content = row.get("contentDetails", {})
            video_id = content.get("videoId") or snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue
            string_id = str(video_id)
            if string_id in seen:
                continue
            seen.add(string_id)
            ids.append(string_id)
        return ids

    def _music_preference_terms_from_rows(self, video_rows: list[dict[str, Any]]) -> set[str]:
        terms: set[str] = set()
        for row in video_rows:
            snippet = row.get("snippet", {})
            title = str(snippet.get("title") or "").lower()
            channel = str(snippet.get("channelTitle") or "").lower()
            combined = f"{title} {channel}"

            if "punjabi" in combined or self._contains_gurmukhi(combined):
                terms.update({"punjabi", "bhangra", "desi"})
            for marker in (
                "sidhu",
                "moosewala",
                "diljit",
                "aujla",
                "dhillon",
                "ammy",
                "gurnam",
                "karan",
                "jassa",
                "shubh",
                "arjan",
                "gurlez",
            ):
                if marker in combined:
                    terms.add(marker)
        return terms

    def _music_region_override_from_preferences(self, preferred_terms: set[str]) -> str | None:
        if {"punjabi", "bhangra", "desi"} & preferred_terms:
            return "IN"
        return None

    def _contains_gurmukhi(self, value: str) -> bool:
        for char in value:
            codepoint = ord(char)
            if 0x0A00 <= codepoint <= 0x0A7F:
                return True
        return False

    def _looks_like_music_video(self, video_row: dict[str, Any], preferred_terms: set[str] | None = None) -> bool:
        snippet = video_row.get("snippet", {})
        category = str(snippet.get("categoryId") or "")
        if category == "10":
            return True

        title = str(snippet.get("title") or "").lower()
        channel = str(snippet.get("channelTitle") or "").lower()
        combined = f"{title} {channel}"

        music_terms = (
            "music",
            "song",
            "track",
            "album",
            "single",
            "remix",
            "official video",
            "official audio",
            "lyric",
            "lyrics",
            "visualizer",
            "vevo",
            "records",
            "topic",
            "soundtrack",
            "feat.",
            " ft ",
            " ft.",
            " x ",
            "prod.",
            " punjabi song",
            " punjabi music",
            "bhangra",
            "gurbani",
        )
        if any(term in combined for term in music_terms):
            return True

        if self._contains_gurmukhi(combined):
            music_markers = ("official", "video", "audio", "song", "lyric", "music")
            if any(marker in combined for marker in music_markers):
                return True

        if preferred_terms:
            normalized_terms = {term.strip().lower() for term in preferred_terms if len(term.strip()) >= 3}
            if normalized_terms and any(term in combined for term in normalized_terms):
                confidence_markers = ("official", "video", "audio", "song", "music", "lyric", "records", "topic")
                if any(marker in combined for marker in confidence_markers):
                    return True

        return False

    def _extract_stream(self, video_id: str) -> dict[str, Any]:
        if YoutubeDL is None:
            raise ProviderError(
                "PLAYBACK_EXTRACTOR_MISSING",
                "yt-dlp dependency missing; install requirements to enable playback URL extraction",
                status_code=500,
            )

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        info: dict[str, Any] | None = None
        last_error: Exception | None = None

        # Prefer adaptive/modern formats first, then progressively looser fallbacks.
        for fmt in (
            "bestvideo*+bestaudio/best",
            "best[height>=1080][acodec!=none][vcodec!=none]/best[acodec!=none][vcodec!=none]/best",
            "best",
            "b",
        ):
            try:
                with YoutubeDL(
                    {
                        "quiet": True,
                        "no_warnings": True,
                        "skip_download": True,
                        "noplaylist": True,
                        "format": fmt,
                        "extractor_args": {"youtube": {"player_client": ["tv"]}},
                    }
                ) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                if info:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        if not info:
            raise ProviderError(
                "PLAYBACK_UNAVAILABLE",
                f"Could not resolve stream URL: {last_error}",
                status_code=502,
            ) from last_error

        candidate_formats = [row for row in (info.get("formats") or []) if isinstance(row, dict)]
        playable_formats = [row for row in candidate_formats if self._is_playable_av_format(row)]
        if not playable_formats:
            playable_formats = [row for row in candidate_formats if row.get("url")]

        available_streams = self._available_stream_options(playable_formats)
        subtitle_tracks = self._subtitle_tracks_from_info(info)

        selected_format: dict[str, Any] | None = None
        if playable_formats:
            selected_format = max(playable_formats, key=self._playback_format_rank)

        direct_url = (selected_format or {}).get("url") or info.get("url")
        ext = (selected_format or {}).get("ext") or info.get("ext")

        if not direct_url:
            raise ProviderError("PLAYBACK_UNAVAILABLE", "No playable stream URL found", status_code=502)

        mime_type = self._mime_type_for_format(selected_format, fallback_ext=ext)
        quality_label = self._quality_label_for_format(selected_format)

        is_adaptive = bool(selected_format and self._is_adaptive_stream(selected_format))
        return {
            "streamUrl": direct_url,
            "mimeType": mime_type,
            "qualityLabel": quality_label,
            "isAdaptive": is_adaptive,
            "availableStreams": available_streams,
            "subtitleTracks": subtitle_tracks,
        }

    def _available_stream_options(self, playable_formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = sorted(playable_formats, key=self._playback_format_rank, reverse=True)
        options: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in ranked:
            stream_url = row.get("url")
            if not stream_url:
                continue
            quality_label = self._quality_label_for_format(row) or "auto"
            adaptive = self._is_adaptive_stream(row)
            signature = f"{quality_label}:{adaptive}"
            if signature in seen:
                continue
            seen.add(signature)
            options.append(
                {
                    "id": str(row.get("format_id") or signature),
                    "streamUrl": stream_url,
                    "mimeType": self._mime_type_for_format(row),
                    "qualityLabel": quality_label,
                    "isAdaptive": adaptive,
                }
            )
            if len(options) >= 8:
                break
        return options

    def _subtitle_tracks_from_info(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for source_key, is_auto in (("subtitles", False), ("automatic_captions", True)):
            source = info.get(source_key) or {}
            if not isinstance(source, dict):
                continue
            for language, variants in source.items():
                if not isinstance(variants, list):
                    continue
                picked = None
                for variant in variants:
                    if not isinstance(variant, dict):
                        continue
                    url = variant.get("url")
                    ext = str(variant.get("ext") or "").lower()
                    if not url:
                        continue
                    if ext in ("vtt", "ttml", "srv3", "json3", ""):
                        picked = variant
                        break
                if not picked:
                    continue
                url = picked.get("url")
                if not url:
                    continue
                track_id = f"{language}:{'auto' if is_auto else 'manual'}"
                if track_id in seen_ids:
                    continue
                seen_ids.add(track_id)
                name = str(picked.get("name") or "").strip()
                tracks.append(
                    {
                        "id": track_id,
                        "language": str(language),
                        "label": name or str(language),
                        "url": url,
                        "isAutoGenerated": is_auto,
                    }
                )
                if len(tracks) >= 12:
                    return tracks
        return tracks

    def _quality_label_for_format(self, fmt: dict[str, Any] | None) -> str | None:
        if not fmt:
            return None
        height = int(fmt.get("height") or 0)
        fps = int(fmt.get("fps") or 0)
        if height > 0:
            if fps >= 50:
                return f"{height}p{fps}"
            return f"{height}p"
        return str(fmt.get("format_note") or "").strip() or None

    def _mime_type_for_format(self, fmt: dict[str, Any] | None, fallback_ext: str | None = None) -> str:
        ext = str((fmt or {}).get("ext") or fallback_ext or "").lower()
        protocol = str((fmt or {}).get("protocol") or "").lower()
        if ext == "m3u8" or "m3u8" in protocol:
            return "application/x-mpegURL"
        if ext == "webm":
            return "video/webm"
        if ext == "mpd":
            return "application/dash+xml"
        return "video/mp4"

    def _is_playable_av_format(self, fmt: dict[str, Any]) -> bool:
        has_url = bool(fmt.get("url"))
        has_video = str(fmt.get("vcodec") or "none") != "none"
        has_audio = str(fmt.get("acodec") or "none") != "none"
        return has_url and has_video and has_audio

    def _is_adaptive_stream(self, fmt: dict[str, Any]) -> bool:
        protocol = str(fmt.get("protocol") or "").lower()
        ext = str(fmt.get("ext") or "").lower()
        return "m3u8" in protocol or ext == "m3u8"

    def _playback_format_rank(self, fmt: dict[str, Any]) -> tuple[int, int, int, int]:
        # Prefer higher resolution first; for ties prefer adaptive playlists.
        height = int(fmt.get("height") or 0)
        tbr = int(float(fmt.get("tbr") or fmt.get("abr") or 0))
        fps = int(float(fmt.get("fps") or 0))
        adaptive = 1 if self._is_adaptive_stream(fmt) else 0
        return (height, fps, tbr, adaptive)

    def _published_text(self, published_at: str | None) -> str:
        if not published_at:
            return ""
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(UTC)
            delta = datetime.now(UTC) - published
            seconds = max(int(delta.total_seconds()), 0)
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                minutes = seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            if seconds < 86400:
                hours = seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            if seconds < 604800:
                days = seconds // 86400
                return f"{days} day{'s' if days != 1 else ''} ago"
            weeks = seconds // 604800
            if weeks < 5:
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"
            months = seconds // 2592000
            if months < 12:
                return f"{months} month{'s' if months != 1 else ''} ago"
            years = seconds // 31536000
            return f"{years} year{'s' if years != 1 else ''} ago"
        except Exception:  # noqa: BLE001
            return ""

    def _count_text(self, value: Any, suffix: str = "") -> str:
        try:
            num = int(value)
        except Exception:  # noqa: BLE001
            return "0" + suffix if suffix else "0"

        if num >= 1_000_000_000:
            text = f"{num / 1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            text = f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            text = f"{num / 1_000:.1f}K"
        else:
            text = str(num)

        if text.endswith(".0K") or text.endswith(".0M") or text.endswith(".0B"):
            text = text.replace(".0", "")
        return text + suffix

    def _thumbnail_url(self, snippet: dict[str, Any]) -> str:
        thumbs = snippet.get("thumbnails", {})
        for key in ("maxres", "standard", "high", "medium", "default"):
            entry = thumbs.get(key)
            if entry and entry.get("url"):
                return entry["url"]
        return ""

    def _request_cache_key(self, path: str, params: dict[str, Any], account_id: str | None) -> str:
        normalized = tuple(sorted((str(key), str(value)) for key, value in params.items()))
        auth_marker = f"acct:{account_id}" if account_id else "api-key"
        return f"{path}|{auth_marker}|{normalized}"

    def _quota_bucket_key(self, path: str, account_id: str | None) -> str:
        auth_marker = f"acct:{account_id}" if account_id else "api-key"
        return f"{path}|{auth_marker}"

    def _cache_get(self, cache_key: str, allow_stale: bool = False) -> dict[str, Any] | None:
        record = self._youtube_response_cache.get(cache_key)
        if not record:
            return None
        expires_at, payload = record
        if expires_at > now_epoch() or allow_stale:
            return copy.deepcopy(payload)
        self._youtube_response_cache.pop(cache_key, None)
        return None

    def _cache_put(self, cache_key: str, payload: dict[str, Any]) -> None:
        if self._cache_ttl_sec <= 0:
            return
        self._youtube_response_cache[cache_key] = (now_epoch() + self._cache_ttl_sec, copy.deepcopy(payload))

    def _is_quota_blocked(self, quota_bucket: str) -> bool:
        blocked_until = self._quota_block_until.get(quota_bucket, 0)
        if blocked_until <= now_epoch():
            self._quota_block_until.pop(quota_bucket, None)
            return False
        return True

    def _mark_quota_blocked(self, quota_bucket: str) -> None:
        if self._quota_error_ttl_sec <= 0:
            return
        self._quota_block_until[quota_bucket] = now_epoch() + self._quota_error_ttl_sec

    def _clear_quota_block(self, quota_bucket: str) -> None:
        self._quota_block_until.pop(quota_bucket, None)

    def _is_quota_message(self, message: str) -> bool:
        lowered = message.lower()
        return "quota" in lowered and ("exceed" in lowered or "limit" in lowered)

    def _json_or_error(self, response: httpx.Response, code: str, default_message: str) -> dict[str, Any]:
        if response.status_code >= 400:
            payload = self._safe_json(response)
            message = payload.get("error_description")
            if not message:
                error = payload.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                elif isinstance(error, str):
                    message = error
            raise ProviderError(code, message or default_message, status_code=502)
        return self._safe_json(response)

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            if isinstance(data, dict):
                return data
            return {}
        except Exception:  # noqa: BLE001
            return {}
