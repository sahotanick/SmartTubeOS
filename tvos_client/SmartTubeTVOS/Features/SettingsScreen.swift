import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                sessionSection
                authSection
                accountsSection
                endpointSection
                if let error = appState.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .padding(40)
        }
        .navigationTitle("Settings")
        .task {
            await appState.refreshSessionAndAccounts()
        }
    }

    private var sessionSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Session")
                .font(.title3)
                .bold()
            Text(appState.session.signedIn ? "Signed in" : "Signed out")
            Text("Selected account: \(appState.session.selectedAccountId ?? "none")")
                .foregroundStyle(.secondary)
        }
    }

    private var authSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Google Sign-In")
                .font(.title3)
                .bold()

            if let authStart = appState.authStart {
                Text("Code: \(authStart.signInCode)")
                    .font(.title2)
                    .bold()
                Text("Open: \(authStart.verificationUrl)")
                Button("Poll Sign-In") {
                    Task { await appState.pollSignIn() }
                }
                .disabled(appState.isLoading)
            } else {
                Button("Start Sign-In") {
                    Task { await appState.startSignIn() }
                }
                .disabled(appState.isLoading)
            }

            Button("Sign Out") {
                Task { await appState.signOut() }
            }
            .disabled(appState.isLoading)
        }
    }

    private var accountsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Profiles")
                .font(.title3)
                .bold()

            if appState.accounts.isEmpty {
                Text("No accounts available")
                    .foregroundStyle(.secondary)
            }

            ForEach(appState.accounts) { account in
                HStack(spacing: 12) {
                    Text(account.name)
                    if let email = account.email {
                        Text(email)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if account.selected {
                        Text("Selected")
                            .foregroundStyle(.green)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    Task { await appState.selectAccount(account.id) }
                }
            }
        }
    }

    private var endpointSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Companion")
                .font(.title3)
                .bold()
            Text(AppConfig.baseURL.absoluteString)
                .foregroundStyle(.secondary)
        }
    }
}
