import SwiftUI

struct VideoRowView: View {
    let item: VideoFeedItem

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            thumbnail

            VStack(alignment: .leading, spacing: 8) {
                Text(item.title)
                    .font(.headline)
                    .lineLimit(2)

                Text("\(item.channelName) • \(item.publishedText)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Text(durationText(item.durationSec))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private var thumbnail: some View {
        Group {
            if let thumbnailURL {
                AsyncImage(url: thumbnailURL) { phase in
                    switch phase {
                    case let .success(image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        placeholder(symbol: "photo")
                    case .empty:
                        placeholder(symbol: "photo.fill")
                    @unknown default:
                        placeholder(symbol: "photo")
                    }
                }
            } else {
                placeholder(symbol: "photo")
            }
        }
        .frame(width: 320, height: 180)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func placeholder(symbol: String) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.gray.opacity(0.25))
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(.white.opacity(0.8))
        }
    }

    private func durationText(_ totalSeconds: Int) -> String {
        guard totalSeconds > 0 else {
            return ""
        }
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60

        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%d:%02d", minutes, seconds)
    }

    private var thumbnailURL: URL? {
        let raw = item.thumbnailUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        if !raw.isEmpty, let parsed = URL(string: raw) {
            return parsed
        }
        return URL(string: "https://i.ytimg.com/vi/\(item.videoId)/hqdefault.jpg")
    }
}
