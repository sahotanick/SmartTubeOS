from __future__ import annotations

import copy
import secrets
from typing import Any

from app.mock_data import (
    ACCOUNTS,
    COMMENTS_BY_VIDEO_ID,
    HISTORY_FEED,
    HOME_FEED_ANON,
    HOME_FEED_SIGNED_IN,
    MUSIC_FEED_ANON,
    MUSIC_FEED_SIGNED_IN,
    PLAYBACK_DEFAULT,
    SUBSCRIPTIONS_FEED,
    VIDEO_BY_ID,
    VIDEOS,
    feed_item,
    metadata,
)
from app.providers.base import CompanionProvider, ProviderError
from app.state_store import StateStore
from app.util import decode_cursor, encode_cursor, now_epoch


FEED_PAGE_SIZE = 4
COMMENTS_PAGE_SIZE = 2
REPLIES_PAGE_SIZE = 3


class MockProvider(CompanionProvider):
    def __init__(self, state_store: StateStore):
        self._state_store = state_store
        self._seed_accounts()

    def get_session(self) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        return {
            "signedIn": selected is not None,
            "selectedAccountId": selected,
        }

    def auth_start(self) -> dict[str, Any]:
        sign_in_code = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        verification_url = "https://youtube.com/activate"
        verification_url_complete = f"{verification_url}?user_code={sign_in_code}"

        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)
            state["pendingAuth"] = {
                "signInCode": sign_in_code,
                "verificationUrl": verification_url,
                "verificationUrlComplete": verification_url_complete,
                "expiresAtEpochSec": now_epoch() + 900,
                "pollIntervalSec": 5,
                "pollCount": 0,
                "readyAfterPollCount": 2,
                "targetAccountId": self._next_account_id(state),
            }

        self._state_store.update(updater)
        return {
            "status": "PENDING",
            "signInCode": sign_in_code,
            "verificationUrl": verification_url,
            "verificationUrlComplete": verification_url_complete,
            "expiresInSec": 900,
            "pollIntervalSec": 5,
        }

    def auth_poll(self) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)
            pending = state.get("pendingAuth")
            if not pending:
                return
            pending["pollCount"] = int(pending.get("pollCount", 0)) + 1
            if pending["pollCount"] >= int(pending.get("readyAfterPollCount", 2)):
                state["selectedAccountId"] = pending.get("targetAccountId") or ACCOUNTS[0]["id"]
                state["pendingAuth"] = None
            else:
                state["pendingAuth"] = pending

        state = self._state_store.update(updater)
        if state.get("selectedAccountId"):
            return {
                "status": "SIGNED_IN",
                "selectedAccountId": state["selectedAccountId"],
            }
        return {"status": "PENDING"}

    def auth_signout(self) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            state["selectedAccountId"] = None
            state["pendingAuth"] = None

        self._state_store.update(updater)
        return {"status": "SIGNED_OUT"}

    def list_accounts(self) -> dict[str, Any]:
        state = self._state_store.read()
        self._ensure_accounts(state)
        selected = state.get("selectedAccountId")
        accounts = []
        for account in state.get("accounts", []):
            row = copy.deepcopy(account)
            row["selected"] = row["id"] == selected
            accounts.append(row)
        return {
            "selectedAccountId": selected,
            "accounts": accounts,
        }

    def select_account(self, account_id: str | None) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)
            if account_id is None:
                state["selectedAccountId"] = None
                return
            valid_ids = {row["id"] for row in state.get("accounts", [])}
            if account_id not in valid_ids:
                raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)
            state["selectedAccountId"] = account_id

        state = self._state_store.update(updater)
        return {"selectedAccountId": state.get("selectedAccountId")}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)
            accounts = state.get("accounts", [])
            existing_ids = {row.get("id") for row in accounts}
            if account_id not in existing_ids:
                raise ProviderError("ACCOUNT_NOT_FOUND", f"Unknown account: {account_id}", status_code=404)

            state["accounts"] = [row for row in accounts if row.get("id") != account_id]

            if state.get("selectedAccountId") == account_id:
                next_selected = state["accounts"][0]["id"] if state["accounts"] else None
                state["selectedAccountId"] = next_selected

        state = self._state_store.update(updater)
        return {"selectedAccountId": state.get("selectedAccountId")}

    def refresh_accounts(self) -> dict[str, Any]:
        state = self._state_store.read()
        self._ensure_accounts(state)
        selected = state.get("selectedAccountId")
        account_count = len(state.get("accounts", []))
        return {
            "status": "REFRESHED",
            "selectedAccountId": selected,
            "discoveredProfileCount": account_count,
            "totalProfileCount": account_count,
        }

    def recommendation_feedback(self, video_id: str, channel_id: str | None, action: str) -> dict[str, Any]:
        cleaned_video_id = video_id.strip()
        cleaned_channel_id = (channel_id or "").strip()
        normalized_action = action.strip().upper()
        if normalized_action not in {"NOT_INTERESTED", "DONT_RECOMMEND_CHANNEL"}:
            raise ProviderError("INVALID_ACTION", "Unsupported recommendation feedback action", status_code=400)
        if normalized_action == "NOT_INTERESTED" and not cleaned_video_id:
            raise ProviderError("INVALID_VIDEO_ID", "videoId is required for NOT_INTERESTED", status_code=400)
        if not cleaned_channel_id and cleaned_video_id in VIDEO_BY_ID:
            cleaned_channel_id = VIDEO_BY_ID[cleaned_video_id].channel_id
        if normalized_action == "DONT_RECOMMEND_CHANNEL" and not cleaned_channel_id:
            raise ProviderError("INVALID_CHANNEL_ID", "channelId is required for DONT_RECOMMEND_CHANNEL", status_code=400)

        account_scope = self._recommendation_scope_account_id()

        def updater(state: dict[str, Any]) -> None:
            preferences = self._ensure_recommendation_preferences(state, account_scope)
            if normalized_action == "NOT_INTERESTED":
                hidden_ids = preferences.setdefault("hiddenVideoIds", [])
                if cleaned_video_id and cleaned_video_id not in hidden_ids:
                    hidden_ids.append(cleaned_video_id)
                if cleaned_video_id in VIDEO_BY_ID:
                    title = VIDEO_BY_ID[cleaned_video_id].title.lower()
                    muted_terms = preferences.setdefault("mutedTerms", [])
                    for term in self._tokenize_terms(title)[:5]:
                        if term not in muted_terms:
                            muted_terms.append(term)
                    if len(muted_terms) > 200:
                        del muted_terms[:-200]
                if len(hidden_ids) > 500:
                    del hidden_ids[:-500]
            else:
                blocked_channels = preferences.setdefault("blockedChannelIds", [])
                if cleaned_channel_id not in blocked_channels:
                    blocked_channels.append(cleaned_channel_id)
                if len(blocked_channels) > 500:
                    del blocked_channels[:-500]
            preferences["updatedAtEpochSec"] = now_epoch()

        state = self._state_store.update(updater)
        prefs = self._get_recommendation_preferences(state, account_scope)
        return {
            "status": "OK",
            "accountId": account_scope,
            "action": normalized_action,
            "hiddenVideoCount": len(prefs.get("hiddenVideoIds", [])),
            "blockedChannelCount": len(prefs.get("blockedChannelIds", [])),
            "mutedTermCount": len(prefs.get("mutedTerms", [])),
        }

    def feed_home(self, continuation_token: str | None) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        if selected and selected in HOME_FEED_SIGNED_IN:
            ids = HOME_FEED_SIGNED_IN[selected]
            title = "Home"
        else:
            ids = HOME_FEED_ANON
            title = "Home"
        account_scope = selected if selected else "__anon__"
        items = [feed_item(video_id) for video_id in ids]
        items = self._filter_items_for_preferences(items, account_scope, state)
        return self._paginate_feed(
            items=items,
            title=title,
            continuation_token=continuation_token,
            expected_kind="home",
        )

    def feed_music(self, continuation_token: str | None) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        if selected and selected in MUSIC_FEED_SIGNED_IN:
            ids = MUSIC_FEED_SIGNED_IN[selected]
            expected_kind = f"music:{selected}"
        else:
            ids = MUSIC_FEED_ANON
            expected_kind = "music"
        account_scope = selected if selected else "__anon__"
        items = [feed_item(video_id) for video_id in ids]
        items = self._filter_items_for_preferences(items, account_scope, state)
        return self._paginate_feed(
            items=items,
            title="Music",
            continuation_token=continuation_token,
            expected_kind=expected_kind,
        )

    def feed_subscriptions(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._require_selected_account()
        ids = SUBSCRIPTIONS_FEED.get(selected, [])
        state = self._state_store.read()
        items = [feed_item(video_id) for video_id in ids]
        items = self._filter_items_for_preferences(items, selected, state)
        return self._paginate_feed(
            items=items,
            title="Subscriptions",
            continuation_token=continuation_token,
            expected_kind=f"subscriptions:{selected}",
        )

    def feed_history(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._require_selected_account()
        ids = HISTORY_FEED.get(selected, [])
        return self._paginate_feed(
            items=[feed_item(video_id) for video_id in ids],
            title="History",
            continuation_token=continuation_token,
            expected_kind=f"history:{selected}",
        )

    def search(self, query: str, continuation_token: str | None) -> dict[str, Any]:
        if not query.strip():
            raise ProviderError("INVALID_QUERY", "q must not be empty", status_code=400)
        query_lower = query.strip().lower()
        matched = [video for video in VIDEOS if query_lower in video.title.lower() or query_lower in video.channel_name.lower()]
        state = self._state_store.read()
        account_scope = state.get("selectedAccountId") or "__anon__"
        items = [feed_item(video.video_id) for video in matched]
        items = self._filter_items_for_preferences(items, account_scope, state)
        return self._paginate_feed(
            items=items,
            title=f"Search: {query.strip()}",
            continuation_token=continuation_token,
            expected_kind=f"search:{query_lower}",
        )

    def search_suggestions(self, query: str) -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            raise ProviderError("INVALID_QUERY", "q must not be empty", status_code=400)
        query_lower = cleaned.lower()
        suggestions: list[str] = []
        seen: set[str] = set()
        for video in VIDEOS:
            candidates = [video.title, video.channel_name]
            for candidate in candidates:
                if query_lower not in candidate.lower():
                    continue
                normalized = candidate.strip()
                if not normalized:
                    continue
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                suggestions.append(normalized)
                if len(suggestions) >= 10:
                    break
            if len(suggestions) >= 10:
                break
        if not suggestions:
            suggestions.append(cleaned)
        return {"query": cleaned, "suggestions": suggestions}

    def video_metadata(self, video_id: str) -> dict[str, Any]:
        if video_id not in VIDEO_BY_ID:
            raise ProviderError("VIDEO_NOT_FOUND", f"Unknown video: {video_id}", status_code=404)
        row = metadata(video_id)
        has_comments = bool(COMMENTS_BY_VIDEO_ID.get(video_id))
        row["commentsKey"] = self._encode_comments_key(video_id, 0) if has_comments else None
        row["liveChatKey"] = None
        return row

    def video_playback(self, video_id: str) -> dict[str, Any]:
        if video_id not in VIDEO_BY_ID:
            raise ProviderError("VIDEO_NOT_FOUND", f"Unknown video: {video_id}", status_code=404)
        return {
            "videoId": video_id,
            "streamUrl": PLAYBACK_DEFAULT["streamUrl"],
            "mimeType": PLAYBACK_DEFAULT["mimeType"],
            "qualityLabel": "1080p",
            "isAdaptive": False,
            "availableStreams": [
                {
                    "id": "mock-1080p",
                    "streamUrl": PLAYBACK_DEFAULT["streamUrl"],
                    "mimeType": PLAYBACK_DEFAULT["mimeType"],
                    "qualityLabel": "1080p",
                    "isAdaptive": False,
                },
                {
                    "id": "mock-720p",
                    "streamUrl": PLAYBACK_DEFAULT["streamUrl"],
                    "mimeType": PLAYBACK_DEFAULT["mimeType"],
                    "qualityLabel": "720p",
                    "isAdaptive": False,
                },
            ],
            "subtitleTracks": [
                {
                    "id": "en",
                    "language": "en",
                    "label": "English",
                    "url": "https://example.com/mock/en.vtt",
                    "isAutoGenerated": False,
                }
            ],
            "expiresAtEpochSec": now_epoch() + 3600,
        }

    def video_related(self, video_id: str, continuation_token: str | None) -> dict[str, Any]:
        if video_id not in VIDEO_BY_ID:
            raise ProviderError("VIDEO_NOT_FOUND", f"Unknown video: {video_id}", status_code=404)

        current = VIDEO_BY_ID[video_id]
        same_channel = [video for video in VIDEOS if video.channel_id == current.channel_id and video.video_id != video_id]
        others = [video for video in VIDEOS if video.channel_id != current.channel_id and video.video_id != video_id]
        ordered = same_channel + others
        state = self._state_store.read()
        account_scope = state.get("selectedAccountId") or "__anon__"
        items = [feed_item(video.video_id) for video in ordered]
        items = self._filter_items_for_preferences(items, account_scope, state)

        return self._paginate_feed(
            items=items,
            title="Up Next",
            continuation_token=continuation_token,
            expected_kind=f"related:{video_id}",
        )

    def channel_videos(self, channel_id: str, continuation_token: str | None) -> dict[str, Any]:
        cleaned = channel_id.strip()
        if not cleaned:
            raise ProviderError("CHANNEL_NOT_FOUND", "Channel id is empty", status_code=404)

        matched = [video for video in VIDEOS if video.channel_id == cleaned]
        if not matched:
            raise ProviderError("CHANNEL_NOT_FOUND", f"Unknown channel: {cleaned}", status_code=404)

        return self._paginate_feed(
            items=[feed_item(video.video_id) for video in matched],
            title=f"Channel: {matched[0].channel_name}",
            continuation_token=continuation_token,
            expected_kind=f"channel:{cleaned}",
        )

    def comments(self, comments_key: str) -> dict[str, Any]:
        payload = self._decode_comment_cursor(comments_key, expected_type="comments")
        video_id = payload["videoId"]
        offset = int(payload["offset"])
        comments = COMMENTS_BY_VIDEO_ID.get(video_id, [])
        page = comments[offset : offset + COMMENTS_PAGE_SIZE]
        next_offset = offset + COMMENTS_PAGE_SIZE

        next_key = None
        if next_offset < len(comments):
            next_key = self._encode_comments_key(video_id, next_offset)

        items = []
        for item in page:
            nested_key = None
            if item.get("replies"):
                nested_key = self._encode_replies_key(video_id, item["id"], 0)
            items.append(
                {
                    "id": item["id"],
                    "authorName": item["authorName"],
                    "authorPhotoUrl": item["authorPhotoUrl"],
                    "publishedText": item["publishedText"],
                    "message": item["message"],
                    "likeCountText": item["likeCountText"],
                    "replyCountText": item["replyCountText"],
                    "nestedCommentsKey": nested_key,
                }
            )

        return {
            "nextCommentsKey": next_key,
            "items": items,
        }

    def comment_replies(self, nested_comments_key: str) -> dict[str, Any]:
        payload = self._decode_comment_cursor(nested_comments_key, expected_type="replies")
        video_id = payload["videoId"]
        comment_id = payload["commentId"]
        offset = int(payload["offset"])

        comments = COMMENTS_BY_VIDEO_ID.get(video_id, [])
        target = next((row for row in comments if row["id"] == comment_id), None)
        if target is None:
            raise ProviderError("COMMENTS_NOT_FOUND", "Reply thread not found", status_code=404)

        replies = target.get("replies", [])
        page = replies[offset : offset + REPLIES_PAGE_SIZE]
        next_offset = offset + REPLIES_PAGE_SIZE

        next_key = None
        if next_offset < len(replies):
            next_key = self._encode_replies_key(video_id, comment_id, next_offset)

        items = []
        for item in page:
            items.append(
                {
                    "id": item["id"],
                    "authorName": item["authorName"],
                    "authorPhotoUrl": item["authorPhotoUrl"],
                    "publishedText": item["publishedText"],
                    "message": item["message"],
                    "likeCountText": item["likeCountText"],
                    "replyCountText": item.get("replyCountText", "0"),
                    "nestedCommentsKey": None,
                }
            )

        return {
            "nextCommentsKey": next_key,
            "items": items,
        }

    def _paginate_feed(self, items: list[dict[str, Any]], title: str, continuation_token: str | None, expected_kind: str) -> dict[str, Any]:
        offset = 0
        if continuation_token:
            try:
                cursor = decode_cursor(continuation_token)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("INVALID_CONTINUATION", "Invalid continuation token") from exc
            if cursor.get("kind") != expected_kind:
                raise ProviderError("INVALID_CONTINUATION", "Continuation token does not match this feed")
            offset = int(cursor.get("offset", 0))

        page = items[offset : offset + FEED_PAGE_SIZE]
        next_offset = offset + FEED_PAGE_SIZE
        continuation = None
        if next_offset < len(items):
            continuation = encode_cursor({"kind": expected_kind, "offset": next_offset})

        return {
            "title": title,
            "continuationToken": continuation,
            "items": page,
        }

    def _decode_comment_cursor(self, key: str, expected_type: str) -> dict[str, Any]:
        try:
            payload = decode_cursor(key)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("INVALID_COMMENTS_KEY", "Invalid comments key") from exc
        if payload.get("type") != expected_type:
            raise ProviderError("INVALID_COMMENTS_KEY", "Comments key type mismatch")
        return payload

    def _encode_comments_key(self, video_id: str, offset: int) -> str:
        return encode_cursor({"type": "comments", "videoId": video_id, "offset": offset})

    def _encode_replies_key(self, video_id: str, comment_id: str, offset: int) -> str:
        return encode_cursor(
            {
                "type": "replies",
                "videoId": video_id,
                "commentId": comment_id,
                "offset": offset,
            }
        )

    def _seed_accounts(self) -> None:
        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)

        self._state_store.update(updater)

    def _ensure_accounts(self, state: dict[str, Any]) -> None:
        if not state.get("accounts"):
            state["accounts"] = copy.deepcopy(ACCOUNTS)

    def _next_account_id(self, state: dict[str, Any]) -> str:
        selected = state.get("selectedAccountId")
        if selected == ACCOUNTS[0]["id"]:
            return ACCOUNTS[1]["id"]
        return ACCOUNTS[0]["id"]

    def _require_selected_account(self) -> str:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        if not selected:
            raise ProviderError("AUTH_REQUIRED", "Sign-in required", status_code=401)
        return selected

    def _recommendation_scope_account_id(self) -> str:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        return str(selected) if selected else "__anon__"

    def _ensure_recommendation_preferences(self, state: dict[str, Any], account_scope: str) -> dict[str, Any]:
        root = state.setdefault("recommendationPreferences", {})
        if not isinstance(root, dict):
            root = {}
            state["recommendationPreferences"] = root
        prefs = root.get(account_scope)
        if not isinstance(prefs, dict):
            prefs = {
                "hiddenVideoIds": [],
                "blockedChannelIds": [],
                "mutedTerms": [],
                "updatedAtEpochSec": 0,
            }
            root[account_scope] = prefs
        prefs.setdefault("hiddenVideoIds", [])
        prefs.setdefault("blockedChannelIds", [])
        prefs.setdefault("mutedTerms", [])
        prefs.setdefault("updatedAtEpochSec", 0)
        return prefs

    def _get_recommendation_preferences(self, state: dict[str, Any], account_scope: str) -> dict[str, Any]:
        root = state.get("recommendationPreferences", {})
        if not isinstance(root, dict):
            return {
                "hiddenVideoIds": [],
                "blockedChannelIds": [],
                "mutedTerms": [],
            }
        prefs = root.get(account_scope, {})
        if not isinstance(prefs, dict):
            return {
                "hiddenVideoIds": [],
                "blockedChannelIds": [],
                "mutedTerms": [],
            }
        return prefs

    def _filter_items_for_preferences(
        self,
        items: list[dict[str, Any]],
        account_scope: str,
        state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        if state is None:
            state = self._state_store.read()
        prefs = self._get_recommendation_preferences(state, account_scope)
        hidden_video_ids = {str(row) for row in prefs.get("hiddenVideoIds", []) if row}
        blocked_channel_ids = {str(row) for row in prefs.get("blockedChannelIds", []) if row}
        muted_terms = {str(row).lower() for row in prefs.get("mutedTerms", []) if row}
        if not hidden_video_ids and not blocked_channel_ids and not muted_terms:
            return items
        filtered: list[dict[str, Any]] = []
        for item in items:
            video_id = str(item.get("videoId") or "")
            if video_id and video_id in hidden_video_ids:
                continue
            channel_id = str(item.get("channelId") or "")
            if channel_id and channel_id in blocked_channel_ids:
                continue
            if muted_terms:
                haystack = f"{item.get('title', '')} {item.get('channelName', '')}".lower()
                item_terms = set(self._tokenize_terms(haystack))
                if item_terms & muted_terms:
                    continue
            filtered.append(item)
        return filtered

    def _tokenize_terms(self, text: str) -> list[str]:
        stopwords = {
            "the",
            "and",
            "with",
            "from",
            "your",
            "this",
            "that",
            "you",
            "for",
            "are",
            "new",
            "feat",
            "official",
            "video",
            "music",
        }
        tokens: list[str] = []
        current: list[str] = []
        for char in text:
            if char.isalnum():
                current.append(char)
                continue
            if not current:
                continue
            token = "".join(current)
            current = []
            if len(token) >= 3 and token not in stopwords:
                tokens.append(token)
        if current:
            token = "".join(current)
            if len(token) >= 3 and token not in stopwords:
                tokens.append(token)
        return tokens
