import Foundation

enum CompanionAPIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case backend(code: String, message: String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid companion URL"
        case .invalidResponse:
            return "Unexpected companion response"
        case let .backend(code, message):
            if code == "AUTH_REQUIRED" {
                return "Sign in required. Open Profiles or Settings to add/select an account."
            }
            if code == "AUTH_EXPIRED" {
                return "Your Google session expired. Sign in again from Profiles."
            }
            if code == "GOOGLE_API_ERROR", message.lowercased().contains("quota") {
                return "YouTube API quota reached for today. Try again after reset, or switch to mock mode."
            }
            if code == "GOOGLE_API_KEY_REQUIRED" {
                return "API key missing for signed-out mode. Add YOUTUBE_API_KEY in backend config."
            }
            return "\(code): \(message)"
        case let .transport(message):
            return message
        }
    }
}

final class APIClient {
    private(set) var baseURL: URL
    private let fallbackBaseURLs: [URL]
    private let session: URLSession

    init(baseURL: URL, fallbackBaseURLs: [URL] = [], session: URLSession = .shared) {
        self.baseURL = baseURL
        self.fallbackBaseURLs = fallbackBaseURLs.filter { $0.absoluteString != baseURL.absoluteString }
        self.session = session
    }

    func fetchSession() async throws -> SessionSummary {
        try await request("/v1/session", method: "GET")
    }

    func authStart() async throws -> AuthStartResponse {
        try await request("/v1/auth/start", method: "POST")
    }

    func authPoll() async throws -> AuthPollResponse {
        try await request("/v1/auth/poll", method: "GET")
    }

    func authSignout() async throws -> StatusResponse {
        try await request("/v1/auth/signout", method: "POST")
    }

    func fetchAccounts() async throws -> AccountListResponse {
        try await request("/v1/accounts", method: "GET")
    }

    func selectAccount(accountId: String?) async throws -> SelectAccountResponse {
        let payload = SelectAccountRequest(accountId: accountId)
        return try await request("/v1/accounts/select", method: "POST", body: payload)
    }

    func removeAccount(accountId: String) async throws -> SelectAccountResponse {
        let payload = RemoveAccountRequest(accountId: accountId)
        return try await request("/v1/accounts/remove", method: "POST", body: payload)
    }

    func refreshAccounts() async throws -> RefreshAccountsResponse {
        try await request("/v1/accounts/refresh", method: "POST")
    }

    func sendRecommendationFeedback(videoId: String, channelId: String?, action: String) async throws -> RecommendationFeedbackResponse {
        let payload = RecommendationFeedbackRequest(videoId: videoId, channelId: channelId, action: action)
        return try await request("/v1/recommendations/feedback", method: "POST", body: payload)
    }

    func fetchHome(continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/feed/home", method: "GET", query: ["continuationToken": continuationToken])
    }

    func fetchMusic(continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/feed/music", method: "GET", query: ["continuationToken": continuationToken])
    }

    func fetchSubscriptions(continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/feed/subscriptions", method: "GET", query: ["continuationToken": continuationToken])
    }

    func fetchHistory(continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/feed/history", method: "GET", query: ["continuationToken": continuationToken])
    }

    func search(query: String, continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/search", method: "GET", query: ["q": query, "continuationToken": continuationToken])
    }

    func searchSuggestions(query: String) async throws -> SearchSuggestionsResponse {
        try await request("/v1/search/suggestions", method: "GET", query: ["q": query])
    }

    func fetchMetadata(videoId: String) async throws -> VideoMetadataResponse {
        try await request("/v1/video/\(videoId)/metadata", method: "GET")
    }

    func fetchPlayback(videoId: String) async throws -> PlaybackResponse {
        try await request("/v1/video/\(videoId)/playback", method: "GET")
    }

    func fetchRelated(videoId: String, continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/video/\(videoId)/related", method: "GET", query: ["continuationToken": continuationToken])
    }

    func fetchChannelVideos(channelId: String, continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/channel/\(channelId)/videos", method: "GET", query: ["continuationToken": continuationToken])
    }

    func fetchComments(commentsKey: String) async throws -> CommentsResponse {
        try await request("/v1/comments", method: "GET", query: ["commentsKey": commentsKey])
    }

    func fetchReplies(nestedCommentsKey: String) async throws -> CommentsResponse {
        try await request("/v1/comments/replies", method: "GET", query: ["nestedCommentsKey": nestedCommentsKey])
    }

    private func request<T: Decodable>(_ path: String, method: String, query: [String: String?] = [:]) async throws -> T {
        try await request(path, method: method, query: query, body: Optional<Int>.none)
    }

    private func request<T: Decodable, B: Encodable>(
        _ path: String,
        method: String,
        query: [String: String?] = [:],
        body: B?
    ) async throws -> T {
        let candidates = [baseURL] + fallbackBaseURLs
        var lastError: CompanionAPIError?

        for candidate in candidates {
            do {
                let decoded: T = try await requestOnce(
                    baseURL: candidate,
                    path: path,
                    method: method,
                    query: query,
                    body: body
                )
                if candidate.absoluteString != baseURL.absoluteString {
                    baseURL = candidate
                }
                return decoded
            } catch let error as CompanionAPIError {
                lastError = error
                if !shouldRetry(after: error) || candidate.absoluteString == candidates.last?.absoluteString {
                    throw error
                }
            }
        }

        throw lastError ?? CompanionAPIError.transport("Could not connect to the server.")
    }

    private func requestOnce<T: Decodable, B: Encodable>(
        baseURL: URL,
        path: String,
        method: String,
        query: [String: String?],
        body: B?
    ) async throws -> T {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw CompanionAPIError.invalidURL
        }

        let cleanedPath = path.hasPrefix("/") ? path : "/\(path)"
        components.path = cleanedPath
        let queryItems = query.compactMap { key, value -> URLQueryItem? in
            guard let value else { return nil }
            return URLQueryItem(name: key, value: value)
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw CompanionAPIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let body {
            request.httpBody = try JSONEncoder().encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            if let urlError = error as? URLError {
                throw CompanionAPIError.transport("NETWORK_ERROR_\(urlError.code.rawValue): \(urlError.localizedDescription)")
            }
            throw CompanionAPIError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw CompanionAPIError.invalidResponse
        }

        if !(200 ..< 300).contains(http.statusCode) {
            if let backend = try? JSONDecoder().decode(APIErrorResponse.self, from: data) {
                throw CompanionAPIError.backend(code: backend.error.code, message: backend.error.message)
            }
            throw CompanionAPIError.transport("HTTP \(http.statusCode)")
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw CompanionAPIError.transport("Could not decode response for \(path): \(error.localizedDescription)")
        }
    }

    private func shouldRetry(after error: CompanionAPIError) -> Bool {
        guard case let .transport(message) = error else {
            return false
        }
        if message.hasPrefix("NETWORK_ERROR_") {
            return true
        }
        if message.hasPrefix("HTTP ") || message.hasPrefix("Could not decode response") {
            return false
        }
        let lowered = message.lowercased()
        let networkHints = [
            "connect",
            "connection",
            "offline",
            "timed out",
            "cannot find host",
            "could not resolve",
            "network",
        ]
        return networkHints.contains(where: { lowered.contains($0) })
    }
}
