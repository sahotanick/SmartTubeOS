from __future__ import annotations


def _signin(client) -> str:
    start = client.post("/v1/auth/start")
    assert start.status_code == 200
    client.get("/v1/auth/poll")
    done = client.get("/v1/auth/poll")
    assert done.status_code == 200
    payload = done.json()
    assert payload["status"] == "SIGNED_IN"
    return payload["selectedAccountId"]


def test_subscriptions_and_history_require_auth(app_client):
    subscriptions = app_client.get("/v1/feed/subscriptions")
    assert subscriptions.status_code == 401
    assert subscriptions.json()["error"]["code"] == "AUTH_REQUIRED"

    history = app_client.get("/v1/feed/history")
    assert history.status_code == 401
    assert history.json()["error"]["code"] == "AUTH_REQUIRED"


def test_home_feed_pagination_and_continuation(app_client):
    first = app_client.get("/v1/feed/home")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["title"] == "Home"
    assert len(first_payload["items"]) == 4
    assert first_payload["continuationToken"]

    second = app_client.get("/v1/feed/home", params={"continuationToken": first_payload["continuationToken"]})
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["items"]


def test_music_feed_pagination_and_continuation(app_client):
    first = app_client.get("/v1/feed/music")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["title"] == "Music"
    assert first_payload["items"]

    continuation = first_payload["continuationToken"]
    if continuation:
        second = app_client.get("/v1/feed/music", params={"continuationToken": continuation})
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["items"]


def test_account_switch_updates_feed_context(app_client):
    first_account = _signin(app_client)

    subscriptions_a = app_client.get("/v1/feed/subscriptions")
    assert subscriptions_a.status_code == 200
    items_a = subscriptions_a.json()["items"]
    assert items_a

    second_account = "acc_456" if first_account == "acc_123" else "acc_123"
    select = app_client.post("/v1/accounts/select", json={"accountId": second_account})
    assert select.status_code == 200

    subscriptions_b = app_client.get("/v1/feed/subscriptions")
    assert subscriptions_b.status_code == 200
    items_b = subscriptions_b.json()["items"]
    assert items_b
    assert items_a[0]["videoId"] != items_b[0]["videoId"]


def test_search_and_search_continuation(app_client):
    response = app_client.get("/v1/search", params={"q": "tvOS"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"].startswith("Search:")
    assert payload["items"]

    continuation = payload["continuationToken"]
    if continuation:
        next_page = app_client.get("/v1/search", params={"q": "tvOS", "continuationToken": continuation})
        assert next_page.status_code == 200


def test_search_rejects_invalid_continuation(app_client):
    response = app_client.get("/v1/search", params={"q": "tvOS", "continuationToken": "bad-token"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CONTINUATION"


def test_related_channel_and_suggestions_endpoints(app_client):
    related = app_client.get("/v1/video/v_demo_001/related")
    assert related.status_code == 200
    related_payload = related.json()
    assert related_payload["title"] == "Up Next"
    assert related_payload["items"]
    assert all(row["videoId"] != "v_demo_001" for row in related_payload["items"])

    channel_id = related_payload["items"][0]["channelId"]
    channel_videos = app_client.get(f"/v1/channel/{channel_id}/videos")
    assert channel_videos.status_code == 200
    channel_payload = channel_videos.json()
    assert channel_payload["items"]
    assert all(row["channelId"] == channel_id for row in channel_payload["items"])

    suggestions = app_client.get("/v1/search/suggestions", params={"q": "tv"})
    assert suggestions.status_code == 200
    suggestion_payload = suggestions.json()
    assert suggestion_payload["query"] == "tv"
    assert suggestion_payload["suggestions"]


def test_recommendation_feedback_not_interested_filters_home(app_client):
    initial = app_client.get("/v1/feed/home")
    assert initial.status_code == 200
    initial_items = initial.json()["items"]
    assert initial_items
    target = initial_items[0]

    feedback = app_client.post(
        "/v1/recommendations/feedback",
        json={
            "videoId": target["videoId"],
            "channelId": target["channelId"],
            "action": "NOT_INTERESTED",
        },
    )
    assert feedback.status_code == 200
    feedback_payload = feedback.json()
    assert feedback_payload["status"] == "OK"
    assert feedback_payload["action"] == "NOT_INTERESTED"

    updated = app_client.get("/v1/feed/home")
    assert updated.status_code == 200
    updated_items = updated.json()["items"]
    assert all(row["videoId"] != target["videoId"] for row in updated_items)


def test_recommendation_feedback_block_channel_filters_home(app_client):
    initial = app_client.get("/v1/feed/home")
    assert initial.status_code == 200
    initial_items = initial.json()["items"]
    assert initial_items
    channel_id = initial_items[0]["channelId"]
    assert channel_id

    feedback = app_client.post(
        "/v1/recommendations/feedback",
        json={
            "videoId": initial_items[0]["videoId"],
            "channelId": channel_id,
            "action": "DONT_RECOMMEND_CHANNEL",
        },
    )
    assert feedback.status_code == 200
    feedback_payload = feedback.json()
    assert feedback_payload["status"] == "OK"
    assert feedback_payload["action"] == "DONT_RECOMMEND_CHANNEL"

    updated = app_client.get("/v1/feed/home")
    assert updated.status_code == 200
    updated_items = updated.json()["items"]
    assert all(row["channelId"] != channel_id for row in updated_items)
