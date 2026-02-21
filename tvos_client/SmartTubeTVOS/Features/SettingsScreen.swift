import CoreImage.CIFilterBuiltins
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
                DeviceSignInGuide(authStart: authStart)
                Button("Poll Sign-In") {
                    Task { await appState.pollSignIn() }
                }
                .disabled(appState.isLoading)

                Button("Restart Sign-In") {
                    Task { await appState.startSignIn() }
                }
                .disabled(appState.isLoading)
            } else {
                Button("Start Add Profile Sign-In") {
                    Task { await appState.startSignIn() }
                }
                .disabled(appState.isLoading)
            }

            Button("Sign Out Current Profile") {
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

            Button("Refresh Profiles from Google") {
                Task { await appState.refreshProfilesFromGoogle() }
            }
            .disabled(!appState.session.signedIn || appState.isLoading)

            if let hint = appState.profileHintMessage {
                Text(hint)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if appState.accounts.isEmpty {
                Text("No accounts available")
                    .foregroundStyle(.secondary)
            }

            ForEach(appState.accounts) { account in
                HStack(spacing: 12) {
                    Button {
                        Task { await appState.selectAccount(account.id) }
                    } label: {
                        HStack(spacing: 12) {
                            accountAvatar(account)

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
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(account.selected || appState.isLoading)

                    Button(role: .destructive) {
                        Task { await appState.removeAccount(account.id) }
                    } label: {
                        Image(systemName: "trash")
                    }
                    .disabled(appState.accounts.count <= 1 || appState.isLoading)
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(account.selected ? Color.green.opacity(0.18) : Color.white.opacity(0.06))
                )
            }
        }
    }

    @ViewBuilder
    private func accountAvatar(_ account: AccountSummary) -> some View {
        let side: CGFloat = 46
        if let avatar = account.avatarUrl, let url = URL(string: avatar), !avatar.isEmpty {
            AsyncImage(url: url) { phase in
                switch phase {
                case let .success(image):
                    image
                        .resizable()
                        .scaledToFill()
                default:
                    fallbackAvatar
                }
            }
            .frame(width: side, height: side)
            .clipped()
            .clipShape(Circle())
        } else {
            fallbackAvatar
                .frame(width: side, height: side)
        }
    }

    private var fallbackAvatar: some View {
        Circle()
            .fill(Color.gray.opacity(0.25))
            .overlay(
                Image(systemName: "person.fill")
                    .foregroundStyle(.white.opacity(0.9))
            )
    }

    private var endpointSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Companion")
                .font(.title3)
                .bold()
            Text(appState.api.baseURL.absoluteString)
                .foregroundStyle(.secondary)
        }
    }
}

struct DeviceSignInGuide: View {
    let authStart: AuthStartResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Code: \(authStart.signInCode)")
                .font(.title2)
                .bold()

            HStack(alignment: .top, spacing: 16) {
                QRCodeImageView(payload: authStart.verificationURLWithCode)
                    .frame(width: 132, height: 132)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color.white)
                    )

                VStack(alignment: .leading, spacing: 8) {
                    Text("Scan QR, or open:")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text(authStart.verificationUrl)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct QRCodeImageView: View {
    let payload: String

    private let context = CIContext()

    var body: some View {
        Group {
            if let image = makeQRCodeImage() {
                Image(decorative: image, scale: 1.0)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
                    .padding(10)
            } else {
                Image(systemName: "qrcode")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func makeQRCodeImage() -> CGImage? {
        let data = Data(payload.utf8)
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage else {
            return nil
        }
        let transformed = output.transformed(by: CGAffineTransform(scaleX: 12, y: 12))
        return context.createCGImage(transformed, from: transformed.extent)
    }
}
