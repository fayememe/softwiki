import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import softwiki.api.server as server


def test_agent_event_session_id_variants():
    assert server._agent_event_session_id(
        {"type": "message.part.updated", "properties": {"part": {"sessionID": "ses_a"}}}
    ) == "ses_a"
    assert server._agent_event_session_id(
        {"type": "message.updated", "properties": {"info": {"sessionID": "ses_b"}}}
    ) == "ses_b"
    assert server._agent_event_session_id(
        {"type": "permission.asked", "properties": {"sessionID": "ses_c"}}
    ) == "ses_c"
    assert server._agent_event_session_id({"type": "server.connected", "properties": {}}) is None


def test_agent_event_allowed_filters_other_sessions():
    assert server._agent_event_allowed({"properties": {}}, "ses_x")
    assert server._agent_event_allowed({"properties": {"sessionID": "ses_x"}}, "ses_x")
    assert not server._agent_event_allowed({"properties": {"sessionID": "ses_y"}}, "ses_x")
    assert server._agent_event_allowed({"properties": {"sessionID": "ses_y"}}, None)


def test_agent_event_urls_fallback():
    original = server.AGENT_EVENT_PATH
    try:
        server.AGENT_EVENT_PATH = "/global/event"
        assert server._agent_event_urls() == [
            f"{server.AGENT_WEB_URL}/global/event",
            f"{server.AGENT_WEB_URL}/event",
        ]
        server.AGENT_EVENT_PATH = "/event"
        assert server._agent_event_urls() == [f"{server.AGENT_WEB_URL}/event"]
    finally:
        server.AGENT_EVENT_PATH = original


def test_agent_stream_reemits_and_heartbeats(monkeypatch):
    async def fake_pump(session_id, queue, stop):
        await queue.put('{"type":"server.connected","properties":{}}')
        await queue.put('{"type":"message.part.updated","properties":{"sessionID":"ses_x"}}')
        await queue.put(None)

    monkeypatch.setattr(server, "_agent_pump_events", fake_pump)
    monkeypatch.setattr(server, "AGENT_EVENT_HEARTBEAT", 0.01)
    client = TestClient(server.app)
    with client.stream("GET", "/api/agent/events?session_id=ses_x") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert 'data: {"type":"server.connected"' in body
    assert 'data: {"type":"message.part.updated"' in body


def test_agent_stream_cancel_closes_pump(monkeypatch):
    stopped = asyncio.Event()

    async def slow_pump(session_id, queue, stop):
        try:
            await asyncio.sleep(30)
        finally:
            stopped.set()

    monkeypatch.setattr(server, "_agent_pump_events", slow_pump)
    monkeypatch.setattr(server, "AGENT_EVENT_HEARTBEAT", 0.01)

    async def consume():
        stream = server._agent_event_stream("ses_x")
        first = await asyncio.wait_for(stream.__anext__(), timeout=2)
        await stream.aclose()
        return first

    first = asyncio.run(consume())
    assert first.startswith(": ping")
    assert stopped.is_set()


def test_agent_sessions_sorted(monkeypatch):
    def fake_request(method, path, payload=None, timeout=60):
        assert (method, path) == ("GET", "/session")
        return [
            {"id": "ses_old", "title": "Old", "time": {"created": 1, "updated": 10}},
            {"id": "ses_new", "title": "New", "time": {"created": 2, "updated": 20}},
            {"id": "ses_child", "title": "Child", "parentID": "ses_old", "time": {"created": 3}},
        ]

    monkeypatch.setattr(server, "_agent_request", fake_request)
    client = TestClient(server.app)
    data = client.get("/api/agent/sessions").json()
    assert [s["id"] for s in data["sessions"]] == ["ses_new", "ses_old", "ses_child"]
    assert data["sessions"][2]["parent_id"] == "ses_old"


def test_agent_messages_proxy(monkeypatch):
    def fake_request(method, path, payload=None, timeout=60):
        assert (method, path) == ("GET", "/session/ses_x/message")
        return [{"info": {"id": "m1", "sessionID": "ses_x"}, "parts": [{"type": "text", "text": "hi"}]}]

    monkeypatch.setattr(server, "_agent_request", fake_request)
    client = TestClient(server.app)
    data = client.get("/api/agent/session/ses_x/messages").json()
    assert data["session_id"] == "ses_x"
    assert data["messages"][0]["parts"][0]["text"] == "hi"


def test_agent_prompt_uses_prompt_async(monkeypatch):
    calls = []

    def fake_request(method, path, payload=None, timeout=60):
        calls.append((method, path, payload))
        return {"status": "accepted"}

    monkeypatch.setattr(server, "_agent_request", fake_request)
    client = TestClient(server.app)
    resp = client.post("/api/agent/prompt", json={"question": "PL031?", "session_id": "ses_x"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted", "session_id": "ses_x"}
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/session/ses_x/prompt_async")
    assert payload["agent"] == server.AGENT_DEFAULT
    assert payload["parts"] == [{"type": "text", "text": "PL031?"}]


def test_agent_prompt_surfaces_unsupported(monkeypatch):
    def fake_request(method, path, payload=None, timeout=60):
        raise HTTPException(status_code=502, detail="HTTP 404")

    monkeypatch.setattr(server, "_agent_request", fake_request)
    client = TestClient(server.app)
    resp = client.post("/api/agent/prompt", json={"question": "q", "session_id": "ses_x"})
    assert resp.status_code == 502
    assert "prompt_async" in resp.json()["detail"]
