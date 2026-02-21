import SwiftUI

@main
struct SmartTubeTVOSApp: App {
    @StateObject private var appState = AppState(
        api: APIClient(baseURL: AppConfig.baseURL, fallbackBaseURLs: AppConfig.fallbackBaseURLs)
    )

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
    private static let localhost = URL(string: "http://127.0.0.1:8000")!

    private static let configuredBaseURL: URL? = {
        guard let env = ProcessInfo.processInfo.environment["COMPANION_BASE_URL"] else {
            return nil
        }
        return URL(string: env)
    }()

    private static let autoBaseURL: URL? = {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: "CompanionAutoBaseURL") as? String else {
            return nil
        }
        return URL(string: raw)
    }()

    static let baseURL: URL = {
#if targetEnvironment(simulator)
        return localhost
#else
        return autoBaseURL ?? configuredBaseURL ?? localhost
#endif
    }()

    static let fallbackBaseURLs: [URL] = {
        var fallbacks: [URL] = []
        let appendIfNeeded: (URL?) -> Void = { candidate in
            guard let candidate else { return }
            guard candidate.absoluteString != baseURL.absoluteString else { return }
            guard !fallbacks.contains(where: { $0.absoluteString == candidate.absoluteString }) else { return }
            fallbacks.append(candidate)
        }
#if targetEnvironment(simulator)
        appendIfNeeded(configuredBaseURL)
        appendIfNeeded(autoBaseURL)
#else
        appendIfNeeded(autoBaseURL)
        appendIfNeeded(configuredBaseURL)
        appendIfNeeded(localhost)
#endif
        return fallbacks
    }()
}
