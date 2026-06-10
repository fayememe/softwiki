import os
import shutil
from softwiki.config import (
    get_workspace_dir,
    load_merged_agent_soul,
    load_merged_workflows
)

def test_config_cascade():
    # Setup a temporary workspace
    temp_ws = "data/test_config_cascade_ws"
    os.makedirs(os.path.join(temp_ws, "config"), exist_ok=True)
    os.environ["WORKSPACE_DIR"] = temp_ws
    
    try:
        # Load default agent soul
        default_soul = load_merged_agent_soul()
        assert "Softwiki Lead Analyst" in default_soul
        
        # Write custom agent soul
        custom_soul_text = "Custom domain-independent analysis instructions."
        with open(os.path.join(temp_ws, "config", "agent_soul.md"), "w", encoding="utf-8") as f:
            f.write(custom_soul_text)
            
        merged_soul = load_merged_agent_soul()
        assert "Softwiki Lead Analyst" in merged_soul
        assert custom_soul_text in merged_soul
        
        # Load default workflows
        default_wf = load_merged_workflows()
        assert "research" in default_wf["workflows"]
        
        # Override a workflow
        custom_wf_yaml = """
workflows:
  research:
    name: "Custom Research Workflow"
    description: "Domain specific research process."
    steps:
      1: "Custom search step."
"""
        with open(os.path.join(temp_ws, "config", "workflows.yaml"), "w", encoding="utf-8") as f:
            f.write(custom_wf_yaml)
            
        merged_wf = load_merged_workflows()
        assert "research" in merged_wf["workflows"]
        assert merged_wf["workflows"]["research"]["name"] == "Custom Research Workflow"
        assert merged_wf["workflows"]["research"]["steps"][1] == "Custom search step."
        # Verify that other non-overridden workflows like wiki-compile are still there
        assert "wiki-compile" in merged_wf["workflows"]
        
    finally:
        if os.path.exists(temp_ws):
            shutil.rmtree(temp_ws)
        del os.environ["WORKSPACE_DIR"]
