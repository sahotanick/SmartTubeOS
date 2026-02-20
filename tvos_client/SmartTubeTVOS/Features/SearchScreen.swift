import SwiftUI

struct SearchScreen: View {
    @EnvironmentObject private var appState: AppState

    @State private var query = ""
    @State private var items: [VideoFeedItem] = []
    @State private var continuationToken: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                TextField("Search YouTube", text: $query)
                Button("Search") {
                    Task { await runSearch(reset: true) }
                }
                .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            List(items) { item in
                NavigationLink {
                    VideoDetailScreen(videoId: item.videoId)
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.title)
                            .font(.headline)
                        Text("\(item.channelName) • \(item.publishedText)")
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let continuationToken {
                Button(isLoading ? "Loading..." : "Load More") {
                    Task { await runSearch(reset: false, continuation: continuationToken) }
                }
                .disabled(isLoading)
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
        .navigationTitle("Search")
    }

    private func runSearch(reset: Bool, continuation: String? = nil) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await appState.api.search(query: trimmed, continuationToken: continuation)
            if reset {
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
