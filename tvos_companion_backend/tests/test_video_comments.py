from __future__ import annotations


def test_video_metadata_includes_description_and_comments_key(app_client):
    response = app_client.get("/v1/video/v_demo_001/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["videoId"] == "v_demo_001"
    assert payload["title"]
    assert payload["description"]
    assert payload["commentsKey"]
    assert payload["liveChatKey"] is None


def test_video_metadata_handles_no_comments_case(app_client):
    response = app_client.get("/v1/video/v_demo_010/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["videoId"] == "v_demo_010"
    assert payload["commentsKey"] is None


def test_playback_payload_shape(app_client):
    response = app_client.get("/v1/video/v_demo_001/playback")
    assert response.status_code == 200
    payload = response.json()
    assert payload["videoId"] == "v_demo_001"
    assert payload["streamUrl"].startswith("https://")
    assert payload["mimeType"]
    assert payload["expiresAtEpochSec"] > 0


def test_comments_pagination_and_replies(app_client):
    metadata = app_client.get("/v1/video/v_demo_001/metadata")
    key = metadata.json()["commentsKey"]

    first = app_client.get("/v1/comments", params={"commentsKey": key})
    assert first.status_code == 200
    payload1 = first.json()
    assert len(payload1["items"]) == 2

    first_item = payload1["items"][0]
    assert first_item["authorName"]
    assert first_item["message"]

    nested_key = first_item["nestedCommentsKey"]
    assert nested_key is not None

    replies = app_client.get("/v1/comments/replies", params={"nestedCommentsKey": nested_key})
    assert replies.status_code == 200
    replies_payload = replies.json()
    assert replies_payload["items"]

    next_key = payload1["nextCommentsKey"]
    assert next_key is not None
    second = app_client.get("/v1/comments", params={"commentsKey": next_key})
    assert second.status_code == 200
    payload2 = second.json()
    assert payload2["items"]


def test_invalid_comments_key_is_rejected(app_client):
    response = app_client.get("/v1/comments", params={"commentsKey": "not-a-real-key"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_COMMENTS_KEY"
