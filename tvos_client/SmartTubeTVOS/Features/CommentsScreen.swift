import SwiftUI

struct CommentsScreen: View {
    let initialCommentsKey: String

    @EnvironmentObject private var appState: AppState

    @State private var items: [CommentItem] = []
    @State private var nextKey: String?
    @State private var selectedReplies: [CommentItem] = []
    @State private var showReplies = false
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                List(items) { comment in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(comment.authorName)
                            .font(.headline)
                        Text(comment.message)
                        Text("\(comment.publishedText) • \(comment.likeCountText) likes")
                            .font(.footnote)
                            .foregroundStyle(.secondary)

                        if let nestedKey = comment.nestedCommentsKey {
                            Button("View Replies (\(comment.replyCountText))") {
                                Task { await loadReplies(nestedKey: nestedKey) }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }

                if let nextKey {
                    Button(isLoading ? "Loading..." : "Load More Comments") {
                        Task { await loadComments(commentsKey: nextKey, append: true) }
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
                            let key = nextKey ?? initialCommentsKey
                            Task { await loadComments(commentsKey: key, append: nextKey != nil) }
                        }
                        .disabled(isLoading)
                    }
                }
            }
            .padding(24)
            .navigationTitle("Comments")
            .task {
                await loadComments(commentsKey: initialCommentsKey, append: false)
            }
            .sheet(isPresented: $showReplies) {
                NavigationStack {
                    List(selectedReplies) { reply in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(reply.authorName)
                                .font(.headline)
                            Text(reply.message)
                            Text(reply.publishedText)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                    .navigationTitle("Replies")
                }
            }
        }
    }

    private func loadComments(commentsKey: String, append: Bool) async {
        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await appState.api.fetchComments(commentsKey: commentsKey)
            if append {
                items.append(contentsOf: response.items)
            } else {
                items = response.items
            }
            nextKey = response.nextCommentsKey
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadReplies(nestedKey: String) async {
        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await appState.api.fetchReplies(nestedCommentsKey: nestedKey)
            selectedReplies = response.items
            showReplies = true
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
