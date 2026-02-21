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

### 2026-02-20T16:18 History Check Post-Playback
- Verified `/v1/feed/history` returns entries after playback call under google-mode local-history fallback.
- Sample result during real test: count `1`.

### 2026-02-20T17:09 tvOS Build Membership Fix
- Issue: `xcodebuild` failed with `Cannot find 'VideoRowView' in scope`.
- Cause: New `VideoRowView.swift` file was not added to the Xcode target sources.
- Action: Added file reference/build phase entries in `SmartTubeTVOS.xcodeproj/project.pbxproj`.
- Result: tvOS tests/build resumed successfully.

### 2026-02-20T17:12 Google Account Filtering/Profile Merge Hardening
- Issue: Old non-Google rows could leak into account list and channel-profile rows could be overwritten on re-auth.
- Actions:
  - Tightened visible account criteria to Google rows only (`provider/id-owner markers`).
  - Updated auth completion merge to preserve existing same-owner channel profiles while refreshing tokens/scope.
  - Added/updated tests in `tests/test_google_provider.py`.
- Validation:
  - `pytest -q tests/test_google_provider.py` -> `9 passed`.
  - `pytest -q` -> `23 passed`.

### 2026-02-20T17:14 Live Google Verification (Post-Hardening)
- Companion running in `google` mode.
- `/v1/accounts` now returns only Google account rows (stale mock rows hidden).
- `/v1/feed/home` returns items with populated thumbnail URLs.

### 2026-02-20T17:14 Live Limitation: Profile Discovery
- Observation: Authenticated `channels?mine=true` returned only one channel for current token (`Preet` in direct API check).
- Impact: Automatic multi-profile list under one sign-in is limited by what Google returns for that OAuth token.
- Decision: Keep multi-profile accumulation support across repeated sign-ins; document that additional profiles require Google presenting those channels during auth/token scope.

### 2026-02-20T17:14 Live Issue: Quota Exceeded
- Issue: `/v1/feed/subscriptions` returned `GOOGLE_API_ERROR` quota exceeded.
- Impact: Subscriptions feed unavailable until quota resets or is increased.
- Decision: Treat as environment/quota blocker for live verification (not compile/test blocker).

### 2026-02-20T18:32 tvOS Fullscreen Playback UX
- Request: Video launch should open fullscreen and exit with remote Back / simulator Esc.
- Actions:
  - Switched player presentation from `.sheet` to `.fullScreenCover`.
  - Auto-presents player once playback URL is resolved on video open.
  - Added `onExitCommand { dismiss() }` in player screen.
- Validation:
  - `xcodebuild -project SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV 4K (3rd generation),OS=26.2' test` -> `TEST SUCCEEDED` (`3/3` tests).

### 2026-02-20T18:35 Subscriptions Quota Saver
- Issue: Legacy subscriptions fallback used per-channel `search.list` calls (high quota cost).
- Action: Replaced fallback with lower-cost flow:
  1. `subscriptions.list` for channel IDs
  2. `channels.list` for uploads playlist IDs
  3. `playlistItems.list` (`maxResults=1`) per channel
- Validation:
  - Added test `test_google_subscriptions_fallback_uses_playlist_items_not_search`.
  - `pytest -q tests/test_google_provider.py` -> `10 passed`.
  - `pytest -q` -> `24 passed`.

### 2026-02-20T18:36 Live Runtime Status
- Companion backend running in google mode at `0.0.0.0:8000` (LAN `192.168.1.62`).
- Current blocker: Google project quota is exhausted; live `/v1/feed/home` and `/v1/feed/subscriptions` return quota-exceeded error until quota reset/increase.

### 2026-02-20T19:21 Quota Saver Controls
- Request: reduce quota burn during local testing.
- Actions:
  - Added in-memory response cache for YouTube GET requests (`path + params + account`) with TTL.
  - Added quota-cooldown guard so repeated requests after quota-exceeded errors are short-circuited.
  - Added stale-cache fallback when quota errors occur and cached payload exists.
  - Added env controls:
    - `YOUTUBE_QUOTA_SAVER` (default `1`)
    - `YOUTUBE_QUOTA_CACHE_TTL_SEC` (default `180`)
    - `YOUTUBE_QUOTA_ERROR_TTL_SEC` (default `60`)
  - Updated backend README with these settings.
- Validation:
  - Added provider tests for cache hit behavior and quota-cooldown short-circuit.
  - `pytest -q tests/test_google_provider.py` -> `12 passed`.
  - `pytest -q` -> `26 passed`.

### 2026-02-20T21:31 Profile Switcher Focus Reliability (tvOS)
- Issue: Top-right profile icon was intermittently unreachable via Siri Remote focus.
- Action: Moved launcher into in-content overlay button (`Profiles`) in `RootTabView`.
- Validation:
  - `xcodebuild ... build` -> `BUILD SUCCEEDED`.
  - `xcodebuild ... test` -> `TEST SUCCEEDED` (`4/4` tests).

### 2026-02-20T21:44 Adaptive Playback + QR Sign-In Helper
- Request: improve practical playback quality and make add-profile flow faster.
- Actions:
  - Backend (`google_provider`) playback extraction now prefers higher-resolution AV formats and flags adaptive streams.
  - Playback payload extended with optional `qualityLabel` and `isAdaptive`.
  - Auth start payload extended with `verificationUrlComplete` (URL prefilled with device code).
  - tvOS UI now renders local QR code for device sign-in flow in both Settings and profile switcher sheet.
  - Video detail now displays playback mode hint (`adaptive` vs `fixed stream`).
- Validation:
  - Backend: `cd tvos_companion_backend && . .venv/bin/activate && pytest -q` -> `30 passed`.
  - tvOS: `xcodebuild -project tvos_client/SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'id=011802A3-06D8-4CC1-B8DE-D279D71406D7' test` -> `TEST SUCCEEDED` (`4/4` tests).

### 2026-02-20T21:45 Build Issue During QR UI Wiring
- Issue: `textSelection(.enabled)` is unavailable on tvOS and caused compile failure.
- Action: Removed text-selection modifier from sign-in guide URL label.
- Result: Build/test returned to green.

### 2026-02-20T22:10 Profile Refresh API + Single-Profile Guidance
- Request: add explicit profile re-discovery and explain when only one profile is visible.
- Actions:
  - Added backend endpoint `POST /v1/accounts/refresh` with Google-provider owner-profile re-discovery and merge.
  - Added tvOS client action `Refresh Profiles from Google` in both Settings and profile switcher.
  - Added in-app hint message when signed in but only one profile is currently exposed by Google for that token.
- Validation:
  - Backend tests: `pytest -q` -> `32 passed`.
  - tvOS tests: `xcodebuild ... test` -> `TEST SUCCEEDED` (`5/5` tests).

### 2026-02-20T23:31 Profile Access Parity Pass (Top-Bar Account Entry)
- Request: make account switching feel closer to native YouTube and remove profile-icon reachability friction.
- Issues observed:
  - Floating overlay profile launcher could be hard to reach with Siri Remote focus in some navigation states.
  - Account entry point felt disconnected from native top-bar account affordance.
- Actions:
  - Replaced overlay launcher with a true per-screen toolbar account control in `RootTabView`.
  - Upgraded the launcher UI to a compact top-bar badge with current time + avatar to mirror native TV app patterns.
  - Switched profile center presentation from sheet to fullscreen profile hub.
  - Added header/current-profile context and kept in-place actions for refresh/add/select/remove/sign-out mode.
  - Added `onExitCommand` for fast remote Back/Esc dismissal from profile hub.
- Validation:
  - `xcodebuild -project tvos_client/SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV' test` -> `TEST SUCCEEDED` (`5/5` tests).

### 2026-02-21T00:39 V2/V3 Feature Sprint (Up Next, Continue Watching, Suggestions, Channel Browse)
- Request: continue immediately with broader parity improvements while capacity remains.
- Actions (backend):
  - Added new endpoints:
    - `GET /v1/search/suggestions`
    - `GET /v1/video/{id}/related`
    - `GET /v1/channel/{id}/videos`
  - Extended playback payload with optional:
    - `availableStreams[]` for quality options
    - `subtitleTracks[]` for caption metadata
  - Implemented mock and Google provider support for all above.
  - Added backend tests for new endpoints/provider mappings.
- Actions (tvOS client):
  - Added API client methods for suggestions, related, and channel videos.
  - Added search suggestions + persistent recent searches.
  - Added continue-watching rail on Home with persisted per-account watch progress.
  - Expanded video detail with:
    - Up Next list
    - Channel navigation surface
    - Autoplay toggle
  - Reworked fullscreen player to include:
    - Up-next progression
    - Playback options panel (speed + quality options + caption metadata visibility)
    - periodic watch-progress persistence.
  - Added retry affordances in feed/search/comments/video detail error states.
- Validation:
  - Backend: `cd tvos_companion_backend && . .venv/bin/activate && pytest -q` -> `35 passed`.
  - tvOS: `xcodebuild -project tvos_client/SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV' test` -> `TEST SUCCEEDED` (`9/9` tests).
- Noted limitations:
  - Caption track metadata is surfaced, but full subtitle rendering still depends on stream/media characteristics exposed by AVPlayer for each source.
  - Account/profile visibility remains constrained by what Google APIs expose for the authenticated token.

### 2026-02-21T00:42 Stability Follow-up (Persistence + Error Messaging)
- Actions:
  - Added tvOS `AppState` tests for recent-search persistence/deduplication and continue-watching progress persistence.
  - Added user-facing backend error mapping in `APIClient` for auth-required/auth-expired/quota/api-key-missing cases.
- Validation:
  - Backend: `pytest -q` -> `35 passed`.
  - tvOS: `xcodebuild -project tvos_client/SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV' test` -> `TEST SUCCEEDED` (`9/9` tests).

### 2026-02-21T00:55 Music Tab Addition
- Request: add a YouTube-like Music tab that surfaces music the user is likely interested in.
- Actions:
  - Added backend endpoint `GET /v1/feed/music`.
  - Google provider logic:
    - signed-in personalized pass from `activities?home=true` filtered to music-like videos.
    - automatic fallback to popular music (`videoCategoryId=10`) when personalized pass is empty.
  - Mock provider logic:
    - deterministic music feed for signed-in and signed-out test states.
  - tvOS client:
    - added `Music` tab in top-level navigation.
    - wired API client method `fetchMusic`.
  - Added backend and tvOS tests for music feed endpoint/client decode.

### 2026-02-21T01:26 Music Personalization Refinement (Punjabi/Profile Bias)
- Issue observed: Music tab content was valid but too generic for selected profile taste.
- Root cause:
  - Personalized pass depended on `activities?home=true` plus narrow music heuristics.
  - Non-category-10 regional tracks (including Punjabi uploads) could be dropped.
- Actions:
  - Added low-quota personalization seed from each selected profile's own Liked Videos playlist.
  - Blended liked-seed videos with existing personalized activity candidates and deduplicated by `videoId`.
  - Expanded music heuristics to better recognize official music uploads beyond strict category checks.
  - Added Punjabi/Gurmukhi preference signal detection from liked-seed metadata.
  - Added optional regional popular backfill (`IN`) only when Punjabi-like preference signals exist and first-page results are sparse.
- Validation:
  - Backend tests updated for liked-seed + fallback behavior and re-run to green.
