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
                if title == "Home", !appState.continueWatching.isEmpty {
                    continueWatchingRail
                }

                if items.isEmpty && !isLoading {
                    Text("No items available.")
                        .font(.headline)
                }

                List(items) { item in
                    NavigationLink {
                        VideoDetailScreen(videoId: item.videoId)
                    } label: {
                        VideoRowView(item: item)
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
                VStack(alignment: .leading, spacing: 10) {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.footnote)
                    Button("Retry") {
                        Task { await refresh() }
                    }
                    .disabled(isLoading)
                }
            }
        }
        .navigationTitle(title)
        .task(id: appState.session.selectedAccountId) {
            await refresh()
        }
    }

    private var continueWatchingRail: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Continue Watching")
                .font(.title3.bold())

            ScrollView(.horizontal) {
                HStack(spacing: 16) {
                    ForEach(appState.continueWatching) { entry in
                        NavigationLink {
                            VideoDetailScreen(videoId: entry.videoId)
                        } label: {
                            ContinueWatchingCard(entry: entry)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 4)
            }
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

private struct ContinueWatchingCard: View {
    let entry: WatchProgressEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack(alignment: .bottomLeading) {
                thumbnail
                    .frame(width: 300, height: 168)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.white.opacity(0.25))
                    .frame(height: 5)
                    .overlay(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.red)
                            .frame(width: 300 * entry.progressFraction, height: 5)
                    }
            }

            Text(entry.title)
                .font(.headline)
                .lineLimit(2)
                .frame(width: 300, alignment: .leading)

            Text(entry.channelName)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .frame(width: 300, alignment: .leading)
        }
    }

    @ViewBuilder
    private var thumbnail: some View {
        if let url = URL(string: entry.thumbnailUrl), !entry.thumbnailUrl.isEmpty {
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
        } else {
            placeholder
        }
    }

    private var placeholder: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.gray.opacity(0.25))
            Image(systemName: "play.tv.fill")
                .font(.title2)
                .foregroundStyle(.white.opacity(0.85))
        }
    }
}
