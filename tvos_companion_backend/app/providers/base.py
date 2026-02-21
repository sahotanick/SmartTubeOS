from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CompanionProvider(ABC):
    @abstractmethod
    def get_session(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def auth_start(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def auth_poll(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def auth_signout(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_accounts(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def select_account(self, account_id: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def remove_account(self, account_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def refresh_accounts(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def feed_home(self, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def feed_music(self, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def feed_subscriptions(self, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def feed_history(self, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def search_suggestions(self, query: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def video_metadata(self, video_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def video_playback(self, video_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def video_related(self, video_id: str, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def channel_videos(self, channel_id: str, continuation_token: str | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def comments(self, comments_key: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def comment_replies(self, nested_comments_key: str) -> dict[str, Any]:
        raise NotImplementedError
