import os
import shutil

import pytest
import yaml


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    (ws / "config" / "topics.yaml").write_text(yaml.safe_dump({
        "topics": {
            "cortex-m55": {"name": "Cortex-M55", "group": "IP 产品"},
            "amba-axi": {"name": "AMBA AXI", "group": "协议"},
        }
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    yield str(ws)


def test_save_compose_delete_interventions(workspace):
    from softwiki.wiki import interventions

    g = interventions.save_intervention("global", "先给结论，再给证据。", priority=10)
    grp = interventions.save_intervention("group:IP 产品", "寄存器章节用表格。", priority=20)
    top = interventions.save_intervention("topic:amba-axi", "握手章节用状态表。", priority=30)

    composed = interventions.compose_interventions(
        "cortex-m55", adhoc="这次只测试布局。", include_saved=True
    )
    assert "[GLOBAL]" in composed
    assert "[GROUP: IP 产品]" in composed
    assert "[TOPIC: cortex-m55]" not in composed
    assert "[TOPIC: amba-axi]" not in composed
    assert "[AD-HOC PREVIEW]" in composed
    assert composed.index("先给结论") < composed.index("寄存器章节") < composed.index("这次只测试布局")

    # Topic scope only applies to its topic.
    axi = interventions.compose_interventions("amba-axi", include_saved=True)
    assert "[GROUP: 协议]" not in axi
    assert "[TOPIC: amba-axi]" in axi

    assert interventions.delete_intervention(top["id"]) is True
    assert all(x["id"] != top["id"] for x in interventions.list_interventions())
    assert g["id"] != grp["id"]


def test_compose_without_interventions_is_empty(workspace):
    from softwiki.wiki import interventions
    assert interventions.compose_interventions("cortex-m55", include_saved=True) == ""


def test_preview_endpoint_does_not_touch_canonical(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    import softwiki.api.server as server
    import softwiki.wiki.page_generator as pg

    def fake_generate(self, db, topic, force_rebuild=False, intervention="", output_dir=None):
        self.last_model = "fake-model"
        self.last_fallback = False
        self.last_intervention = intervention
        assert output_dir and "wiki/preview" in output_dir
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{topic}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Fake\n\n## Summary\nLine [1]\n")
        return path

    monkeypatch.setattr(pg.WikiPageGenerator, "generate_topic_page", fake_generate)
    client = TestClient(server.app)
    r = client.post("/api/wiki/preview", json={
        "topics": ["cortex-m55"],
        "intervention": "先给结论。",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["content"].startswith("# Fake")
    assert data["results"][0]["model"] == "fake-model"
    assert data["results"][0]["citation_count"] == 1
    canonical = os.path.join(workspace, "exports", "wiki", "topics", "cortex-m55.md")
    assert not os.path.exists(canonical)

    r = client.post("/api/wiki/preview", json={"topics": ["a", "b", "c", "d"]})
    assert r.status_code == 400


def test_intervention_api(workspace):
    from fastapi.testclient import TestClient
    import softwiki.api.server as server
    client = TestClient(server.app)
    r = client.post("/api/wiki/interventions", json={
        "scope": "global", "text": "All pages must start with a conclusion."
    })
    assert r.status_code == 200
    iid = r.json()["intervention"]["id"]
    r = client.get("/api/wiki/interventions")
    assert any(x["id"] == iid for x in r.json()["interventions"])
    r = client.delete(f"/api/wiki/interventions/{iid}")
    assert r.status_code == 200
