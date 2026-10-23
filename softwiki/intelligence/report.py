import hashlib
import json
import os
import time

import yaml

from softwiki.config import get_config_path, get_export_dir, get_workspace_dir
from softwiki.intelligence.answer_engine import AnswerEngine


def _template_path(template_id):
    workspace_path = get_config_path(os.path.join("analysis", f"{template_id}.yaml"))
    if os.path.exists(workspace_path):
        return workspace_path
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "templates",
        "analysis",
        f"{template_id}.yaml",
    )


def load_template(template_id):
    path = _template_path(template_id)
    if not os.path.exists(path):
        raise ValueError(f"Unknown report template: {template_id}")
    with open(path, encoding="utf-8") as f:
        template = yaml.safe_load(f) or {}
    if not template.get("sections"):
        raise ValueError(f"Template {template_id} has no sections")
    return template


def generate_report(db, question, template_id="research-report"):
    template = load_template(template_id)
    answer = AnswerEngine().ask(db, question)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    digest = hashlib.sha256(f"{question}\n{answer}".encode()).hexdigest()[:12]
    report_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{digest}"
    report_dir = os.path.join(get_export_dir("reports"), report_id)
    os.makedirs(report_dir, exist_ok=True)

    sections = template["sections"]
    lines = [f"# {template.get('title', template_id)}", ""]
    lines.append(f"**Question:** {question}")
    lines.append(f"**Workspace:** {os.path.basename(get_workspace_dir())}")
    lines.append(f"**Template:** {template_id}")
    lines.append(f"**Generated:** {created_at}")
    lines.append("")

    for index, section in enumerate(sections):
        lines.append(f"## {section['title']}")
        lines.append("")
        if index == 0:
            lines.append(answer.strip())
        elif section["id"] == "sources":
            lines.append("Citations are included in the answer above.")
        elif section["id"] == "limitations":
            lines.append(
                "Trial report: structured extraction covers the first 15k characters "
                "of each document; retrieval covers the full indexed text."
            )
        else:
            lines.append("Not separately generated in this trial report.")
        lines.append("")

    report_path = os.path.join(report_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    manifest = {
        "report_id": report_id,
        "question": question,
        "template": template_id,
        "workspace": os.path.basename(get_workspace_dir()),
        "created_at": created_at,
        "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
        "sections": [s["id"] for s in sections],
        "report_path": report_path,
    }
    manifest_path = os.path.join(report_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return {
        "status": "success",
        "report_id": report_id,
        "report_path": report_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }
