from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MockVideo:
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    thumbnail_url: str
    published_text: str
    duration_sec: int
    description: str
    view_count_text: str


def _video(idx: int, title: str, channel: str, channel_id: str, published: str, duration: int, description: str, views: str) -> MockVideo:
    video_id = f"v_demo_{idx:03d}"
    return MockVideo(
        video_id=video_id,
        title=title,
        channel_name=channel,
        channel_id=channel_id,
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_text=published,
        duration_sec=duration,
        description=description,
        view_count_text=views,
    )


VIDEOS: list[MockVideo] = [
    _video(1, "tvOS Companion Intro", "SmartTube Labs", "chan_st_1", "2 hours ago", 602, "Walkthrough of the local companion architecture and why profile switching matters on tvOS.", "12K views"),
    _video(2, "Build a Leanback-Style Grid in SwiftUI", "Living Room UI", "chan_st_2", "1 day ago", 987, "How to structure browse surfaces for remote-first navigation.", "30K views"),
    _video(3, "Device Code OAuth Explained", "Auth Deep Dive", "chan_st_3", "3 days ago", 721, "An implementation-focused look at Google OAuth device flow.", "18K views"),
    _video(4, "Handling Long Video Descriptions", "Player Patterns", "chan_st_4", "1 week ago", 560, "Techniques for rendering long plain-text descriptions without layout jitter.", "8.2K views"),
    _video(5, "Comments Pagination Strategy", "API Design", "chan_st_5", "1 week ago", 835, "Designing comments and replies APIs with stable continuation keys.", "9.4K views"),
    _video(6, "Profile Switching UX Review", "Product Decisions", "chan_st_6", "2 weeks ago", 410, "Trade-offs in handling multiple Google accounts in a living-room app.", "5.6K views"),
    _video(7, "State Persistence on Apple TV", "Persistence Lab", "chan_st_7", "2 weeks ago", 675, "Persisting auth/account state and restoring context after cold start.", "4.1K views"),
    _video(8, "AVPlayer Playback Basics", "Playback Core", "chan_st_8", "3 weeks ago", 730, "Configuring stream playback from companion-provided URLs.", "22K views"),
    _video(9, "Search Ranking for TV", "Discoverability", "chan_st_9", "1 month ago", 903, "Balancing relevance and recency in a low-typing environment.", "14K views"),
    _video(10, "Subscriptions Feed QA", "Quality Engineering", "chan_st_10", "1 month ago", 512, "Regression checks for authenticated subscriptions surfaces.", "7.3K views"),
    _video(11, "History Feed Recovery", "Reliability Notes", "chan_st_11", "1 month ago", 456, "Fallback approaches when upstream history APIs are restricted.", "3.9K views"),
    _video(12, "Shipping a Local-Only tvOS App", "Indie Builds", "chan_st_12", "2 months ago", 1040, "Practical checklist for local signing and sideload testing.", "11K views"),
]


VIDEO_BY_ID: dict[str, MockVideo] = {video.video_id: video for video in VIDEOS}


ACCOUNTS: list[dict[str, Any]] = [
    {
        "id": "acc_123",
        "name": "John",
        "email": "john@example.com",
        "avatarUrl": "https://example.com/avatar-john.png",
    },
    {
        "id": "acc_456",
        "name": "Brand",
        "email": "brand@example.com",
        "avatarUrl": "https://example.com/avatar-brand.png",
    },
]


HOME_FEED_ANON = [
    "v_demo_001",
    "v_demo_002",
    "v_demo_003",
    "v_demo_008",
    "v_demo_009",
    "v_demo_012",
]


HOME_FEED_SIGNED_IN = {
    "acc_123": [
        "v_demo_001",
        "v_demo_003",
        "v_demo_004",
        "v_demo_006",
        "v_demo_008",
        "v_demo_010",
    ],
    "acc_456": [
        "v_demo_002",
        "v_demo_005",
        "v_demo_007",
        "v_demo_009",
        "v_demo_011",
        "v_demo_012",
    ],
}

MUSIC_FEED_ANON = [
    "v_demo_008",
    "v_demo_009",
    "v_demo_012",
    "v_demo_003",
    "v_demo_002",
    "v_demo_006",
]

MUSIC_FEED_SIGNED_IN = {
    "acc_123": [
        "v_demo_008",
        "v_demo_003",
        "v_demo_002",
        "v_demo_010",
        "v_demo_009",
        "v_demo_006",
    ],
    "acc_456": [
        "v_demo_009",
        "v_demo_012",
        "v_demo_007",
        "v_demo_005",
        "v_demo_002",
        "v_demo_008",
    ],
}


SUBSCRIPTIONS_FEED = {
    "acc_123": [
        "v_demo_002",
        "v_demo_004",
        "v_demo_005",
        "v_demo_008",
        "v_demo_010",
        "v_demo_012",
    ],
    "acc_456": [
        "v_demo_001",
        "v_demo_003",
        "v_demo_006",
        "v_demo_007",
        "v_demo_009",
        "v_demo_011",
    ],
}


HISTORY_FEED = {
    "acc_123": [
        "v_demo_011",
        "v_demo_010",
        "v_demo_009",
        "v_demo_003",
        "v_demo_001",
    ],
    "acc_456": [
        "v_demo_012",
        "v_demo_008",
        "v_demo_006",
        "v_demo_004",
        "v_demo_002",
    ],
}


COMMENTS_BY_VIDEO_ID: dict[str, list[dict[str, Any]]] = {
    "v_demo_001": [
        {
            "id": "c_1001",
            "authorName": "Alex",
            "authorPhotoUrl": "https://example.com/u-alex.png",
            "publishedText": "1 day ago",
            "message": "This architecture split makes the port manageable.",
            "likeCountText": "31",
            "replyCountText": "2",
            "replies": [
                {
                    "id": "r_1001_1",
                    "authorName": "Chris",
                    "authorPhotoUrl": "https://example.com/u-chris.png",
                    "publishedText": "22 hours ago",
                    "message": "Agreed. Provider abstraction is the key here.",
                    "likeCountText": "8",
                    "replyCountText": "0",
                },
                {
                    "id": "r_1001_2",
                    "authorName": "Sam",
                    "authorPhotoUrl": "https://example.com/u-sam.png",
                    "publishedText": "20 hours ago",
                    "message": "Would love a write-up on test strategy too.",
                    "likeCountText": "4",
                    "replyCountText": "0",
                },
            ],
        },
        {
            "id": "c_1002",
            "authorName": "Morgan",
            "authorPhotoUrl": "https://example.com/u-morgan.png",
            "publishedText": "2 days ago",
            "message": "Profile switching parity was the blocker for us too.",
            "likeCountText": "18",
            "replyCountText": "0",
            "replies": [],
        },
        {
            "id": "c_1003",
            "authorName": "Taylor",
            "authorPhotoUrl": "https://example.com/u-taylor.png",
            "publishedText": "3 days ago",
            "message": "Plain-text descriptions are enough for a first release.",
            "likeCountText": "11",
            "replyCountText": "1",
            "replies": [
                {
                    "id": "r_1003_1",
                    "authorName": "Jordan",
                    "authorPhotoUrl": "https://example.com/u-jordan.png",
                    "publishedText": "2 days ago",
                    "message": "Link parsing can wait for v1.1.",
                    "likeCountText": "5",
                    "replyCountText": "0",
                }
            ],
        },
        {
            "id": "c_1004",
            "authorName": "Riley",
            "authorPhotoUrl": "https://example.com/u-riley.png",
            "publishedText": "4 days ago",
            "message": "Can this be run fully on LAN without cloud services?",
            "likeCountText": "9",
            "replyCountText": "0",
            "replies": [],
        },
    ],
    "v_demo_002": [
        {
            "id": "c_2001",
            "authorName": "Dana",
            "authorPhotoUrl": "https://example.com/u-dana.png",
            "publishedText": "1 week ago",
            "message": "The focus navigation examples are really helpful.",
            "likeCountText": "6",
            "replyCountText": "0",
            "replies": [],
        }
    ],
    "v_demo_010": [],
}


PLAYBACK_DEFAULT = {
    "streamUrl": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "mimeType": "video/mp4",
}


def feed_item(video_id: str) -> dict[str, Any]:
    video = VIDEO_BY_ID[video_id]
    return {
        "videoId": video.video_id,
        "title": video.title,
        "channelName": video.channel_name,
        "channelId": video.channel_id,
        "thumbnailUrl": video.thumbnail_url,
        "publishedText": video.published_text,
        "durationSec": video.duration_sec,
    }


def metadata(video_id: str) -> dict[str, Any]:
    video = VIDEO_BY_ID[video_id]
    return {
        "videoId": video.video_id,
        "title": video.title,
        "channelName": video.channel_name,
        "channelId": video.channel_id,
        "publishedText": video.published_text,
        "viewCountText": video.view_count_text,
        "description": video.description,
    }
