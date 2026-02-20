# SmartTube tvOS Rewrite: V1 Scope

## Goal
Build a local-use tvOS app with core playback parity, including Google account sign-in, profile switching, subscriptions/history, video descriptions, and comments.

## V1 Must-Have Features
1. Browse and search videos.
2. Start and control playback (play/pause/seek/next/previous).
3. Sign in with Google account (device code flow).
4. Persist signed-in session and support sign-out.
5. Switch between available Google profiles/accounts.
6. Show authenticated feeds:
   - subscriptions
   - watch history
7. Show video metadata in player UI (title, channel, publish info).
8. Show full video description from metadata.
9. Open comments from playback/menu and read:
   - initial comments page
   - load more comments
   - nested replies

## V1 Non-Goals (Can Be V1.1+)
1. Comment like/dislike actions.
2. Full Android TV integrations (channels provider, bridge installer).
3. Android-specific background/service behaviors.
4. Full Google Drive backup integration.

## Existing Code Paths That Define Parity
### Description path
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/models/playback/controllers/PlayerUIController.java`
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/models/data/Video.java`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/next/v2/impl/MediaItemMetadataImpl.kt`

### Comments path
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/models/playback/controllers/CommentsController.java`
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/presenters/dialogs/menu/VideoMenuPresenter.java`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/YouTubeCommentsService.kt`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/comments/CommentsServiceInt.kt`

### Sign-in and profile switching path
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/presenters/YTSignInPresenter.java`
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/presenters/SignInPresenter.java`
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/presenters/dialogs/AccountSelectionPresenter.java`
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/misc/MediaServiceManager.java`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/YouTubeAccountManager.java`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/auth/V2/AuthService.java`

### Subscriptions and history path
- `common/src/main/java/com/liskovsoft/smartyoutubetv2/common/app/presenters/BrowsePresenter.java`
- `MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/YouTubeContentService.java`

## Build Findings That Affect Rewrite Decisions
1. Android app is currently buildable for `stbeta`, `ststable`, and `stfdroid`.
2. Flavor differences are mostly packaging/configuration, not feature logic.
3. Core feature logic is concentrated in shared Java/Kotlin modules (`common` and `MediaServiceCore`), which is useful for extracting behavior specs.

## Decisions To Lock Before Coding
1. Architecture:
   - Option A (recommended for speed): tvOS client + local companion backend reusing existing Java/Kotlin service logic.
   - Option B: full native Swift rewrite (UI + service layer).
2. Auth stack in V1:
   - Option A (recommended for speed): reuse existing OAuth/account backend behavior via companion backend.
   - Option B: native tvOS auth implementation end-to-end in Swift.
3. Profile switching in V1:
   - Option A (recommended V1): switch among fetched YouTube accounts and persist selected account.
   - Option B: include profile add/remove management UI in v1.
4. Comments in V1:
   - Read-only (recommended V1) or interactive (like/dislike/reply actions in V1).
5. Description behavior:
   - Plain long-text rendering in V1 (recommended), with link parsing as V1.1.

## Locked Decisions (2026-02-20)
1. `1A` Architecture: tvOS client + local companion backend.
2. `2A` Auth stack: reuse existing OAuth/account backend behavior via companion backend.
3. `3A` Profile switching: switch among fetched accounts and persist selected account.
4. `4A` Comments: read-only in v1.
5. `5A` Description: plain long-text in v1 (no link parsing in v1).

## Acceptance Criteria For V1
1. User can complete sign-in and session is restored after app restart.
2. User can switch profile/account and the feed context updates to the selected account.
3. Subscriptions and watch history load for signed-in accounts.
4. Opening a video always attempts metadata load and shows description when available.
5. User can open comments for videos where comments key exists.
6. User can paginate and open reply threads without app reset.
7. For videos with no description/comments, app shows a clear "not available" state.
