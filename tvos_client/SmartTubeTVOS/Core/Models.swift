import Foundation

struct APIErrorResponse: Decodable {
    let error: APIErrorBody
}

struct APIErrorBody: Decodable {
    let code: String
    let message: String
}

struct SessionSummary: Codable {
    let signedIn: Bool
    let selectedAccountId: String?
}

struct AuthStartResponse: Codable {
    let status: String
    let signInCode: String
    let verificationUrl: String
    let expiresInSec: Int
    let pollIntervalSec: Int
}

struct AuthPollResponse: Codable {
    let status: String
    let selectedAccountId: String?
}

struct StatusResponse: Codable {
    let status: String
}

struct AccountListResponse: Codable {
    let selectedAccountId: String?
    let accounts: [AccountSummary]
}

struct AccountSummary: Codable, Identifiable {
    let id: String
    let name: String
    let email: String?
    let avatarUrl: String?
    let selected: Bool
}

struct SelectAccountRequest: Codable {
    let accountId: String?
}

struct SelectAccountResponse: Codable {
    let selectedAccountId: String?
}

struct FeedResponse: Codable {
    let title: String
    let continuationToken: String?
    let items: [VideoFeedItem]
}

struct VideoFeedItem: Codable, Identifiable {
    let videoId: String
    let title: String
    let channelName: String
    let channelId: String
    let thumbnailUrl: String
    let publishedText: String
    let durationSec: Int

    var id: String { videoId }
}

struct VideoMetadataResponse: Codable {
    let videoId: String
    let title: String
    let channelName: String
    let channelId: String
    let publishedText: String
    let viewCountText: String
    let description: String
    let commentsKey: String?
    let liveChatKey: String?
}

struct PlaybackResponse: Codable {
    let videoId: String
    let streamUrl: String
    let mimeType: String
    let expiresAtEpochSec: Int
}

struct CommentsResponse: Codable {
    let nextCommentsKey: String?
    let items: [CommentItem]
}

struct CommentItem: Codable, Identifiable {
    let id: String
    let authorName: String
    let authorPhotoUrl: String
    let publishedText: String
    let message: String
    let likeCountText: String
    let replyCountText: String
    let nestedCommentsKey: String?
}
