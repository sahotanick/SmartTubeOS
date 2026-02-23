from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings
from app.provider_factory import create_provider
from app.providers.base import ProviderError
from app.state_store import StateStore


class SelectAccountRequest(BaseModel):
    accountId: str | None


class RemoveAccountRequest(BaseModel):
    accountId: str


class CompanionApp:
    def __init__(self, settings: Settings | None = None, state_store: StateStore | None = None):
        self.settings = settings or Settings.from_env()
        self.state_store = state_store or StateStore(self.settings.state_file)
        self.provider = create_provider(self.settings, self.state_store)



def create_app(settings: Settings | None = None, state_store: StateStore | None = None) -> FastAPI:
    runtime = CompanionApp(settings=settings, state_store=state_store)
    if runtime.settings.debug_formats:
        import logging
        logging.getLogger("smarttube").setLevel(logging.INFO)
    app = FastAPI(title="SmartTube tvOS Companion API", version="0.1.0")

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": app.version, "provider": runtime.settings.provider_mode}

    @app.get("/v1/session")
    def session() -> dict[str, Any]:
        return runtime.provider.get_session()

    @app.post("/v1/auth/start")
    def auth_start() -> dict[str, Any]:
        return runtime.provider.auth_start()

    @app.get("/v1/auth/poll")
    def auth_poll() -> dict[str, Any]:
        return runtime.provider.auth_poll()

    @app.post("/v1/auth/signout")
    def auth_signout() -> dict[str, Any]:
        return runtime.provider.auth_signout()

    @app.get("/v1/accounts")
    def accounts() -> dict[str, Any]:
        return runtime.provider.list_accounts()

    @app.post("/v1/accounts/select")
    def accounts_select(request: SelectAccountRequest) -> dict[str, Any]:
        return runtime.provider.select_account(request.accountId)

    @app.post("/v1/accounts/remove")
    def accounts_remove(request: RemoveAccountRequest) -> dict[str, Any]:
        return runtime.provider.remove_account(request.accountId)

    @app.post("/v1/accounts/refresh")
    def accounts_refresh() -> dict[str, Any]:
        return runtime.provider.refresh_accounts()

    @app.get("/v1/feed/home")
    def feed_home(continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.feed_home(continuationToken)

    @app.get("/v1/feed/music")
    def feed_music(continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.feed_music(continuationToken)

    @app.get("/v1/feed/subscriptions")
    def feed_subscriptions(continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.feed_subscriptions(continuationToken)

    @app.get("/v1/feed/history")
    def feed_history(continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.feed_history(continuationToken)

    @app.get("/v1/search")
    def search(q: str = Query(..., min_length=1), continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.search(q, continuationToken)

    @app.get("/v1/search/suggestions")
    def search_suggestions(q: str = Query(..., min_length=1)) -> dict[str, Any]:
        return runtime.provider.search_suggestions(q)

    @app.get("/v1/video/{video_id}/metadata")
    def video_metadata(video_id: str) -> dict[str, Any]:
        return runtime.provider.video_metadata(video_id)

    @app.get("/v1/video/{video_id}/playback")
    def video_playback(video_id: str) -> dict[str, Any]:
        return runtime.provider.video_playback(video_id)

    @app.get("/v1/video/{video_id}/related")
    def video_related(video_id: str, continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.video_related(video_id, continuationToken)

    @app.get("/v1/channel/{channel_id}/videos")
    def channel_videos(channel_id: str, continuationToken: str | None = None) -> dict[str, Any]:
        return runtime.provider.channel_videos(channel_id, continuationToken)

    @app.get("/v1/comments")
    def comments(commentsKey: str = Query(..., min_length=1)) -> dict[str, Any]:
        return runtime.provider.comments(commentsKey)

    @app.get("/v1/comments/replies")
    def comment_replies(nestedCommentsKey: str = Query(..., min_length=1)) -> dict[str, Any]:
        return runtime.provider.comment_replies(nestedCommentsKey)

    return app


app = create_app()
