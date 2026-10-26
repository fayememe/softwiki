import yaml


def _write_topics(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    data = {
        "topics": {
            "ip": {"name": "IP 产品", "kind": "category", "children": ["cpu"]},
            "cpu": {"name": "CPU", "kind": "category", "parent": "ip", "children": ["cortex-m55"]},
            "cortex-m55": {
                "name": "Cortex-M55", "kind": "page", "parent": "cpu",
                "category": "IP 产品", "subcategory": "CPU",
                "aliases": ["cortex-m55*", "cm55"],
            },
            "protocols": {"name": "协议", "kind": "category", "children": ["amba"]},
            "amba": {
                "name": "AMBA", "kind": "page", "parent": "protocols",
                "category": "协议", "subcategory": "AMBA", "nav": True,
                "aliases": ["apb-*", "axi-*"],
            },
            "__ignore__": {"kind": "ignore", "aliases": ["warranty*", "copyright*"]},
        }
    }
    (ws / "config" / "topics.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    return ws


def test_topic_helpers(tmp_path, monkeypatch):
    _write_topics(tmp_path, monkeypatch)
    from softwiki.wiki.interventions import topic_aliases, topic_group, topic_name
    assert topic_group("cortex-m55") == "IP 产品"
    assert topic_group("amba") == "协议"
    assert topic_name("cortex-m55") == "Cortex-M55"
    assert "cortex-m55*" in topic_aliases("cortex-m55")


def test_coverage_pattern_map(tmp_path, monkeypatch):
    _write_topics(tmp_path, monkeypatch)
    from softwiki.wiki.coverage import _topic_map
    aliases, patterns, ignored, canonical = _topic_map()
    assert aliases["cm55"] == "cortex-m55"
    assert ("apb-*", "amba") in patterns
    assert "warranty*" in ignored
    assert canonical == {"cortex-m55", "amba"}
