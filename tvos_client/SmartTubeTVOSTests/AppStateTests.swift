import XCTest
@testable import SmartTubeTVOS

@MainActor
final class AppStateTests: XCTestCase {
    private var session: URLSession!
    private var defaults: UserDefaults!
    private var defaultsSuiteName: String!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLProtocolMock.self]
        session = URLSession(configuration: config)
        defaultsSuiteName = "SmartTubeTVOSTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: defaultsSuiteName)!
    }

    override func tearDown() {
        URLProtocolMock.requestHandler = nil
        if let defaultsSuiteName {
            UserDefaults.standard.removePersistentDomain(forName: defaultsSuiteName)
        }
        defaultsSuiteName = nil
        defaults = nil
        session = nil
        super.tearDown()
    }

    func testBootstrapLoadsSessionAndAccounts() async {
        URLProtocolMock.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.url?.path == "/v1/session" {
                let data = Data("{\"signedIn\":true,\"selectedAccountId\":\"acc_456\"}".utf8)
                return (response, data)
            }
            if request.url?.path == "/v1/accounts" {
                let data = Data(
                    """
                    {
                      "selectedAccountId":"acc_456",
                      "accounts":[
                        {"id":"acc_123","name":"John","email":"john@example.com","avatarUrl":null,"selected":false},
                        {"id":"acc_456","name":"Brand","email":"brand@example.com","avatarUrl":null,"selected":true}
                      ]
                    }
                    """.utf8
                )
                return (response, data)
            }
            return (response, Data())
        }

        let api = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: session)
        let state = AppState(api: api, defaults: defaults)

        await state.bootstrap()

        XCTAssertTrue(state.session.signedIn)
        XCTAssertEqual(state.session.selectedAccountId, "acc_456")
        XCTAssertEqual(state.accounts.count, 2)
        XCTAssertEqual(state.accounts.first?.id, "acc_123")
    }

    func testRecentSearchesAreDeduplicatedAndPersisted() async {
        URLProtocolMock.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.url?.path == "/v1/session" {
                return (response, Data("{\"signedIn\":true,\"selectedAccountId\":\"acc_123\"}".utf8))
            }
            if request.url?.path == "/v1/accounts" {
                let data = Data(
                    """
                    {"selectedAccountId":"acc_123","accounts":[{"id":"acc_123","name":"John","email":"john@example.com","avatarUrl":null,"selected":true}]}
                    """.utf8
                )
                return (response, data)
            }
            return (response, Data())
        }

        let api = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: session)
        let state = AppState(api: api, defaults: defaults)
        await state.bootstrap()

        state.addRecentSearch("smarttube")
        state.addRecentSearch("youtube")
        state.addRecentSearch("SmartTube")

        XCTAssertEqual(state.recentSearches.count, 2)
        XCTAssertEqual(state.recentSearches.first, "SmartTube")
    }

    func testRecordWatchProgressUpdatesContinueWatchingForSelectedAccount() async {
        URLProtocolMock.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.url?.path == "/v1/session" {
                return (response, Data("{\"signedIn\":true,\"selectedAccountId\":\"acc_123\"}".utf8))
            }
            if request.url?.path == "/v1/accounts" {
                let data = Data(
                    """
                    {"selectedAccountId":"acc_123","accounts":[{"id":"acc_123","name":"John","email":"john@example.com","avatarUrl":null,"selected":true}]}
                    """.utf8
                )
                return (response, data)
            }
            return (response, Data())
        }

        let api = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: session)
        let state = AppState(api: api, defaults: defaults)
        await state.bootstrap()

        state.recordWatchProgress(
            videoId: "v1",
            title: "Video One",
            channelName: "Channel",
            thumbnailUrl: "https://i.example/v1.jpg",
            positionSec: 120,
            durationSec: 600
        )

        XCTAssertEqual(state.continueWatching.count, 1)
        XCTAssertEqual(state.continueWatching.first?.videoId, "v1")
    }
}
