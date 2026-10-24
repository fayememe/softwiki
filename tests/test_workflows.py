from softwiki.intelligence.workflows import get_workflow, load_workflows, render_workflow


def test_default_workflows():
    workflows = load_workflows()
    assert "research" in workflows
    assert "academic-analysis" in workflows


def test_render_academic_workflow():
    text = render_workflow(get_workflow("academic-analysis"))
    assert "Decompose" in text
    assert "chronology" in text


def test_workspace_override(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    config = tmp_path / "ws" / "config"
    config.mkdir(parents=True)
    (config / "workflows.yaml").write_text(
        "workflows:\n  custom:\n    name: Custom\n    steps:\n      1: Do it\n",
        encoding="utf-8",
    )
    workflows = load_workflows()
    assert "custom" in workflows
    assert "research" in workflows
