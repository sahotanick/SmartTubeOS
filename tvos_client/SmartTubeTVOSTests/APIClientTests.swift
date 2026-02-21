import XCTest
@testable import SmartTubeTVOS

final class APIClientTests: XCTestCase {
    private var session: URLSession!
    private var client: APIClient!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLProtocolMock.self]
        session = URLSession(configuration: config)
        client = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: session)
    }

    override func tearDown() {
        URLProtocolMock.requestHandler = nil
        session = nil
        client = nil
        super.tearDown()
    }

    func testFetchSessionDecodesPayload() async throws {
        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/session")
            let json = """
            {"signedIn":true,"selectedAccountId":"acc_123"}
            """
            let data = Data(json.utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, data)
        }

        let result = try await client.fetchSession()
        XCTAssertTrue(result.signedIn)
        XCTAssertEqual(result.selectedAccountId, "acc_123")
    }

    func testBackendErrorIsDecoded() async {
        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/feed/subscriptions")
            let json = """
            {"error":{"code":"AUTH_REQUIRED","message":"Sign-in required"}}
            """
            let data = Data(json.utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!
            return (response, data)
        }

        do {
            _ = try await client.fetchSubscriptions(continuationToken: nil)
            XCTFail("Expected error")
        } catch let error as CompanionAPIError {
            switch error {
            case let .backend(code, message):
                XCTAssertEqual(code, "AUTH_REQUIRED")
                XCTAssertEqual(message, "Sign-in required")
            default:
                XCTFail("Unexpected error type: \(error)")
            }
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testFetchSessionFallsBackToLocalhostWhenPrimaryHostIsUnreachable() async throws {
        var primaryAttempts = 0
        var fallbackAttempts = 0

        client = APIClient(
            baseURL: URL(string: "http://192.168.1.15:8000")!,
            fallbackBaseURLs: [URL(string: "http://127.0.0.1:8000")!],
            session: session
        )

        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/session")
            let host = request.url?.host ?? ""
            if host == "192.168.1.15" {
                primaryAttempts += 1
                throw URLError(.cannotConnectToHost)
            }
            if host == "127.0.0.1" {
                fallbackAttempts += 1
                let json = """
                {"signedIn":true,"selectedAccountId":"acc_123"}
                """
                let data = Data(json.utf8)
                let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
                return (response, data)
            }
            XCTFail("Unexpected host: \(host)")
            throw URLError(.badURL)
        }

        let result = try await client.fetchSession()
        XCTAssertTrue(result.signedIn)
        XCTAssertEqual(result.selectedAccountId, "acc_123")
        XCTAssertEqual(primaryAttempts, 1)
        XCTAssertEqual(fallbackAttempts, 1)
        XCTAssertEqual(client.baseURL.host, "127.0.0.1")
    }

    func testRefreshAccountsDecodesPayload() async throws {
        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/accounts/refresh")
            XCTAssertEqual(request.httpMethod, "POST")
            let json = """
            {"status":"REFRESHED","selectedAccountId":"google_user-1","discoveredProfileCount":1,"totalProfileCount":2}
            """
            let data = Data(json.utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, data)
        }

        let result = try await client.refreshAccounts()
        XCTAssertEqual(result.status, "REFRESHED")
        XCTAssertEqual(result.selectedAccountId, "google_user-1")
        XCTAssertEqual(result.discoveredProfileCount, 1)
        XCTAssertEqual(result.totalProfileCount, 2)
    }

    func testSearchSuggestionsDecodesPayload() async throws {
        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/search/suggestions")
            XCTAssertEqual(request.url?.query, "q=smart")
            let json = """
            {"query":"smart","suggestions":["smarttube","smarttube tvos"]}
            """
            let data = Data(json.utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, data)
        }

        let result = try await client.searchSuggestions(query: "smart")
        XCTAssertEqual(result.query, "smart")
        XCTAssertEqual(result.suggestions.count, 2)
    }

    func testRelatedAndChannelFeedDecodesPayload() async throws {
        var callCount = 0
        URLProtocolMock.requestHandler = { request in
            callCount += 1
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"title":"Up Next","continuationToken":null,"items":[{"videoId":"v1","title":"One","channelName":"C","channelId":"chan","thumbnailUrl":"https://i.example/v1.jpg","publishedText":"1 day ago","durationSec":0}]}
            """
            return (response, Data(json.utf8))
        }

        let related = try await client.fetchRelated(videoId: "abc", continuationToken: nil)
        XCTAssertEqual(related.title, "Up Next")
        XCTAssertEqual(related.items.first?.videoId, "v1")

        let channel = try await client.fetchChannelVideos(channelId: "chan", continuationToken: nil)
        XCTAssertEqual(channel.items.first?.channelId, "chan")
        XCTAssertEqual(callCount, 2)
    }

    func testMusicFeedDecodesPayload() async throws {
        URLProtocolMock.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/v1/feed/music")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"title":"Music","continuationToken":null,"items":[{"videoId":"m1","title":"Track","channelName":"Artist","channelId":"chan-m","thumbnailUrl":"https://i.example/m1.jpg","publishedText":"1 day ago","durationSec":0}]}
            """
            return (response, Data(json.utf8))
        }

        let feed = try await client.fetchMusic(continuationToken: nil)
        XCTAssertEqual(feed.title, "Music")
        XCTAssertEqual(feed.items.first?.videoId, "m1")
    }
}
