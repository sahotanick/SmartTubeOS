import SwiftUI

struct FeedScreen: View {
    let title: String
    let requiresAuth: Bool
    let loader: (String?) async throws -> FeedResponse

    @EnvironmentObject private var appState: AppState

    @State private var items: [VideoFeedItem] = []
    @State private var continuationToken: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if requiresAuth && !appState.session.signedIn {
                Text("Sign in from Settings to access \(title).")
                    .font(.headline)
            } else {
                if items.isEmpty && !isLoading {
                    Text("No items available.")
                        .font(.headline)
                }

                List(items) { item in
                    NavigationLink {
                        VideoDetailScreen(videoId: item.videoId)
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(item.title)
                                .font(.headline)
                            Text("\(item.channelName) • \(item.publishedText)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if let continuationToken {
                    Button(isLoading ? "Loading..." : "Load More") {
                        Task {
                            await loadPage(continuation: continuationToken)
                        }
                    }
                    .disabled(isLoading)
                }
            }

            if isLoading {
                ProgressView()
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
                    .font(.footnote)
            }
        }
        .navigationTitle(title)
        .task(id: appState.session.selectedAccountId) {
            await refresh()
        }
    }

    private func refresh() async {
        items = []
        continuationToken = nil
        await loadPage(continuation: nil)
    }

    private func loadPage(continuation: String?) async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await loader(continuation)
            if continuation == nil {
                items = response.items
            } else {
                items.append(contentsOf: response.items)
            }
            continuationToken = response.continuationToken
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
