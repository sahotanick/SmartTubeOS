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
        .id(appState.session.selectedAccountId ?? "signed_out")
        .overlay(alignment: .topLeading) {
            if !showProfileSwitcher && !appState.launchProfileGateVisible {
                profileQuickAccessButton
                    .padding(.top, 58)
                    .padding(.leading, 58)
            }
        }
        .fullScreenCover(isPresented: $showProfileSwitcher) {
            ProfileSwitcherSheet()
                .environmentObject(appState)
        }
        .fullScreenCover(isPresented: launchProfileGateBinding) {
            LaunchProfileGateView()
                .environmentObject(appState)
        }
    }

    private func tabNavigation<Content: View>(title: String, systemImage: String, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
        }
        .tabItem { Label(title, systemImage: systemImage) }
    }

    private var profileQuickAccessButton: some View {
        Button {
            showProfileSwitcher = true
        } label: {
            ZStack(alignment: .bottomTrailing) {
                Image(systemName: "person.crop.circle.fill")
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.92))
                    .frame(width: 48, height: 48)
                    .background(
                        Circle()
                            .fill(Color.black.opacity(0.45))
                    )
                    .overlay(
                        Circle()
                            .strokeBorder(Color.white.opacity(0.25), lineWidth: 1)
                    )

                Circle()
                    .fill(appState.session.signedIn ? Color.green : Color.gray)
                    .frame(width: 10, height: 10)
                    .overlay(
                        Circle()
                            .strokeBorder(Color.black.opacity(0.4), lineWidth: 1)
                    )
                    .offset(x: 2, y: 2)
            }
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Profiles")
        .accessibilityHint("Open profile switcher")
        .zIndex(2)
    }

    private var launchProfileGateBinding: Binding<Bool> {
        Binding(
            get: { appState.launchProfileGateVisible },
            set: { isPresented in
                if !isPresented {
                    appState.dismissLaunchProfileGate()
                }
            }
        )
    }
}

private struct ProfileSwitcherSheet: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var pendingRemoval: AccountSummary?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black
                    .ignoresSafeArea()

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
                                HStack(spacing: 20) {
                                    Button {
                                        Task {
                                            await appState.selectAccount(account.id)
                                            dismiss()
                                        }
                                    } label: {
                                        HStack(spacing: 12) {
                                            ProfileAvatarBadge(account: account, size: 48)

                                            Text(account.name)
                                                .lineLimit(1)

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
                                    .frame(maxWidth: .infinity, alignment: .leading)

                                    Button(role: .destructive) {
                                        pendingRemoval = account
                                    } label: {
                                        Image(systemName: "trash")
                                    }
                                    .frame(width: 64, height: 56)
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

private struct LaunchProfileGateView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text("Who’s Watching?")
                        .font(.system(size: 64, weight: .bold))
                        .padding(.top, 30)

                    if appState.accounts.isEmpty {
                        VStack(alignment: .leading, spacing: 14) {
                            Text("No profiles are loaded yet.")
                                .font(.title3)
                                .foregroundStyle(.secondary)
                            Button("Start Sign-In") {
                                Task { await appState.startSignIn() }
                            }
                            .disabled(appState.isLoading)

                            Button("Continue Signed-Out") {
                                Task { await appState.selectLaunchAccount(nil) }
                            }
                            .disabled(appState.isLoading)
                        }
                    } else {
                        LazyVStack(alignment: .leading, spacing: 16) {
                            ForEach(appState.accounts) { account in
                                Button {
                                    Task { await appState.selectLaunchAccount(account.id) }
                                } label: {
                                    HStack(spacing: 20) {
                                        ProfileAvatarBadge(account: account, size: 88)

                                        Text(account.name)
                                            .font(.system(size: 44, weight: .semibold))

                                        Spacer()

                                        if account.selected {
                                            Text("Current")
                                                .font(.title3.bold())
                                                .foregroundStyle(.green)
                                        }
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(20)
                                    .background(
                                        RoundedRectangle(cornerRadius: 20)
                                            .fill(account.selected ? Color.green.opacity(0.18) : Color.white.opacity(0.08))
                                    )
                                }
                                .buttonStyle(.plain)
                                .disabled(appState.isLoading)
                            }
                        }
                    }

                    if let message = appState.errorMessage {
                        Text(message)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }
                .padding(.horizontal, 70)
                .padding(.bottom, 40)
            }
            .background(Color.black.opacity(0.85).ignoresSafeArea())
            .task {
                if !appState.hasBootstrapped {
                    await appState.bootstrap()
                }
            }
        }
    }
}

private struct ProfileAvatarBadge: View {
    let account: AccountSummary?
    let size: CGFloat

    var body: some View {
        ZStack {
            placeholder

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
                            .frame(width: size, height: size)
                            .clipped()
                    default:
                        EmptyView()
                    }
                }
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .contentShape(Circle())
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
