import Foundation

@MainActor
final class AppState: ObservableObject {
    @Published private(set) var session = SessionSummary(signedIn: false, selectedAccountId: nil)
    @Published private(set) var accounts: [AccountSummary] = []
    @Published private(set) var authStart: AuthStartResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var hasBootstrapped = false
    @Published private(set) var launchProfileGateVisible = false
    @Published private(set) var recentSearches: [String] = []
    @Published private(set) var continueWatching: [WatchProgressEntry] = []
    @Published var errorMessage: String?
    @Published var profileHintMessage: String?

    let api: APIClient
    private let defaults: UserDefaults
    private let recentSearchesKey = "smarttube_recent_searches_v2"
    private let watchProgressKey = "smarttube_watch_progress_v2"
    private var watchProgressByAccount: [String: [WatchProgressEntry]] = [:]

    var selectedAccount: AccountSummary? {
        accounts.first(where: { $0.selected })
    }

    init(api: APIClient, defaults: UserDefaults = .standard) {
        self.api = api
        self.defaults = defaults
        loadRecentSearches()
        loadWatchProgress()
        updateContinueWatchingForSelectedAccount()
    }

    func bootstrap() async {
        await refreshSessionAndAccounts()
        hasBootstrapped = true
        launchProfileGateVisible = !accounts.isEmpty
    }

    func refreshSessionAndAccounts() async {
        isLoading = true
        defer { isLoading = false }

        do {
            async let sessionTask = api.fetchSession()
            async let accountsTask = api.fetchAccounts()
            session = try await sessionTask
            let accountResponse = try await accountsTask
            accounts = accountResponse.accounts
            authStart = nil
            profileHintMessage = profileHint(for: accountResponse.accounts)
            updateContinueWatchingForSelectedAccount()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startSignIn() async {
        isLoading = true
        defer { isLoading = false }

        do {
            authStart = try await api.authStart()
            profileHintMessage = nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func pollSignIn() async {
        guard authStart != nil else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let poll = try await api.authPoll()
            if poll.status == "SIGNED_IN" {
                authStart = nil
                await refreshSessionAndAccounts()
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func signOut() async {
        isLoading = true
        defer { isLoading = false }

        do {
            _ = try await api.authSignout()
            authStart = nil
            profileHintMessage = nil
            await refreshSessionAndAccounts()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectAccount(_ accountId: String?) async {
        _ = await selectAccountInternal(accountId)
    }

    func selectLaunchAccount(_ accountId: String?) async {
        let success = await selectAccountInternal(accountId)
        if success {
            launchProfileGateVisible = false
        }
    }

    func dismissLaunchProfileGate() {
        launchProfileGateVisible = false
    }

    func removeAccount(_ accountId: String) async {
        isLoading = true
        defer { isLoading = false }

        do {
            _ = try await api.removeAccount(accountId: accountId)
            await refreshSessionAndAccounts()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshProfilesFromGoogle() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let refresh = try await api.refreshAccounts()
            await refreshSessionAndAccounts()

            if refresh.discoveredProfileCount <= 1 {
                profileHintMessage = "Google currently returned one profile for this sign-in. Use Add Profile to sign in with another Google account if needed."
            } else {
                profileHintMessage = "Refreshed \(refresh.discoveredProfileCount) profiles from Google."
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func profileHint(for accounts: [AccountSummary]) -> String? {
        if session.signedIn, accounts.count <= 1 {
            return "Only one profile is currently available from Google for this sign-in."
        }
        return nil
    }

    func addRecentSearch(_ query: String) {
        let cleaned = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }

        recentSearches.removeAll { $0.caseInsensitiveCompare(cleaned) == .orderedSame }
        recentSearches.insert(cleaned, at: 0)
        if recentSearches.count > 15 {
            recentSearches = Array(recentSearches.prefix(15))
        }
        persistRecentSearches()
    }

    func removeRecentSearch(_ query: String) {
        recentSearches.removeAll { $0.caseInsensitiveCompare(query) == .orderedSame }
        persistRecentSearches()
    }

    func clearRecentSearches() {
        recentSearches = []
        persistRecentSearches()
    }

    func recordWatchProgress(
        videoId: String,
        title: String,
        channelName: String,
        thumbnailUrl: String,
        positionSec: Double,
        durationSec: Double
    ) {
        guard let accountId = session.selectedAccountId else { return }
        guard positionSec.isFinite, durationSec.isFinite else { return }
        guard positionSec >= 3 else { return }

        var rows = watchProgressByAccount[accountId] ?? []
        rows.removeAll { $0.videoId == videoId }

        if durationSec > 0, positionSec / durationSec >= 0.95 {
            watchProgressByAccount[accountId] = rows
            persistWatchProgress()
            updateContinueWatchingForSelectedAccount()
            return
        }

        rows.append(
            WatchProgressEntry(
                accountId: accountId,
                videoId: videoId,
                title: title,
                channelName: channelName,
                thumbnailUrl: thumbnailUrl,
                lastPositionSec: positionSec,
                durationSec: max(durationSec, 0),
                updatedAtEpochSec: Int(Date().timeIntervalSince1970)
            )
        )
        rows.sort { $0.updatedAtEpochSec > $1.updatedAtEpochSec }
        if rows.count > 80 {
            rows = Array(rows.prefix(80))
        }
        watchProgressByAccount[accountId] = rows
        persistWatchProgress()
        updateContinueWatchingForSelectedAccount()
    }

    func continueWatchingEntry(for videoId: String) -> WatchProgressEntry? {
        guard let accountId = session.selectedAccountId else { return nil }
        return (watchProgressByAccount[accountId] ?? []).first { $0.videoId == videoId }
    }

    func removeContinueWatching(videoId: String) {
        guard let accountId = session.selectedAccountId else { return }
        var rows = watchProgressByAccount[accountId] ?? []
        rows.removeAll { $0.videoId == videoId }
        watchProgressByAccount[accountId] = rows
        persistWatchProgress()
        updateContinueWatchingForSelectedAccount()
    }

    private func updateContinueWatchingForSelectedAccount() {
        guard let accountId = session.selectedAccountId else {
            continueWatching = []
            return
        }
        let rows = (watchProgressByAccount[accountId] ?? []).sorted { $0.updatedAtEpochSec > $1.updatedAtEpochSec }
        continueWatching = Array(rows.prefix(20))
    }

    private func loadRecentSearches() {
        if let data = defaults.data(forKey: recentSearchesKey),
           let decoded = try? JSONDecoder().decode([String].self, from: data)
        {
            recentSearches = decoded
        } else {
            recentSearches = []
        }
    }

    private func persistRecentSearches() {
        if let encoded = try? JSONEncoder().encode(recentSearches) {
            defaults.set(encoded, forKey: recentSearchesKey)
        }
    }

    private func loadWatchProgress() {
        if let data = defaults.data(forKey: watchProgressKey),
           let decoded = try? JSONDecoder().decode([String: [WatchProgressEntry]].self, from: data)
        {
            watchProgressByAccount = decoded
        } else {
            watchProgressByAccount = [:]
        }
    }

    private func persistWatchProgress() {
        if let encoded = try? JSONEncoder().encode(watchProgressByAccount) {
            defaults.set(encoded, forKey: watchProgressKey)
        }
    }

    private func selectAccountInternal(_ accountId: String?) async -> Bool {
        isLoading = true
        defer { isLoading = false }

        do {
            _ = try await api.selectAccount(accountId: accountId)
            await refreshSessionAndAccounts()
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}
