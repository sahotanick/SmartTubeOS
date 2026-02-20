import Foundation

@MainActor
final class AppState: ObservableObject {
    @Published private(set) var session = SessionSummary(signedIn: false, selectedAccountId: nil)
    @Published private(set) var accounts: [AccountSummary] = []
    @Published private(set) var authStart: AuthStartResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func bootstrap() async {
        await refreshSessionAndAccounts()
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
            await refreshSessionAndAccounts()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectAccount(_ accountId: String?) async {
        isLoading = true
        defer { isLoading = false }

        do {
            _ = try await api.selectAccount(accountId: accountId)
            await refreshSessionAndAccounts()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
