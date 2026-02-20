# SmartTube tvOS Companion Backend (V1)

## What it provides
- `/v1` API contract from `TVOS_COMPANION_API.md`.
- Provider modes:
  - `mock`: deterministic local data for development and testing.
  - `google`: OAuth device flow + YouTube Data API + `yt-dlp` playback extraction.

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
```

## Test suite
```bash
cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend
. .venv/bin/activate
pytest -q
```
