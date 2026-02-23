import SwiftUI

struct SearchScreen: View {
    @EnvironmentObject private var appState: AppState

    @State private var query = ""
    @State private var suggestions: [String] = []
    @State private var items: [VideoFeedItem] = []
    @State private var continuationToken: String?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var suggestionTask: Task<Void, Never>?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                TextField("Search YouTube", text: $query)
                    .submitLabel(.search)
                    .onSubmit {
                        Task { await runSearch(reset: true) }
                    }
                Button("Search") {
                    Task { await runSearch(reset: true) }
                }
                .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !appState.recentSearches.isEmpty {
                recentSearchesSection
            } else if !suggestions.isEmpty {
                suggestionsSection
            }

            List(items) { item in
                NavigationLink {
                    VideoDetailScreen(videoId: item.videoId, queueContext: items)
                } label: {
                    VideoRowView(item: item)
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
                VStack(alignment: .leading, spacing: 10) {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.footnote)
                    Button("Retry") {
                        Task { await runSearch(reset: continuationToken == nil) }
                    }
                    .disabled(isLoading || query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .navigationTitle("Search")
        .onChange(of: query) { _, newValue in
            scheduleSuggestions(for: newValue)
        }
        .onDisappear {
            suggestionTask?.cancel()
        }
    }

    private func runSearch(reset: Bool, continuation: String? = nil) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        collapseSuggestions()

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
            if reset {
                appState.addRecentSearch(trimmed)
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private var recentSearchesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Recent Searches")
                    .font(.headline)
                Spacer()
                Button("Clear") {
                    appState.clearRecentSearches()
                }
            }

            ForEach(appState.recentSearches, id: \.self) { recent in
                Button(recent) {
                    query = recent
                    Task { await runSearch(reset: true) }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var suggestionsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Suggestions")
                .font(.headline)

            ForEach(suggestions, id: \.self) { suggestion in
                Button(suggestion) {
                    query = suggestion
                    Task { await runSearch(reset: true) }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func scheduleSuggestions(for rawQuery: String) {
        suggestionTask?.cancel()
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            suggestions = []
            return
        }

        suggestionTask = Task {
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            do {
                let response = try await appState.api.searchSuggestions(query: trimmed)
                guard !Task.isCancelled else { return }
                suggestions = response.suggestions
            } catch {
                if Task.isCancelled {
                    return
                }
                suggestions = []
            }
        }
    }

    private func collapseSuggestions() {
        suggestionTask?.cancel()
        suggestions = []
    }
}
