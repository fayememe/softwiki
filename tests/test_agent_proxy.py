from softwiki.api.server import (
    _agent_answer_text,
    _agent_final_message,
    _agent_sources,
    _agent_tool_parts,
)


def test_agent_sources_parse_and_dedup():
    output = (
        "[0.032] Untitled Document: [Document: Untitled Document | Source: Manual Import | "
        "Date: 2026-10-23 | Pages: 9-10] RTC Base +0xFD0 ...\n"
        "[0.016] ARM PrimeCell RTC: [Document: ARM PrimeCell RTC | Source: ARM | "
        "Date: 2026-10-23 | Pages: 12] Register Memory Map ...\n"
        "[0.016] ARM PrimeCell RTC: [Document: ARM PrimeCell RTC | Source: ARM | "
        "Date: 2026-10-23 | Pages: 12] duplicate\n"
    )
    tools = [{"name": "softwiki_search", "output": output}]
    sources = _agent_sources(tools)
    assert len(sources) == 2
    assert sources[0]["title"] == "Untitled Document"
    assert sources[0]["page_start"] == 9
    assert sources[0]["page_end"] == 10
    assert sources[1]["title"] == "ARM PrimeCell RTC"
    assert sources[1]["page_start"] == 12
    assert sources[1]["page_end"] == 12
    assert sources[1]["citation_num"] == 2


def test_agent_sources_prefer_answer_references():
    tools = [{"name": "softwiki_search", "output": (
        "[0.032] Untitled Document: [Document: Untitled Document | Source: Manual Import | "
        "Date: 2026-10-23 | Pages: 9-10] text"
    )}]
    answer = "See [4] (ARM PrimeCell RTC, p. 23) and [1] (Untitled Document, pp. 9-10)."
    sources = _agent_sources(tools, answer)
    assert [s["citation_num"] for s in sources] == [4, 1]
    assert sources[0]["title"] == "ARM PrimeCell RTC"
    assert sources[0]["page_start"] == 23
    assert sources[1]["page_start"] == 9


def test_agent_tool_parts_and_final_message():
    messages = [
        {"info": {"role": "assistant", "finish": "tool-calls"},
         "parts": [{"type": "tool", "tool": "softwiki_search",
                    "state": {"status": "completed", "input": {"query": "PL031"},
                              "output": "No results found."}}]},
        {"info": {"role": "assistant", "finish": "stop", "id": "msg_final"},
         "parts": [{"type": "text", "text": "Answer with [1]."}]},
    ]
    final = _agent_final_message(messages, 0)
    assert final is not None
    assert final["info"]["id"] == "msg_final"
    assert _agent_answer_text(final) == "Answer with [1]."
    tools = _agent_tool_parts(messages)
    assert tools[0]["name"] == "softwiki_search"
    assert tools[0]["status"] == "completed"
    assert tools[0]["input"]["query"] == "PL031"


def test_agent_ask_proxy(monkeypatch):
    from fastapi.testclient import TestClient
    import softwiki.api.server as server

    calls = []

    def fake_request(method, path, payload=None, timeout=60):
        calls.append((method, path, payload))
        if method == "POST" and path == "/session":
            return {"id": "ses_test"}
        if method == "GET" and path == "/session/ses_test/message":
            if any(c[0] == "POST" and c[1] == "/session/ses_test/message" for c in calls):
                return [
                    {"info": {"role": "user", "id": "u1"}, "parts": [{"type": "text", "text": "q"}]},
                    {"info": {"role": "assistant", "id": "a1", "finish": "tool-calls"},
                     "parts": [{"type": "tool", "tool": "softwiki_search",
                                "state": {"status": "completed", "input": {"query": "PL031"},
                                          "output": "[0.5] RTC: [Document: RTC | Source: ARM | Date: 2026 | Pages: 9-10] text"}}]},
                    {"info": {"role": "assistant", "id": "a2", "finish": "stop"},
                     "parts": [{"type": "text", "text": "PL031 has RTCDR [1]."}]},
                ]
            return []
        if method == "POST" and path == "/session/ses_test/message":
            return {"info": {"role": "assistant", "id": "a1"}, "parts": []}
        raise AssertionError((method, path))

    monkeypatch.setattr(server, "_agent_request", fake_request)
    client = TestClient(server.app)
    resp = client.post("/api/agent/ask", json={"question": "PL031?", "session_id": "ses_test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "PL031 has RTCDR [1]."
    assert data["session_id"] == "ses_test"
    assert data["sources"][0]["title"] == "RTC"
    assert data["tools"][0]["name"] == "softwiki_search"


def test_agent_sources_parse_reference_lines():
    answer = (
        "Some answer.\n\n### Sources\n\n"
        "[1] ARM PrimeCell Real Time Clock (PL031) Technical Reference Manual, "
        "2017-05-23, pp. 3-6, 23\n"
        "[6] ARM PrimeCell Real Time Clock (PL031) Technical Reference Manual, "
        "2017-05-23, p. 23\n"
    )
    sources = _agent_sources([], answer)
    assert [s["citation_num"] for s in sources] == [1, 6]
    assert sources[0]["page_start"] == 3
    assert sources[0]["page_end"] == 6
    assert sources[1]["page_start"] == 23
    assert sources[1]["page_end"] == 23


def test_agent_sources_dedup_inline_and_line_refs():
    answer = (
        "Answer.\n\n[1] (Untitled Document, Manual Import, 2026-10-23, pp. 9-10)\n"
        "Sources:\n[1] (Untitled Document, pp. 9-10)\n"
    )
    sources = _agent_sources([], answer)
    assert len(sources) == 1
    assert sources[0]["citation_num"] == 1
    assert sources[0]["title"] == "Untitled Document"
    assert sources[0]["page_start"] == 9


def test_agent_sources_singular_page():
    tools = [{"name": "softwiki_search", "output": (
        "[0.5] ARM PrimeCell RTC: [Document: ARM PrimeCell RTC | Source: ARM | "
        "Date: 2017-05-23 | Page: 23] text"
    )}]
    sources = _agent_sources(tools)
    assert len(sources) == 1
    assert sources[0]["page_start"] == 23
    assert sources[0]["page_end"] == 23


def test_agent_sources_enrich_from_kb(monkeypatch):
    import softwiki.api.server as server
    monkeypatch.setattr(server, "_lookup_doc_meta", lambda title, start, end: {
        "title": title,
        "source_name": "ARM",
        "published_at": "2023-02-06",
        "url": None,
        "text": "excerpt",
    })
    answer = "See [1] (Power Control System Architecture, pp. 137-138)."
    sources = server._agent_sources([], answer)
    assert len(sources) == 1
    assert sources[0]["source_name"] == "ARM"
    assert sources[0]["published_at"] == "2023-02-06"
    assert sources[0]["text"] == "excerpt"
    assert sources[0]["score"] is None
