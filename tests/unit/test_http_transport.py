"""Unit tests for the Streamable HTTP transport."""

import json

from starlette.testclient import TestClient

from mcp_kanka.__main__ import build_http_app

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _json_from_sse(body: str) -> dict:
    """Pull the JSON-RPC message out of an SSE response body."""
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :])
    return json.loads(body)


def test_healthz_answers_ok():
    """Test the liveness probe used by the container healthcheck."""
    with TestClient(build_http_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.text == "ok"


def test_initialize_over_http():
    """Test that an MCP client can initialize a session on /mcp."""
    with TestClient(build_http_app()) as client:
        response = client.post("/mcp", headers=MCP_HEADERS, json=INITIALIZE)

    assert response.status_code == 200
    message = _json_from_sse(response.text)
    assert message["result"]["serverInfo"]["name"] == "mcp-kanka"


def test_tools_are_listed_over_http():
    """Test that the same tools as over stdio are served on /mcp."""
    with TestClient(build_http_app()) as client:
        response = client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 200
    names = {tool["name"] for tool in _json_from_sse(response.text)["result"]["tools"]}
    assert {"find_entities", "create_relations", "create_members"} <= names


def test_allowed_hosts_rejects_other_hosts(monkeypatch):
    """Test that MCP_ALLOWED_HOSTS turns on Host header validation."""
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp-kanka.example.org")

    with TestClient(build_http_app()) as client:
        rejected = client.post(
            "/mcp",
            headers={**MCP_HEADERS, "Host": "evil.example.com"},
            json=INITIALIZE,
        )
        accepted = client.post(
            "/mcp",
            headers={**MCP_HEADERS, "Host": "mcp-kanka.example.org"},
            json=INITIALIZE,
        )

    assert rejected.status_code >= 400
    assert accepted.status_code == 200


def _tools_list(client, headers=None):
    """POST a tools/list request to /mcp."""
    return client.post(
        "/mcp",
        headers={**MCP_HEADERS, **(headers or {})},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )


def test_no_token_configured_keeps_mcp_open(monkeypatch):
    """Test that without MCP_AUTH_TOKEN nothing changes."""
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    with TestClient(build_http_app()) as client:
        assert _tools_list(client).status_code == 200


def test_token_required_when_configured(monkeypatch):
    """Test that a configured token turns away requests without it."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "s3cret")

    with TestClient(build_http_app()) as client:
        missing = _tools_list(client)
        wrong = _tools_list(client, {"Authorization": "Bearer nope"})
        not_bearer = _tools_list(client, {"Authorization": "s3cret"})
        right = _tools_list(client, {"Authorization": "Bearer s3cret"})

    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert wrong.status_code == 401
    assert not_bearer.status_code == 401
    assert right.status_code == 200


def test_healthz_stays_open_with_a_token(monkeypatch):
    """Test that the container healthcheck keeps working behind the token."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "s3cret")

    with TestClient(build_http_app()) as client:
        assert client.get("/healthz").status_code == 200
