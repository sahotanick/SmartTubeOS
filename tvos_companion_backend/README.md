# SmartTube tvOS Companion Backend (V1)

## What it provides
- `/v1` API contract from `TVOS_COMPANION_API.md`.
- Provider modes:
  - `mock`: deterministic local data for development and testing.
  - `google`: OAuth device flow + YouTube Data API + `yt-dlp` playback extraction.
- Profile utilities:
  - `POST /v1/accounts/refresh` to re-discover Google channel profiles and merge with saved local profiles for the signed-in owner.
- Discovery/player utilities:
  - `GET /v1/video/{id}/related` for up-next rails.
  - `GET /v1/channel/{id}/videos` for channel browsing.
  - `GET /v1/search/suggestions` for query suggestions.
  - `GET /v1/video/{id}/playback` now includes optional quality stream options and subtitle track metadata.

## Quick start
```bash
cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
COMPANION_PROVIDER=mock uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Google mode env vars
```bash
export COMPANION_PROVIDER=google
export YOUTUBE_CLIENT_ID=...
export YOUTUBE_CLIENT_SECRET=...
# Optional for anonymous endpoints when signed out
export YOUTUBE_API_KEY=...
# Quota saver for local testing (defaults shown)
export YOUTUBE_QUOTA_SAVER=1
export YOUTUBE_QUOTA_CACHE_TTL_SEC=180
export YOUTUBE_QUOTA_ERROR_TTL_SEC=60
```

## Test suite
```bash
cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend
. .venv/bin/activate
pytest -q
```
