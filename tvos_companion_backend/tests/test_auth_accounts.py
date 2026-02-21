from __future__ import annotations


def test_session_defaults_signed_out(app_client):
    response = app_client.get("/v1/session")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"signedIn": False, "selectedAccountId": None}


def test_auth_start_poll_signin_and_signout(app_client):
    start = app_client.post("/v1/auth/start")
    assert start.status_code == 200
    start_payload = start.json()
    assert start_payload["status"] == "PENDING"
    assert start_payload["signInCode"]
    assert start_payload["verificationUrl"].startswith("https://")
    assert start_payload["verificationUrlComplete"].startswith("https://")
    assert start_payload["signInCode"] in start_payload["verificationUrlComplete"]

    poll1 = app_client.get("/v1/auth/poll")
    assert poll1.status_code == 200
    assert poll1.json() == {"status": "PENDING"}

    poll2 = app_client.get("/v1/auth/poll")
    assert poll2.status_code == 200
    signed_payload = poll2.json()
    assert signed_payload["status"] == "SIGNED_IN"
    assert signed_payload["selectedAccountId"] in {"acc_123", "acc_456"}

    session = app_client.get("/v1/session")
    assert session.status_code == 200
    assert session.json()["signedIn"] is True

    signout = app_client.post("/v1/auth/signout")
    assert signout.status_code == 200
    assert signout.json() == {"status": "SIGNED_OUT"}

    session_after = app_client.get("/v1/session")
    assert session_after.status_code == 200
    assert session_after.json() == {"signedIn": False, "selectedAccountId": None}


def test_accounts_list_and_select(app_client):
    accounts = app_client.get("/v1/accounts")
    assert accounts.status_code == 200
    payload = accounts.json()
    assert payload["selectedAccountId"] is None
    assert len(payload["accounts"]) >= 2
    assert all("selected" in row for row in payload["accounts"])

    select = app_client.post("/v1/accounts/select", json={"accountId": "acc_123"})
    assert select.status_code == 200
    assert select.json() == {"selectedAccountId": "acc_123"}

    accounts_after = app_client.get("/v1/accounts")
    assert accounts_after.status_code == 200
    selected_rows = [row for row in accounts_after.json()["accounts"] if row["selected"]]
    assert len(selected_rows) == 1
    assert selected_rows[0]["id"] == "acc_123"


def test_select_unknown_account_returns_404(app_client):
    response = app_client.post("/v1/accounts/select", json={"accountId": "acc_missing"})
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_remove_account_updates_selection(app_client):
    select = app_client.post("/v1/accounts/select", json={"accountId": "acc_123"})
    assert select.status_code == 200
    assert select.json() == {"selectedAccountId": "acc_123"}

    remove = app_client.post("/v1/accounts/remove", json={"accountId": "acc_123"})
    assert remove.status_code == 200
    assert remove.json()["selectedAccountId"] == "acc_456"

    accounts_after = app_client.get("/v1/accounts")
    assert accounts_after.status_code == 200
    payload = accounts_after.json()
    ids = {row["id"] for row in payload["accounts"]}
    assert "acc_123" not in ids
    assert payload["selectedAccountId"] == "acc_456"


def test_remove_unknown_account_returns_404(app_client):
    response = app_client.post("/v1/accounts/remove", json={"accountId": "acc_missing"})
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_refresh_accounts_returns_profile_counts(app_client):
    app_client.post("/v1/accounts/select", json={"accountId": "acc_123"})
    response = app_client.post("/v1/accounts/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REFRESHED"
    assert payload["selectedAccountId"] == "acc_123"
    assert payload["discoveredProfileCount"] >= 2
    assert payload["totalProfileCount"] >= 2
