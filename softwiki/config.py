import os

def load_env():
    """Loads environment variables from .env file if it exists."""
    possible_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        # Remove quotes if present
                        if val.startswith('"') and val.endswith('"'):
                            val = val[1:-1]
                        elif val.startswith("'") and val.endswith("'"):
                            val = val[1:-1]
                        if key and key not in os.environ:
                            os.environ[key] = val
            break

# Automatically load environment variables on import
load_env()

def get_workspace_dir() -> str:
    """Returns the active workspace directory, defaulting to 'workspace/default'."""
    return os.path.abspath(os.getenv("WORKSPACE_DIR", "workspace/default"))

def get_db_url() -> str:
    """Returns the SQLite database URL inside .softwiki/."""
    db_path = os.path.join(get_workspace_dir(), ".softwiki", "processed.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"

def get_config_path(filename: str) -> str:
    """Returns the config file path inside config/."""
    path = os.path.join(get_workspace_dir(), "config", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def get_index_path(filename: str) -> str:
    """Returns the search index file path inside .softwiki/index/."""
    path = os.path.join(get_workspace_dir(), ".softwiki", "index", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def get_export_dir(subdir: str) -> str:
    """Returns the export directory inside the workspace, ensuring it exists."""
    path = os.path.join(get_workspace_dir(), "exports", subdir)
    os.makedirs(path, exist_ok=True)
    return path

def get_raw_dir(subdir: str) -> str:
    """Returns the raw data directory inside the workspace, ensuring it exists."""
    path = os.path.join(get_workspace_dir(), "raw", subdir)
    os.makedirs(path, exist_ok=True)
    return path

def get_softwiki_dir(subdir: str) -> str:
    """Returns a path inside .softwiki/, ensuring it exists."""
    path = os.path.join(get_workspace_dir(), ".softwiki", subdir)
    os.makedirs(path, exist_ok=True)
    return path

def get_processed_dir(subdir: str) -> str:
    """Returns a path inside .softwiki/ (pipeline artifacts)."""
    return get_softwiki_dir(subdir)

def load_merged_agent_soul() -> str:
    """Loads default agent soul and appends workspace-specific soul if it exists."""
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    default_soul_path = os.path.join(templates_dir, "agent_soul.md")
    
    soul_content = ""
    if os.path.exists(default_soul_path):
        with open(default_soul_path, "r", encoding="utf-8") as f:
            soul_content = f.read()
            
    # Check workspace override
    ws_soul_path = os.path.join(get_workspace_dir(), "config", "agents.md")
    if not os.path.exists(ws_soul_path):
        ws_soul_path = os.path.join(get_workspace_dir(), "config", "agent_soul.md")
        
    if os.path.exists(ws_soul_path):
        with open(ws_soul_path, "r", encoding="utf-8") as f:
            soul_content += "\n\n" + f.read()
            
    return soul_content

def load_merged_workflows() -> dict:
    """Loads default workflows and merges workspace-specific workflow overrides."""
    import yaml
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    default_wf_path = os.path.join(templates_dir, "workflows.yaml")
    
    workflows = {"workflows": {}}
    if os.path.exists(default_wf_path):
        with open(default_wf_path, "r", encoding="utf-8") as f:
            try:
                workflows = yaml.safe_load(f) or {"workflows": {}}
            except Exception as e:
                print(f"Error loading default workflows: {e}")
                
    # Check workspace override
    ws_wf_path = os.path.join(get_workspace_dir(), "config", "workflows.yaml")
    if os.path.exists(ws_wf_path):
        with open(ws_wf_path, "r", encoding="utf-8") as f:
            try:
                ws_workflows = yaml.safe_load(f) or {}
                # Merge workflows dict
                if "workflows" in ws_workflows:
                    workflows["workflows"].update(ws_workflows["workflows"])
            except Exception as e:
                print(f"Error loading workspace workflows: {e}")
                
    return workflows

def is_module_enabled(module_name: str) -> bool:
    """Checks if a knowledge module (rag, graph, claimdb, timeline, llmwiki) is enabled."""
    enabled_str = os.getenv("ENABLED_MODULES", "rag,graph,claimdb,timeline,llmwiki")
    enabled_list = [m.strip().lower() for m in enabled_str.split(",") if m.strip()]
    return module_name.strip().lower() in enabled_list

def get_session_id() -> str:
    """Returns the active session ID, generating a random one if in user mode and not set."""
    session_id = os.getenv("SOFTWIKI_SESSION_ID")
    if not session_id and os.getenv("SOFTWIKI_MODE") in ["wiki-study", "wiki-work", "wiki-user", "study", "work", "user"]:
        import secrets
        import string
        rand_str = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        session_id = f"session-{rand_str}"
        os.environ["SOFTWIKI_SESSION_ID"] = session_id
    return session_id or "default"



