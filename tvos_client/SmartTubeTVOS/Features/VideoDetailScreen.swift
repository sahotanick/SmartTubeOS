import AVKit
import SwiftUI

struct VideoDetailScreen: View {
    let videoId: String

    @EnvironmentObject private var appState: AppState

    @State private var metadata: VideoMetadataResponse?
    @State private var playback: PlaybackResponse?
    @State private var showPlayer = false
    @State private var showComments = false
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let metadata {
                    Text(metadata.title)
                        .font(.title2)
                        .bold()
                    Text("\(metadata.channelName) • \(metadata.publishedText) • \(metadata.viewCountText)")
                        .foregroundStyle(.secondary)

                    HStack(spacing: 12) {
                        Button("Play") {
                            showPlayer = true
                        }
                        .disabled(playback == nil)

                        Button("Comments") {
                            showComments = true
                        }
                        .disabled(metadata.commentsKey == nil)
                    }

                    Text("Description")
                        .font(.title3)
                        .bold()

                    if metadata.description.isEmpty {
                        Text("Description not available")
                            .foregroundStyle(.secondary)
                    } else {
                        Text(metadata.description)
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
            .padding(40)
        }
        .navigationTitle("Video")
        .task {
            await loadData()
        }
        .sheet(isPresented: $showPlayer) {
            if let stream = playback?.streamUrl, let url = URL(string: stream) {
                PlayerScreen(streamURL: url)
            } else {
                Text("Playback unavailable")
            }
        }
        .sheet(isPresented: $showComments) {
            if let commentsKey = metadata?.commentsKey {
                CommentsScreen(initialCommentsKey: commentsKey)
                    .environmentObject(appState)
            } else {
                Text("Comments unavailable")
            }
        }
    }

    private func loadData() async {
        isLoading = true
        defer { isLoading = false }

        do {
            async let metadataTask = appState.api.fetchMetadata(videoId: videoId)
            async let playbackTask = appState.api.fetchPlayback(videoId: videoId)
            metadata = try await metadataTask
            playback = try await playbackTask
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct PlayerScreen: View {
    let streamURL: URL

    @State private var player: AVPlayer

    init(streamURL: URL) {
        self.streamURL = streamURL
        _player = State(initialValue: AVPlayer(url: streamURL))
    }

    var body: some View {
        VideoPlayer(player: player)
            .onAppear { player.play() }
            .onDisappear { player.pause() }
    }
}
