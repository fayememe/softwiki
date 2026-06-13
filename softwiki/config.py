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

# Runtime module overrides (takes precedence over env var)
_runtime_enabled_modules = None

def set_enabled_modules(modules: list):
    """Override enabled modules at runtime."""
    global _runtime_enabled_modules
    _runtime_enabled_modules = [m.strip().lower() for m in modules]

def get_enabled_modules(workspace_dir: Optional[str] = None) -> list:
    """Return enabled module list from workspace override, global runtime, or env var."""
    ws_dir = workspace_dir or get_workspace_dir()
    ws_modules_path = os.path.join(ws_dir, ".softwiki", "modules.json")
    if os.path.exists(ws_modules_path):
        try:
            with open(ws_modules_path, "r") as f:
                import json
                data = json.load(f)
                if isinstance(data, list):
                    return [m.strip().lower() for m in data]
        except Exception:
            pass
    if _runtime_enabled_modules is not None:
        return _runtime_enabled_modules
    enabled_str = os.getenv("ENABLED_MODULES", "rag,graph,claimdb,timeline,llmwiki")
    return [m.strip().lower() for m in enabled_str.split(",") if m.strip()]

def set_workspace_modules(modules: Optional[list] = None):
    """Override modules for the current workspace (stored in .softwiki/modules.json).
    Pass None to clear the workspace override and fall back to global defaults."""
    ws_dir = get_workspace_dir()
    ws_modules_path = os.path.join(ws_dir, ".softwiki", "modules.json")
    if modules is None:
        if os.path.exists(ws_modules_path):
            os.remove(ws_modules_path)
        return
    os.makedirs(os.path.dirname(ws_modules_path), exist_ok=True)
    import json
    with open(ws_modules_path, "w") as f:
        json.dump([m.strip().lower() for m in modules], f)

def is_module_enabled(module_name: str) -> bool:
    """Checks if a knowledge module (rag, graph, claimdb, timeline, llmwiki) is enabled."""
    return module_name.strip().lower() in get_enabled_modules()

def set_workspace_dir(path: str):
    """Switch the active workspace at runtime by setting WORKSPACE_DIR env var."""
    os.environ["WORKSPACE_DIR"] = os.path.abspath(path)

def list_workspaces() -> list:
    """Scan the workspace/ directory for available workspaces."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workspace")
    base = os.path.abspath(base)
    if not os.path.isdir(base):
        return []
    candidates = []
    for name in sorted(os.listdir(base)):
        ws_dir = os.path.join(base, name)
        softwiki_dir = os.path.join(ws_dir, ".softwiki")
        if os.path.isdir(ws_dir) and os.path.isdir(softwiki_dir):
            candidates.append(name)
    return candidates

# ── Configuration resolution ──
# Priority: CLI args > env vars > config file > defaults

CONFIG_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"),
    os.path.expanduser("~/.config/softwiki/config.yaml"),
    os.path.join(os.getcwd(), "config.yaml"),
]

_config_cache = None

def _load_config() -> dict:
    """Load config from the first existing config file."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    import yaml
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    _config_cache = yaml.safe_load(f) or {}
                print(f"[config] Loaded from {path}")
                return _config_cache
            except Exception as e:
                print(f"[config] Error loading {path}: {e}")
    _config_cache = {}
    return _config_cache

def get_setting(key: str, default=None):
    """Resolve a setting: env var > config file > default.
    Env var name: SOFTWIKI_{key.upper()} or just {key.upper()} for common ones.
    """
    # Try env var first
    env_key = f"SOFTWIKI_{key.upper()}"
    env_val = os.getenv(env_key) or os.getenv(key.upper())
    if env_val is not None:
        # Try to cast to int if default is int
        if isinstance(default, int):
            try:
                return int(env_val)
            except ValueError:
                pass
        return env_val
    # Try config file
    cfg = _load_config()
    if key in cfg:
        return cfg[key]
    return default

def get_api_port() -> int:
    return int(get_setting("api_port", 6200))

def get_mcp_port() -> int:
    return int(get_setting("mcp_port", 6100))

def get_host() -> str:
    return get_setting("host", "0.0.0.0")

def get_web_port() -> int:
    return int(get_setting("web_port", 6108))

def reload_config():
    """Force reload config file on next read."""
    global _config_cache
    _config_cache = None

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



