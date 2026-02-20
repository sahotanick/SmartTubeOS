# SmartTube tvOS Rewrite: Execution Plan (Locked Decisions 1A/2A/3A/4A/5A)

## Architecture Snapshot
1. `tvOS App`:
   - Native Swift client for UI, navigation, and playback.
   - Talks to a local companion backend over HTTP on LAN/localhost.
2. `Companion Backend`:
   - JVM service that reuses existing SmartTube service logic for auth, account selection, feeds, metadata, and comments.
   - Exposes a small stable API for the tvOS client.

## V1 Functional Contract
1. Browse/search available.
2. Google sign-in via device code flow.
3. Session restore and sign-out.
4. Profile/account switching (among fetched accounts).
5. Subscriptions and history feeds.
6. Playback with metadata.
7. Description (plain long text).
8. Read-only comments (top-level + pagination + replies).

## Phase Plan
### Phase 0: API Contract and Parity Spec
1. Define backend API surface and payloads for:
   - auth start/poll/sign-out
   - accounts list/select
   - feeds (home/search/subscriptions/history)
   - metadata and comments
2. Freeze field-level parity requirements from Android behavior.
3. Create deterministic test fixtures for metadata/comments/account switching.

### Phase 1: Companion Backend Skeleton
1. Create a dedicated backend module in this repo.
2. Add health endpoint and version endpoint.
3. Implement auth endpoints (device code, poll, account list/select).
4. Implement read endpoints for subscriptions/history/metadata/comments.
5. Add integration tests for account switching state propagation.

### Phase 2: tvOS App Shell
1. Build app shell with tabs/sections:
   - Home/Search/Subscriptions/History/Settings
2. Implement sign-in flow and account/profile switch UI.
3. Wire subscriptions/history to backend endpoints.
4. Implement player screen with title/channel/publish info + description panel.
5. Implement comments panel (read-only, paginated).

### Phase 3: End-to-End Integration
1. Validate auth lifecycle:
   - signed out -> sign in -> restart app -> still signed in
   - switch account -> feed context updates
2. Validate feeds and metadata parity against Android app behavior.
3. Validate comments pagination and reply loading.

### Phase 4: V1 Hardening
1. Handle empty states and auth errors cleanly.
2. Add local logging and debug screen.
3. Add regression checklist and repeatable smoke tests.

## Immediate Milestone (Next Step)
1. Implement `Phase 0` artifacts in-repo:
   - `TVOS_COMPANION_API.md` with endpoint specs and payload shapes.
   - `TVOS_PARITY_CHECKLIST.md` for sign-in/profile/feeds/comments/description.
2. Start `Phase 1` backend skeleton immediately after contract freeze.

## Known Constraints
1. Build requires JDK 11 for current Android stack.
2. Flavor builds should be run separately to avoid cross-flavor google-services plugin coupling.
3. Native Android libraries are present in current app; tvOS v1 should avoid depending on Android-only runtime paths.
