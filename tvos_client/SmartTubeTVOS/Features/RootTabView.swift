import SwiftUI

struct RootTabView: View {
    @EnvironmentObject private var appState: AppState
    @State private var showProfileSwitcher = false

    var body: some View {
        TabView {
            tabNavigation(title: "Home", systemImage: "house") {
                FeedScreen(title: "Home", requiresAuth: false) { token in
                    try await appState.api.fetchHome(continuationToken: token)
                }
            }

            tabNavigation(title: "Music", systemImage: "music.note") {
                FeedScreen(title: "Music", requiresAuth: false) { token in
                    try await appState.api.fetchMusic(continuationToken: token)
                }
            }

            tabNavigation(title: "Search", systemImage: "magnifyingglass") {
                SearchScreen()
            }

            tabNavigation(title: "Subscriptions", systemImage: "rectangle.stack.badge.person.crop") {
                FeedScreen(title: "Subscriptions", requiresAuth: true) { token in
                    try await appState.api.fetchSubscriptions(continuationToken: token)
                }
            }

            tabNavigation(title: "History", systemImage: "clock.arrow.circlepath") {
                FeedScreen(title: "History", requiresAuth: true) { token in
                    try await appState.api.fetchHistory(continuationToken: token)
                }
            }

            tabNavigation(title: "Settings", systemImage: "gearshape") {
                SettingsScreen()
            }
        }
        .fullScreenCover(isPresented: $showProfileSwitcher) {
            ProfileSwitcherSheet()
                .environmentObject(appState)
        }
    }

    private func tabNavigation<Content: View>(title: String, systemImage: String, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        profileQuickAccessButton
                    }
                }
        }
        .tabItem { Label(title, systemImage: systemImage) }
    }

    private var profileQuickAccessButton: some View {
        Button {
            showProfileSwitcher = true
        } label: {
            ProfileToolbarBadge(account: appState.selectedAccount)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Profiles")
        .accessibilityHint("Open profile switcher")
    }
}

private struct ProfileSwitcherSheet: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var pendingRemoval: AccountSummary?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    switcherHeader

                    if appState.accounts.isEmpty {
                        Text("No profiles available")
                            .foregroundStyle(.secondary)
                    } else {
                        HStack(spacing: 12) {
                            Button("Refresh Profiles from Google") {
                                Task { await appState.refreshProfilesFromGoogle() }
                            }
                            .disabled(!appState.session.signedIn || appState.isLoading)

                            Button("Add Profile") {
                                Task { await appState.startSignIn() }
                            }
                            .disabled(appState.isLoading)
                        }

                        if let hint = appState.profileHintMessage {
                            Text(hint)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }

                        ForEach(appState.accounts) { account in
                            HStack(spacing: 16) {
                                Button {
                                    Task { await appState.selectAccount(account.id) }
                                } label: {
                                    HStack(spacing: 12) {
                                        ProfileAvatarBadge(account: account, size: 48)

                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(account.name)
                                            if let email = account.email {
                                                Text(email)
                                                    .font(.footnote)
                                                    .foregroundStyle(.secondary)
                                            }
                                        }

                                        Spacer()

                                        if account.selected {
                                            Text("Current")
                                                .font(.footnote)
                                                .foregroundStyle(.green)
                                        }
                                    }
                                    .padding(12)
                                    .background(
                                        RoundedRectangle(cornerRadius: 12)
                                            .fill(account.selected ? Color.green.opacity(0.18) : Color.white.opacity(0.06))
                                    )
                                }
                                .buttonStyle(.plain)
                                .disabled(account.selected || appState.isLoading)

                                Button(role: .destructive) {
                                    pendingRemoval = account
                                } label: {
                                    Image(systemName: "trash")
                                }
                                .disabled(appState.accounts.count <= 1 || appState.isLoading)
                            }
                        }
                    }

                    Divider()

                    Button("Use Signed-Out Mode") {
                        Task { await appState.selectAccount(nil) }
                    }
                    .disabled(!appState.session.signedIn || appState.isLoading)

                    Divider()

                    if let authStart = appState.authStart {
                        Text("Authorize this profile")
                            .font(.title3)
                            .bold()

                        DeviceSignInGuide(authStart: authStart)

                        HStack(spacing: 12) {
                            Button("Poll Sign-In") {
                                Task { await appState.pollSignIn() }
                            }
                            .disabled(appState.isLoading)

                            Button("Restart") {
                                Task { await appState.startSignIn() }
                            }
                            .disabled(appState.isLoading)
                        }
                    } else {
                        Button("Start Add Profile Sign-In") {
                            Task { await appState.startSignIn() }
                        }
                        .disabled(appState.isLoading)
                    }

                    if let error = appState.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
                .padding(40)
            }
            .navigationTitle("Profiles")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .onExitCommand {
                dismiss()
            }
            .task {
                await appState.refreshSessionAndAccounts()
            }
            .alert("Remove Profile?", isPresented: Binding(get: {
                pendingRemoval != nil
            }, set: { show in
                if !show {
                    pendingRemoval = nil
                }
            })) {
                Button("Cancel", role: .cancel) {
                    pendingRemoval = nil
                }
                Button("Remove", role: .destructive) {
                    guard let account = pendingRemoval else { return }
                    pendingRemoval = nil
                    Task { await appState.removeAccount(account.id) }
                }
            } message: {
                Text("This removes the saved profile from this app.")
            }
        }
    }

    private var switcherHeader: some View {
        HStack(spacing: 16) {
            ProfileAvatarBadge(account: appState.selectedAccount, size: 64)
            VStack(alignment: .leading, spacing: 6) {
                Text("Switch Profile")
                    .font(.title2)
                    .bold()
                Text(appState.selectedAccount?.name ?? "Signed-out mode")
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct ProfileToolbarBadge: View {
    let account: AccountSummary?
    private static let clock: Date.FormatStyle = .dateTime.hour(.defaultDigits(amPM: .omitted)).minute()

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            HStack(spacing: 10) {
                Text(context.date.formatted(Self.clock))
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.92))

                ProfileAvatarBadge(account: account, size: 36)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(Color.black.opacity(0.45))
            )
            .overlay(
                Capsule()
                    .strokeBorder(Color.white.opacity(0.25), lineWidth: 1)
            )
        }
    }
}

private struct ProfileAvatarBadge: View {
    let account: AccountSummary?
    let size: CGFloat

    var body: some View {
        if
            let avatar = account?.avatarUrl,
            let url = URL(string: avatar),
            !avatar.isEmpty
        {
            AsyncImage(url: url) { phase in
                switch phase {
                case let .success(image):
                    image
                        .resizable()
                        .scaledToFill()
                default:
                    placeholder
                }
            }
            .frame(width: size, height: size)
            .clipped()
            .clipShape(Circle())
        } else {
            placeholder
                .frame(width: size, height: size)
        }
    }

    private var placeholder: some View {
        Circle()
            .fill(Color.gray.opacity(0.25))
            .overlay(
                Image(systemName: "person.fill")
                    .foregroundStyle(.white.opacity(0.9))
            )
    }
}
