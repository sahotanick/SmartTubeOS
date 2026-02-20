# SmartTube tvOS Companion API (V1 Draft)

## Conventions
1. Base path: `/v1`
2. All responses: JSON
3. Error shape:
```json
{ "error": { "code": "STRING_CODE", "message": "Human-readable message" } }
```

## Auth
### `POST /v1/auth/start`
Starts device-code sign-in flow.

Response:
```json
{
  "status": "PENDING",
  "signInCode": "ABCD-EFGH",
  "verificationUrl": "https://youtube.com/activate",
  "expiresInSec": 900,
  "pollIntervalSec": 5
}
```

### `GET /v1/auth/poll`
Poll current sign-in state.

Response (pending):
```json
{ "status": "PENDING" }
```

Response (success):
```json
{
  "status": "SIGNED_IN",
  "selectedAccountId": "acc_123"
}
```

### `POST /v1/auth/signout`
Signs out current user/session.

Response:
```json
{ "status": "SIGNED_OUT" }
```

## Accounts / Profiles
### `GET /v1/accounts`
Returns available accounts/profiles.

Response:
```json
{
  "selectedAccountId": "acc_123",
  "accounts": [
    { "id": "acc_123", "name": "John", "email": "john@example.com", "avatarUrl": "...", "selected": true },
    { "id": "acc_456", "name": "Brand", "email": null, "avatarUrl": "...", "selected": false }
  ]
}
```

### `POST /v1/accounts/select`
Selects active account (or `null` for signed-out style context).

Request:
```json
{ "accountId": "acc_456" }
```

Response:
```json
{ "selectedAccountId": "acc_456" }
```

## Feeds
### `GET /v1/feed/home`
Home feed (signed-in or anonymous depending on account state).

### `GET /v1/feed/subscriptions`
Signed-in subscriptions feed.

### `GET /v1/feed/history`
Signed-in watch history feed.

### Feed response shape (all feed endpoints)
```json
{
  "title": "Subscriptions",
  "continuationToken": "CONT_TOKEN_OR_NULL",
  "items": [
    {
      "videoId": "abc123",
      "title": "Video title",
      "channelName": "Channel",
      "channelId": "chan_1",
      "thumbnailUrl": "...",
      "publishedText": "2 hours ago",
      "durationSec": 621
    }
  ]
}
```

## Search
### `GET /v1/search?q=...&continuationToken=...`
Search videos/channels/playlists.

Response: same base shape as feed response.

## Video
### `GET /v1/video/{videoId}/metadata`
Returns metadata required by player/details screen.

Response:
```json
{
  "videoId": "abc123",
  "title": "Video title",
  "channelName": "Channel",
  "channelId": "chan_1",
  "publishedText": "2 hours ago",
  "viewCountText": "123K views",
  "description": "Long plain text",
  "commentsKey": "COMMENTS_KEY_OR_NULL",
  "liveChatKey": "LIVE_CHAT_KEY_OR_NULL"
}
```

### `GET /v1/video/{videoId}/playback`
Returns playable stream/url data for tvOS player.

Response (minimum):
```json
{
  "videoId": "abc123",
  "streamUrl": "https://...",
  "mimeType": "application/x-mpegURL",
  "expiresAtEpochSec": 0
}
```

## Comments (Read-Only V1)
### `GET /v1/comments?commentsKey=...`
Loads first page or continuation.

Response:
```json
{
  "nextCommentsKey": "NEXT_OR_NULL",
  "items": [
    {
      "id": "comment_1",
      "authorName": "User",
      "authorPhotoUrl": "...",
      "publishedText": "1 day ago",
      "message": "Comment text",
      "likeCountText": "31",
      "replyCountText": "4",
      "nestedCommentsKey": "NESTED_OR_NULL"
    }
  ]
}
```

### `GET /v1/comments/replies?nestedCommentsKey=...`
Loads replies for a specific comment thread.

Response: same shape as `GET /v1/comments`.

## Session/State
### `GET /v1/session`
Returns current session/account summary used during app boot.

Response:
```json
{
  "signedIn": true,
  "selectedAccountId": "acc_123"
}
```
