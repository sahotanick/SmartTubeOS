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

        def updater(state: dict[str, Any]) -> None:
            self._ensure_accounts(state)
            state["pendingAuth"] = {
                "signInCode": sign_in_code,
                "verificationUrl": "https://youtube.com/activate",
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
            "verificationUrl": "https://youtube.com/activate",
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

    def feed_home(self, continuation_token: str | None) -> dict[str, Any]:
        state = self._state_store.read()
        selected = state.get("selectedAccountId")
        if selected and selected in HOME_FEED_SIGNED_IN:
            ids = HOME_FEED_SIGNED_IN[selected]
            title = "Home"
        else:
            ids = HOME_FEED_ANON
            title = "Home"
        return self._paginate_feed(
            items=[feed_item(video_id) for video_id in ids],
            title=title,
            continuation_token=continuation_token,
            expected_kind="home",
        )

    def feed_subscriptions(self, continuation_token: str | None) -> dict[str, Any]:
        selected = self._require_selected_account()
        ids = SUBSCRIPTIONS_FEED.get(selected, [])
        return self._paginate_feed(
            items=[feed_item(video_id) for video_id in ids],
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
        items = [feed_item(video.video_id) for video in matched]
        return self._paginate_feed(
            items=items,
            title=f"Search: {query.strip()}",
            continuation_token=continuation_token,
            expected_kind=f"search:{query_lower}",
        )

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
            "expiresAtEpochSec": now_epoch() + 3600,
        }

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
