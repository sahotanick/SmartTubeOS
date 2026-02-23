import AVFoundation
import AVKit
import CoreMedia
import SwiftUI

struct VideoDetailScreen: View {
    let videoId: String
    let queueContext: [VideoFeedItem]?

    init(videoId: String, queueContext: [VideoFeedItem]? = nil) {
        self.videoId = videoId
        self.queueContext = queueContext
    }

    @EnvironmentObject private var appState: AppState
    @AppStorage("autoplay_up_next_enabled") private var autoplayUpNextEnabled = true

    @State private var metadata: VideoMetadataResponse?
    @State private var playback: PlaybackResponse?
    @State private var relatedItems: [VideoFeedItem] = []
    @State private var relatedContinuationToken: String?
    @State private var showPlayer = false
    @State private var didAutoPresentPlayer = false
    @State private var showComments = false
    @State private var autoNavigateRoute: VideoRoute?
    @State private var isLoading = false
    @State private var isLoadingRelated = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let metadata {
                    Text(metadata.title)
                        .font(.title2)
                        .bold()

                    HStack(spacing: 8) {
                        NavigationLink {
                            ChannelVideosScreen(channelId: metadata.channelId, channelName: metadata.channelName)
                                .environmentObject(appState)
                        } label: {
                            Text(metadata.channelName)
                                .foregroundStyle(.white)
                                .underline()
                        }
                        .buttonStyle(.plain)

                        Text("• \(metadata.publishedText) • \(metadata.viewCountText)")
                            .foregroundStyle(.secondary)
                    }

                    HStack(spacing: 12) {
                        Button("Play") {
                            showPlayer = true
                        }
                        .disabled(playback == nil)

                        Button("Comments") {
                            showComments = true
                        }
                        .disabled(metadata.commentsKey == nil)

                        Button(autoplayUpNextEnabled ? "Autoplay On" : "Autoplay Off") {
                            autoplayUpNextEnabled.toggle()
                        }
                    }

                    if let playback {
                        Text(playbackDetails(playback))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    if !relatedItems.isEmpty {
                        Text("Up Next")
                            .font(.title3)
                            .bold()
                        ForEach(relatedItems.prefix(12)) { item in
                            NavigationLink {
                                VideoDetailScreen(videoId: item.videoId, queueContext: relatedItems)
                            } label: {
                                VideoRowView(item: item)
                            }
                            .buttonStyle(.plain)
                        }

                        if let token = relatedContinuationToken {
                            Button(isLoadingRelated ? "Loading..." : "More Up Next") {
                                Task { await loadRelated(continuationToken: token) }
                            }
                            .disabled(isLoadingRelated)
                        }
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
                    VStack(alignment: .leading, spacing: 10) {
                        Text(errorMessage)
                            .foregroundStyle(.red)
                            .font(.footnote)
                        Button("Retry") {
                            Task { await loadData() }
                        }
                        .disabled(isLoading)
                    }
                }
            }
            .padding(40)
        }
        .navigationTitle("Video")
        .navigationDestination(item: $autoNavigateRoute) { route in
            VideoDetailScreen(videoId: route.id, queueContext: queueContext)
        }
        .task {
            await loadData()
        }
        .fullScreenCover(isPresented: $showPlayer) {
            if let playback {
                PlayerScreen(
                    initialVideoId: videoId,
                    initialMetadata: metadata,
                    initialPlayback: playback,
                    queue: playbackQueue,
                    autoplayEnabled: autoplayUpNextEnabled,
                    onAutoplayChange: { autoplayUpNextEnabled = $0 },
                    onNavigateToVideo: { nextVideoId in
                        showPlayer = false
                        autoNavigateRoute = VideoRoute(id: nextVideoId)
                    }
                )
                .environmentObject(appState)
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

            let loadedMetadata = try await metadataTask
            let loadedPlayback = try await playbackTask
            metadata = loadedMetadata
            playback = loadedPlayback
            await loadRelated(continuationToken: nil)

            if !didAutoPresentPlayer, playback != nil {
                didAutoPresentPlayer = true
                showPlayer = true
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadRelated(continuationToken: String?) async {
        isLoadingRelated = true
        defer { isLoadingRelated = false }

        do {
            let response = try await appState.api.fetchRelated(videoId: videoId, continuationToken: continuationToken)
            if continuationToken == nil {
                relatedItems = response.items
            } else {
                relatedItems.append(contentsOf: response.items)
            }
            relatedContinuationToken = response.continuationToken
        } catch {
            if continuationToken == nil {
                relatedItems = []
            }
            relatedContinuationToken = nil
        }
    }

    private var playbackQueue: [PlaybackQueueItem] {
        if let queueContext, !queueContext.isEmpty {
            var queue: [PlaybackQueueItem] = []
            for item in queueContext {
                guard !queue.contains(where: { $0.videoId == item.videoId }) else { continue }
                queue.append(
                    PlaybackQueueItem(
                        videoId: item.videoId,
                        title: item.title,
                        channelName: item.channelName,
                        thumbnailUrl: item.thumbnailUrl
                    )
                )
            }
            if !queue.contains(where: { $0.videoId == videoId }) {
                let primaryTitle = metadata?.title ?? "Video \(videoId)"
                let primaryChannel = metadata?.channelName ?? ""
                queue.insert(
                    PlaybackQueueItem(
                        videoId: videoId,
                        title: primaryTitle,
                        channelName: primaryChannel,
                        thumbnailUrl: "https://i.ytimg.com/vi/\(videoId)/hqdefault.jpg"
                    ),
                    at: 0
                )
            }
            return queue
        }

        var queue: [PlaybackQueueItem] = []
        let primaryTitle = metadata?.title ?? "Video \(videoId)"
        let primaryChannel = metadata?.channelName ?? ""
        queue.append(
            PlaybackQueueItem(
                videoId: videoId,
                title: primaryTitle,
                channelName: primaryChannel,
                thumbnailUrl: "https://i.ytimg.com/vi/\(videoId)/hqdefault.jpg"
            )
        )

        for item in relatedItems {
            guard item.videoId != videoId else { continue }
            guard !queue.contains(where: { $0.videoId == item.videoId }) else { continue }
            queue.append(
                PlaybackQueueItem(
                    videoId: item.videoId,
                    title: item.title,
                    channelName: item.channelName,
                    thumbnailUrl: item.thumbnailUrl
                )
            )
        }

        return queue
    }

    private func playbackDetails(_ playback: PlaybackResponse) -> String {
        let quality = playback.qualityLabel ?? "auto"
        if playback.isAdaptive == true {
            return "Playback: adaptive (\(quality))"
        }
        return "Playback: fixed stream (\(quality))"
    }
}

private struct VideoRoute: Identifiable, Hashable {
    let id: String
}

private struct PlaybackQueueItem: Identifiable, Hashable {
    let videoId: String
    let title: String
    let channelName: String
    let thumbnailUrl: String

    var id: String { videoId }
}

struct ChannelVideosScreen: View {
    let channelId: String
    let channelName: String
    @EnvironmentObject private var appState: AppState
    @State private var items: [VideoFeedItem] = []
    @State private var continuationToken: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            List(items) { item in
                NavigationLink {
                    VideoDetailScreen(videoId: item.videoId, queueContext: items)
                } label: {
                    VideoRowView(item: item)
                }
            }

            if let continuationToken {
                Button(isLoading ? "Loading..." : "Load More") {
                    Task { await loadPage(continuation: continuationToken) }
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
                        Task { await refresh() }
                    }
                    .disabled(isLoading)
                }
            }
        }
        .navigationTitle(channelName)
        .task {
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
            let response = try await appState.api.fetchChannelVideos(channelId: channelId, continuationToken: continuation)
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

private struct PlayerScreen: View {
    let initialVideoId: String
    let initialMetadata: VideoMetadataResponse?
    let initialPlayback: PlaybackResponse
    let queue: [PlaybackQueueItem]
    let autoplayEnabled: Bool
    let onAutoplayChange: (Bool) -> Void
    let onNavigateToVideo: (String) -> Void
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer
    @State private var currentVideoId: String
    @State private var currentTitle: String
    @State private var currentChannelName: String
    @State private var currentThumbnailURL: String
    @State private var availableStreams: [PlaybackStreamOption]
    @State private var subtitleTracks: [SubtitleTrack]
    @State private var selectedStreamID: String?
    @State private var selectedSubtitleID: String?
    @State private var resumePositionByVideoId: [String: Double] = [:]
    @State private var playbackRate = 1.0
    @State private var autoplay: Bool
    @State private var showSettings = false
    @State private var isLoadingNext = false
    @State private var playerError: String?
    @State private var showOverlay = true
    @State private var overlayHideTask: Task<Void, Never>?

    init(
        initialVideoId: String,
        initialMetadata: VideoMetadataResponse?,
        initialPlayback: PlaybackResponse,
        queue: [PlaybackQueueItem],
        autoplayEnabled: Bool,
        onAutoplayChange: @escaping (Bool) -> Void,
        onNavigateToVideo: @escaping (String) -> Void
    ) {
        self.initialVideoId = initialVideoId
        self.initialMetadata = initialMetadata
        self.initialPlayback = initialPlayback
        self.queue = queue
        self.autoplayEnabled = autoplayEnabled
        self.onAutoplayChange = onAutoplayChange
        self.onNavigateToVideo = onNavigateToVideo

        let initialURL = URL(string: initialPlayback.streamUrl) ?? URL(string: "https://example.com")!
        _player = State(initialValue: AVPlayer(url: initialURL))
        _currentVideoId = State(initialValue: initialVideoId)
        _currentTitle = State(initialValue: initialMetadata?.title ?? "Video \(initialVideoId)")
        _currentChannelName = State(initialValue: initialMetadata?.channelName ?? "")
        _currentThumbnailURL = State(initialValue: "https://i.ytimg.com/vi/\(initialVideoId)/hqdefault.jpg")
        _availableStreams = State(initialValue: initialPlayback.availableStreams ?? [])
        _subtitleTracks = State(initialValue: initialPlayback.subtitleTracks ?? [])
        _selectedStreamID = State(initialValue: initialPlayback.availableStreams?.first?.id)
        _selectedSubtitleID = State(initialValue: nil)
        _autoplay = State(initialValue: autoplayEnabled)
        _resumePositionByVideoId = State(initialValue: [:])
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            VideoPlayer(player: player)
                .ignoresSafeArea()

            if showOverlay {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top, spacing: 20) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(currentTitle)
                                .font(.title3.bold())
                                .lineLimit(2)
                            if !currentChannelName.isEmpty {
                                Text(currentChannelName)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            if let next = nextQueueItem {
                                Text("Up next: \(next.title)")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }

                        Spacer()

                        Button("Options") {
                            showSettings = true
                            revealOverlay()
                        }
                    }

                    if isLoadingNext {
                        ProgressView("Loading Up Next...")
                            .padding(.top, 8)
                    }

                    if let playerError {
                        Text(playerError)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }

                    if !autoplay, let next = nextQueueItem {
                        Button("Play Next: \(next.title)") {
                            Task { await playNext() }
                            revealOverlay()
                        }
                    }

                    Spacer()
                }
                .padding(40)
                .transition(.opacity)
            }
        }
        .onAppear {
            applyResumePosition(for: currentVideoId)
            player.play()
            revealOverlay()
        }
        .onDisappear {
            saveWatchProgressSnapshot()
            player.pause()
            overlayHideTask?.cancel()
            if currentVideoId != initialVideoId {
                onNavigateToVideo(currentVideoId)
            }
        }
        .onPlayPauseCommand {
            togglePlayPause()
            revealOverlay()
        }
        .onMoveCommand { _ in
            revealOverlay()
        }
        .onExitCommand {
            dismiss()
        }
        .onTapGesture {
            revealOverlay()
        }
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime)) { notification in
            guard let item = notification.object as? AVPlayerItem else { return }
            guard item == player.currentItem else { return }
            Task { await handlePlaybackFinished() }
        }
        .task(id: currentVideoId) {
            await progressPersistenceLoop(for: currentVideoId)
        }
        .sheet(isPresented: $showSettings) {
            PlayerSettingsPanel(
                autoplay: $autoplay,
                availableStreams: availableStreams,
                selectedStreamID: $selectedStreamID,
                subtitleTracks: subtitleTracks,
                selectedSubtitleID: $selectedSubtitleID,
                playbackRate: playbackRate,
                onSelectRate: { rate in
                    playbackRate = rate
                    if player.timeControlStatus == .playing {
                        player.playImmediately(atRate: Float(playbackRate))
                    }
                },
                onSelectStream: { stream in
                    switchStream(to: stream)
                }
            )
            .onDisappear {
                onAutoplayChange(autoplay)
                revealOverlay()
            }
        }
    }

    private var nextQueueItem: PlaybackQueueItem? {
        guard !queue.isEmpty else { return nil }
        let currentIndex = queue.firstIndex(where: { $0.videoId == currentVideoId }) ?? 0
        let nextIndex = currentIndex + 1
        guard nextIndex < queue.count else { return nil }
        return queue[nextIndex]
    }

    private func togglePlayPause() {
        if player.timeControlStatus == .playing {
            player.pause()
        } else {
            player.playImmediately(atRate: Float(playbackRate))
        }
    }

    private func handlePlaybackFinished() async {
        saveWatchProgressSnapshot()
        guard autoplay else { return }
        await playNext()
    }

    private func playNext() async {
        guard let next = nextQueueItem else { return }
        isLoadingNext = true
        defer { isLoadingNext = false }
        do {
            let nextPlayback = try await appState.api.fetchPlayback(videoId: next.videoId)
            let nextMetadata = try? await appState.api.fetchMetadata(videoId: next.videoId)
            guard let url = URL(string: nextPlayback.streamUrl) else {
                throw CompanionAPIError.invalidURL
            }

            let item = AVPlayerItem(url: url)
            player.replaceCurrentItem(with: item)
            player.playImmediately(atRate: Float(playbackRate))

            currentVideoId = next.videoId
            applyResumePosition(for: next.videoId)
            currentTitle = nextMetadata?.title ?? next.title
            currentChannelName = nextMetadata?.channelName ?? next.channelName
            currentThumbnailURL = next.thumbnailUrl
            availableStreams = nextPlayback.availableStreams ?? []
            subtitleTracks = nextPlayback.subtitleTracks ?? []
            selectedStreamID = availableStreams.first?.id
            selectedSubtitleID = nil
            playerError = nil
            showOverlay = true
            overlayHideTask?.cancel()
            overlayHideTask = Task { @MainActor in
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                withAnimation(.easeOut(duration: 0.2)) {
                    showOverlay = false
                }
            }
        } catch {
            playerError = error.localizedDescription
        }
    }

    private func revealOverlay() {
        showOverlay = true
        overlayHideTask?.cancel()
        overlayHideTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            withAnimation(.easeOut(duration: 0.2)) {
                showOverlay = false
            }
        }
    }

    private func switchStream(to stream: PlaybackStreamOption) {
        guard let url = URL(string: stream.streamUrl) else {
            playerError = CompanionAPIError.invalidURL.localizedDescription
            return
        }

        let currentTime = player.currentTime()
        let wasPlaying = player.timeControlStatus == .playing
        let item = AVPlayerItem(url: url)
        player.replaceCurrentItem(with: item)
        player.seek(to: currentTime, toleranceBefore: .zero, toleranceAfter: .zero)
        selectedStreamID = stream.id
        playerError = nil
        if wasPlaying {
            player.playImmediately(atRate: Float(playbackRate))
        }
    }

    private func progressPersistenceLoop(for videoID: String) async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            guard videoID == currentVideoId else { return }
            saveWatchProgressSnapshot()
        }
    }

    private func applyResumePosition(for videoId: String) {
        let cached = resumePositionByVideoId[videoId] ?? 0
        let persisted = appState.continueWatchingEntry(for: videoId)?.lastPositionSec ?? 0
        let position = max(cached, persisted)
        guard position > 5 else { return }
        let time = CMTime(seconds: position, preferredTimescale: 600)
        player.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero)
    }

    private func saveWatchProgressSnapshot() {
        let position = player.currentTime().seconds
        let duration = player.currentItem?.duration.seconds ?? 0
        guard position.isFinite, duration.isFinite else { return }
        resumePositionByVideoId[currentVideoId] = position
        appState.recordWatchProgress(
            videoId: currentVideoId,
            title: currentTitle,
            channelName: currentChannelName,
            thumbnailUrl: currentThumbnailURL,
            positionSec: position,
            durationSec: duration
        )
    }
}

private struct PlayerSettingsPanel: View {
    @Environment(\.dismiss) private var dismiss

    @Binding var autoplay: Bool
    let availableStreams: [PlaybackStreamOption]
    @Binding var selectedStreamID: String?
    let subtitleTracks: [SubtitleTrack]
    @Binding var selectedSubtitleID: String?
    let playbackRate: Double
    let onSelectRate: (Double) -> Void
    let onSelectStream: (PlaybackStreamOption) -> Void

    private let speedOptions: [Double] = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

    var body: some View {
        NavigationStack {
            List {
                Color.clear
                    .frame(height: 10)
                    .listRowBackground(Color.clear)
                    .listRowInsets(.init(top: 0, leading: 0, bottom: 0, trailing: 0))

                settingsSection("Autoplay") {
                    FocusableSettingsRowButton {
                        autoplay.toggle()
                    } label: {
                        Text(autoplay ? "Turn Autoplay Off" : "Turn Autoplay On")
                            .font(.headline)
                    }
                }

                settingsSection("Playback Speed") {
                    ForEach(speedOptions, id: \.self) { speed in
                        FocusableSettingsRowButton {
                            onSelectRate(speed)
                        } label: {
                            HStack {
                                Text("\(speed, specifier: "%.2gx")")
                                Spacer()
                                if speed == playbackRate {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                }

                settingsSection("Quality") {
                    if availableStreams.isEmpty {
                        Text("No alternate streams available")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .listRowBackground(Color.clear)
                    } else {
                        ForEach(availableStreams) { stream in
                            FocusableSettingsRowButton {
                                onSelectStream(stream)
                                selectedStreamID = stream.id
                            } label: {
                                HStack {
                                    Text(streamLabel(stream))
                                    Spacer()
                                    if selectedStreamID == stream.id {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                            .listRowBackground(Color.clear)
                        }
                    }
                }

                settingsSection("Captions") {
                    FocusableSettingsRowButton {
                        selectedSubtitleID = nil
                    } label: {
                        HStack {
                            Text("Off")
                            Spacer()
                            if selectedSubtitleID == nil {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                    .listRowBackground(Color.clear)

                    if subtitleTracks.isEmpty {
                        Text("No captions exposed for this stream")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .listRowBackground(Color.clear)
                    } else {
                        ForEach(subtitleTracks) { track in
                            FocusableSettingsRowButton {
                                selectedSubtitleID = track.id
                            } label: {
                                HStack {
                                    Text(track.label)
                                    if track.isAutoGenerated {
                                        Text("(Auto)")
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if selectedSubtitleID == track.id {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                            .listRowBackground(Color.clear)
                        }
                    }
                }

                Color.clear
                    .frame(height: 14)
                    .listRowBackground(Color.clear)
                    .listRowInsets(.init(top: 0, leading: 0, bottom: 0, trailing: 0))
            }
            .listStyle(.plain)
                        .background(Color.black.opacity(0.94).ignoresSafeArea())
            .navigationTitle("Playback Options")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }

    private func streamLabel(_ stream: PlaybackStreamOption) -> String {
        let mode = stream.isAdaptive ? "adaptive" : "fixed"
        return "\(stream.qualityLabel) (\(mode))"
    }

    @ViewBuilder
    private func settingsSection<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                content()
            }
        } header: {
            Text(title)
                .font(.title3.bold())
                .foregroundStyle(.white.opacity(0.9))
        }
        .textCase(nil)
        .listRowBackground(Color.clear)
    }
}

private struct FocusableSettingsRowButton<Label: View>: View {
    private let action: () -> Void
    private let label: () -> Label

    @Environment(\.isFocused) private var isFocused

    init(action: @escaping () -> Void, @ViewBuilder label: @escaping () -> Label) {
        self.action = action
        self.label = label
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                label()
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(isFocused ? Color.white.opacity(0.94) : Color.white.opacity(0.08))
            )
            .foregroundStyle(isFocused ? Color.black : Color.white)
        }
        .buttonStyle(.plain)
    }
}
