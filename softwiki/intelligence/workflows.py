import os

import yaml

from softwiki.config import get_config_path

_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates", "workflows.yaml"
)


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_workflows():
    data = _load(_TEMPLATE)
    workspace_path = get_config_path("workflows.yaml")
    if os.path.exists(workspace_path):
        override = _load(workspace_path).get("workflows", {})
        data.setdefault("workflows", {}).update(override)
    return data.get("workflows", {})


def get_workflow(workflow_id):
    return load_workflows().get(workflow_id)


def render_workflow(workflow):
    lines = [f"Workflow: {workflow.get('name', '')}"]
    description = workflow.get("description")
    if description:
        lines.append(description)
    for number, step in workflow.get("steps", {}).items():
        lines.append(f"{number}. {step}")
    return "\n".join(lines)
