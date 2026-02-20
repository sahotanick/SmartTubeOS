# SmartTube tvOS V1 Implementation Log

Date: 2026-02-20

## Session Objective
Move from planning artifacts to a testable V1 implementation for locked decisions `1A/2A/3A/4A/5A`.

## Decisions Log

### 2026-02-20T15:35 Local Backend Runtime
- Decision: Implement companion backend in Python/FastAPI for V1 test phase.
- Reason: Existing Android service modules are tightly coupled to Android runtime; Python backend enables immediate, testable endpoint parity while preserving future option to replace provider internals with reused JVM logic.
- Risk: Behavioral drift from SmartTube service implementation.
- Mitigation: Keep API contract strict and map parity checklist into tests.

## Issues Log

### 2026-02-20T15:35 Android Reuse Constraint
- Issue: Directly running `MediaServiceCore` service logic in a plain JVM backend is blocked by AndroidX dependencies.
- Impact: Cannot quickly stand up JVM companion with direct source reuse in V1 timeframe.
- Action: Proceed with provider abstraction (`mock` + `google`) and preserve endpoint contract.

## Test Log

- Pending.

### 2026-02-20T15:43 Python Test Discovery
- Issue: Initial pytest run failed with `ModuleNotFoundError: app`.
- Impact: Tests could not import backend package.
- Action: Added `tvos_companion_backend/pytest.ini` with `pythonpath = .`.
- Result: Import issue resolved.

### 2026-02-20T15:44 Backend Auth/Accounts Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q tests/test_auth_accounts.py`
- Result: `4 passed`.
- Notes: Runtime emitted FastAPI/Starlette deprecation warnings under Python 3.14 for `asyncio.iscoroutinefunction`; no functional failures.

### 2026-02-20T15:47 Backend Feeds/Search Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q tests/test_feeds_search.py`
- Result: `5 passed`.
- Coverage focus: auth-required feeds, pagination continuation, search continuation, account-switch feed-context changes.

### 2026-02-20T15:49 Backend Video/Comments Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q tests/test_video_comments.py`
- Result: `5 passed`.
- Coverage focus: metadata/description/comments-key behavior, no-comments state, playback payload, comments pagination, replies loading.

### 2026-02-20T15:50 Full Backend Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q`
- Result: `14 passed`.
- Issue: Large deprecation warning volume on Python 3.14 from FastAPI/Starlette internals.
- Decision: Keep Python 3.14 for now (non-blocking functional behavior); revisit runtime pin to Python 3.12 if warning noise affects CI readability.

### 2026-02-20T16:01 Google Provider Design
- Decision: Implement Google sign-in with OAuth device code flow (`oauth2.googleapis.com`) and persist multiple Google accounts for profile switching.
- Reason: Meets V1 sign-in/profile switching requirements with local persistence and no App Store dependency.

### 2026-02-20T16:01 History Source Strategy
- Issue: YouTube Data API does not reliably expose full cloud watch-history for all accounts.
- Decision: Try related history playlist first; fallback to companion-local playback history per selected account.
- Impact: History endpoint remains functional in V1 but may not mirror full YouTube account history in all cases.

### 2026-02-20T16:01 Subscriptions Feed Strategy
- Decision: Use authenticated `activities?home=true` as primary source, with fallback to latest uploads from subscribed channels.
- Reason: `subscriptions.list` alone returns channels, not feed video items required by V1 UI.

### 2026-02-20T16:01 Playback Extraction Strategy
- Decision: Use `yt-dlp` to resolve direct playback URLs for local testing usage.
- Reason: YouTube Data API does not provide direct stream URLs.
- Risk: Upstream format/signature changes can intermittently break playback extraction.

### 2026-02-20T16:02 Google Provider Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q tests/test_google_provider.py`
- Result: `5 passed` (network mocked unit coverage for auth persistence, account selection, local history fallback, playback history append).

### 2026-02-20T16:02 Full Backend Test Run (Post-Google)
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_companion_backend && . .venv/bin/activate && pytest -q`
- Result: `19 passed`.

### 2026-02-20T15:45 tvOS Build Environment
- Issue: `xcodebuild test` failed because tvOS platform component was missing from Xcode 26.2.
- Action: Installed tvOS simulator runtime with `xcodebuild -downloadPlatform tvOS` (tvOS 26.2, 3.62 GB).
- Result: tvOS simulator destinations became available for build/test.

### 2026-02-20T15:53 tvOS Compile Fixes
- Issue: `APIClient.selectAccount` shadowed method name (`request`), causing compile failure.
- Action: Renamed local payload variable.
- Issue: `.textFieldStyle(.roundedBorder)` unavailable on tvOS.
- Action: Removed unavailable style usage in `SearchScreen`.

### 2026-02-20T15:54 tvOS Unit Test Run
- Command: `cd /Users/harnake/Documents/SmartTubeOS/tvos_client && xcodebuild -project SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV 4K (3rd generation),OS=26.2' test`
- Result: `TEST SUCCEEDED`.
- Tests passed: `APIClientTests` (2), `AppStateTests` (1).

### 2026-02-20T15:55 End-to-End Backend Sanity (Mock Provider)
- Action: Started local companion server on `127.0.0.1:8000`.
- Checks: `/healthz`, `/v1/session`, `/v1/feed/home`, auth start/poll, accounts, subscriptions, metadata, comments.
- Result: Core V1 endpoint flow succeeded including sign-in -> selected account -> subscriptions -> metadata description -> comments page.

### 2026-02-20T15:56 Final Regression Runs
- Backend: `pytest -q` -> `19 passed`.
- tvOS client: `xcodebuild ... test` -> `TEST SUCCEEDED` (`3/3` tests).
- Note: tvOS app runtime logs connection-refused when companion backend is not running during simulator test launch; unit tests still pass because API traffic is mocked in test target.

### 2026-02-20T15:57 Repo Hygiene
- Added `/Users/harnake/Documents/SmartTubeOS/tvos_companion_backend/.gitignore` for `.venv`, caches, and runtime state file.
- Removed generated caches/state artifacts from backend folder.
- Re-ran backend tests after cleanup: `19 passed`.

### 2026-02-20T15:59 Google History Pagination Fix
- Issue: `google_history_local` continuation tokens could fail in `feed_history` due strict initial decode path.
- Action: Updated continuation routing to accept both remote (`google_history`) and local (`google_history_local`) token types.
- Validation:
  - `pytest -q tests/test_google_provider.py` -> `6 passed`.
  - `pytest -q` -> `20 passed`.

### 2026-02-20T16:10 Real Account Test (Google Provider) - In Progress
- Environment wired via local `.env.local` (git-ignored) with Google OAuth/API credentials.
- Companion started in `google` mode.
- Verification:
  - `/version` -> provider `google`
  - `POST /v1/auth/start` -> `PENDING` with device code emitted
  - `GET /v1/auth/poll` -> `PENDING` (awaiting browser authorization)
- Next action required: User must complete device-code verification in browser.

### 2026-02-20T16:12 Real Account Test Result: Authenticated Read Endpoints
- Sign-in completed successfully with real Google account (`status=SIGNED_IN`).
- Verified endpoints in `google` mode:
  - `/v1/session` signed-in state and selected account id
  - `/v1/accounts` includes Google profile
  - `/v1/feed/home` returns populated feed
  - `/v1/feed/subscriptions` returns populated feed
  - `/v1/search?q=...` returns populated feed
  - `/v1/video/{id}/metadata` returns description/comments key

### 2026-02-20T16:12 Issue: Comments Scope Error Under OAuth
- Issue: `/v1/comments` initially returned `GOOGLE_API_ERROR: Request had insufficient authentication scopes` despite read-only scopes present.
- Decision/Fix: Added controlled fallback for comments/replies to API-key-backed public read when OAuth token gets scope-policy rejection.
- Result: Comments and replies load successfully for real account test video.

### 2026-02-20T16:15 Issue: Playback Extraction Failure on Real Video
- Issue: `/v1/video/{id}/playback` failed on real subscription video with `Requested format is not available`.
- Actions:
  - Upgraded `yt-dlp` from `2025.1.26` to `2026.2.4`.
  - Relaxed stream extraction strategy with progressive format fallback and requested-format URL handling.
- Result: Playback endpoint now returns valid stream URL and `video/mp4` mime type for tested video.

### 2026-02-20T16:16 Real Account Test Result: Full Core V1 Flow
- Core authenticated flow validated end-to-end in `google` mode:
  1. Device auth start/poll -> signed in
  2. Account list/profile selected
  3. Subscriptions feed loaded
  4. Metadata + long description loaded
  5. Comments page loaded
  6. Replies page loaded
  7. Playback URL resolved
