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
}
