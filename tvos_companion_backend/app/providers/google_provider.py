from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

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


class GoogleProvider(CompanionProvider):
    def __init__(self, settings: Settings, state_store: StateStore):
        self._settings = settings
        self._state_store = state_store
        self._client = httpx.Client(timeout=settings.request_timeout_sec)

        if not settings.youtube_client_id or not settings.youtube_client_secret:
            raise ProviderError(
                "GOOGLE_CONFIG_MISSING",
                "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are required for google provider",
                status_code=500,
            )

    def get_session(self) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        return {
            "signedIn": selected is not None,
            "selectedAccountId": selected,
        }

    def auth_start(self) -> dict[str, Any]:
        payload = self._request_device_code()
        expires_in = int(payload.get("expires_in", 900))
        interval = int(payload.get("interval", 5))

        pending_auth = {
            "provider": "google",
            "deviceCode": payload["device_code"],
            "signInCode": payload["user_code"],
            "verificationUrl": payload.get("verification_url") or payload.get("verification_uri") or "https://youtube.com/activate",
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
            "expiresInSec": expires_in,
            "pollIntervalSec": interval,
        }

    def auth_poll(self) -> dict[str, Any]:
        state = self._state_store.read()
        pending = state.get("pendingAuth")

        if not pending:
            selected = state.get("selectedAccountId")
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
        account_id = f"google_{user_info['sub']}"
        account_row = {
            "id": account_id,
            "name": user_info.get("name") or user_info.get("email") or "Google Account",
            "email": user_info.get("email"),
            "avatarUrl": user_info.get("picture"),
            "provider": "google",
            "tokens": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresAtEpochSec": now_epoch() + expires_in,
                "scope": token_result.get("scope", GOOGLE_SCOPE),
            },
        }

        def updater_complete(state_mut: dict[str, Any]) -> None:
            accounts = state_mut.setdefault("accounts", [])
            replaced = False
            for index, row in enumerate(accounts):
                if row.get("id") == account_id:
                    previous_tokens = row.get("tokens", {})
                    merged = copy.deepcopy(account_row)
                    if not merged["tokens"].get("refreshToken"):
                        merged["tokens"]["refreshToken"] = previous_tokens.get("refreshToken")
                    accounts[index] = merged
                    replaced = True
                    break
            if not replaced:
                accounts.append(account_row)
            state_mut["accounts"] = accounts
            state_mut["selectedAccountId"] = account_id
            state_mut["pendingAuth"] = None

        self._state_store.update(updater_complete)
        return {
            "status": "SIGNED_IN",
            "selectedAccountId": account_id,
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

        accounts = []
        for row in state.get("accounts", []):
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
            ids = {str(row.get("id")) for row in state.get("accounts", [])}
            if account_id not in ids:
                raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)
            state["selectedAccountId"] = account_id

        state = self._state_store.update(updater)
        return {"selectedAccountId": state.get("selectedAccountId")}

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
            "expiresAtEpochSec": now_epoch() + 3600,
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

    def _refresh_access_token(self, account_id: str, refresh_token: str) -> str:
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
                if row.get("id") != account_id:
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
            raise ProviderError("GOOGLE_API_ERROR", message, status_code=502)

        return self._safe_json(response)

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
        selected = state.get("selectedAccountId")
        if required and not selected:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)
        return selected

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

        items: list[dict[str, Any]] = []
        for row in payload.get("items", []):
            channel_id = row.get("snippet", {}).get("resourceId", {}).get("channelId")
            if not channel_id:
                continue
            search_payload = self._youtube_get(
                path="search",
                params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "order": "date",
                    "type": "video",
                    "maxResults": 1,
                },
                account_id=selected,
                auth_optional=False,
            )
            for hit in search_payload.get("items", []):
                mapped = self._feed_item_from_search_resource(hit)
                if mapped:
                    items.append(mapped)

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

    def _extract_stream(self, video_id: str) -> dict[str, str]:
        if YoutubeDL is None:
            raise ProviderError(
                "PLAYBACK_EXTRACTOR_MISSING",
                "yt-dlp dependency missing; install requirements to enable playback URL extraction",
                status_code=500,
            )

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        info: dict[str, Any] | None = None
        last_error: Exception | None = None

        # Try progressively looser format expressions for real-world availability.
        for fmt in (
            "best[acodec!=none][vcodec!=none]/best",
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

        direct_url = info.get("url")
        ext = info.get("ext")
        if not direct_url:
            requested_formats = info.get("requested_formats") or []
            for fmt in requested_formats:
                candidate_url = fmt.get("url")
                if candidate_url:
                    direct_url = candidate_url
                    ext = fmt.get("ext")
                    break

        if not direct_url:
            formats = info.get("formats") or []
            for fmt in reversed(formats):
                candidate_url = fmt.get("url")
                if candidate_url:
                    direct_url = candidate_url
                    ext = fmt.get("ext")
                    break

        if not direct_url:
            raise ProviderError("PLAYBACK_UNAVAILABLE", "No playable stream URL found", status_code=502)

        mime_type = "video/mp4"
        if ext == "m3u8":
            mime_type = "application/x-mpegURL"

        return {
            "streamUrl": direct_url,
            "mimeType": mime_type,
        }

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
