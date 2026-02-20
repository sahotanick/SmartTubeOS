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
            return "\(code): \(message)"
        case let .transport(message):
            return message
        }
    }
}

final class APIClient {
    let baseURL: URL
    private let session: URLSession

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
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

    func fetchHome(continuationToken: String?) async throws -> FeedResponse {
        try await request("/v1/feed/home", method: "GET", query: ["continuationToken": continuationToken])
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

    func fetchMetadata(videoId: String) async throws -> VideoMetadataResponse {
        try await request("/v1/video/\(videoId)/metadata", method: "GET")
    }

    func fetchPlayback(videoId: String) async throws -> PlaybackResponse {
        try await request("/v1/video/\(videoId)/playback", method: "GET")
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
}
