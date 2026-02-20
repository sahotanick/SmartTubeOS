import XCTest
@testable import SmartTubeTVOS

@MainActor
final class AppStateTests: XCTestCase {
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLProtocolMock.self]
        session = URLSession(configuration: config)
    }

    override func tearDown() {
        URLProtocolMock.requestHandler = nil
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
        let state = AppState(api: api)

        await state.bootstrap()

        XCTAssertTrue(state.session.signedIn)
        XCTAssertEqual(state.session.selectedAccountId, "acc_456")
        XCTAssertEqual(state.accounts.count, 2)
        XCTAssertEqual(state.accounts.first?.id, "acc_123")
    }
}
