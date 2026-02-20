# SmartTube tvOS V1 Parity Checklist

## Account and Session
1. Sign-in flow shows device code and verification URL.
2. Polling transitions from pending to signed-in without app restart.
3. Session restores after app relaunch.
4. Sign-out clears session and authenticated feed access.

## Profile Switching
1. Account list loads with selected indicator.
2. Switching account updates selected account state.
3. Subscriptions/history immediately reflect selected account context.
4. Switching back restores previous account feed context.

## Subscriptions and History
1. Subscriptions feed loads for signed-in account.
2. History feed loads for signed-in account.
3. Pagination/continuation works for both feeds.
4. Signed-out state shows expected auth-required UX for auth-only feeds.

## Playback and Metadata
1. Video opens and plays from selected item.
2. Player shows title/channel/published info from metadata.
3. Metadata updates when moving to next video.

## Description
1. Description is available from metadata when source provides it.
2. Long text description view opens from player/menu.
3. Empty description shows a clear not-available state.

## Comments (Read-Only)
1. Comments open for videos with comments key.
2. Top-level comments render with author/date/message.
3. Load-more pagination works.
4. Reply threads open from nested comments key.
5. No-comments case shows clear not-available state.

## Reliability and UX
1. No app reset/crash during repeated account switching.
2. No app reset/crash during comments pagination/replies navigation.
3. Network/auth errors are surfaced with actionable messages.
