import SwiftUI

@main
struct SmartTubeTVOSApp: App {
    @StateObject private var appState = AppState(api: APIClient(baseURL: AppConfig.baseURL))

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environmentObject(appState)
                .task {
                    await appState.bootstrap()
                }
        }
    }
}

enum AppConfig {
    static let baseURL: URL = {
        if let env = ProcessInfo.processInfo.environment["COMPANION_BASE_URL"], let url = URL(string: env) {
            return url
        }
        return URL(string: "http://127.0.0.1:8000")!
    }()
}
