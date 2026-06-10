import os
import sys
import json
import shutil
import subprocess

# ─── Zero-dependency helpers (replaces softwiki.config) ──────────────────────

def _ws_dir() -> str:
    """Active workspace directory from env, defaulting to workspace/default."""
    return os.path.abspath(os.getenv("WORKSPACE_DIR", "workspace/default"))

def _project_root() -> str:
    """Absolute path to the softwiki project root."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _python_bin(root: str) -> str:
    """Return the venv python, falling back to current interpreter."""
    for p in (os.path.join(root, "venv", "bin", "python"),
              os.path.join(root, "venv", "bin", "python3")):
        if os.path.exists(p):
            return p
    return sys.executable

def _read_file(path: str, fallback: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return fallback

def _load_yaml(path: str) -> dict:
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def _get_agent_soul(ws: str, root: str) -> str:
    """Load base agent_soul.md from templates, merge workspace override if present."""
    templates_dir = os.path.join(root, "softwiki", "templates")
    soul = _read_file(os.path.join(templates_dir, "agent_soul.md"))
    for override in (os.path.join(ws, "config", "agents.md"),
                     os.path.join(ws, "config", "agent_soul.md")):
        extra = _read_file(override)
        if extra:
            soul += "\n\n" + extra
            break
    return soul

def _get_workflows(ws: str, root: str) -> dict:
    """Load default workflows.yaml, merge workspace override if present."""
    templates_dir = os.path.join(root, "softwiki", "templates")
    wf = _load_yaml(os.path.join(templates_dir, "workflows.yaml"))
    if not wf:
        wf = {"workflows": {}}
    ws_wf = _load_yaml(os.path.join(ws, "config", "workflows.yaml"))
    if "workflows" in ws_wf:
        wf.setdefault("workflows", {}).update(ws_wf["workflows"])
    return wf

# ─── MCP client (stdio JSON-RPC) ─────────────────────────────────────────────

def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Call a SoftWiki MCP tool over stdio JSON-RPC without importing softwiki."""
    root = _project_root()
    ws   = _ws_dir()
    mode = os.getenv("SOFTWIKI_MODE", "wiki-admin")

    cmd = [_python_bin(root), "-m", "softwiki.mcp.server"]
    env = os.environ.copy()
    env.update({"WORKSPACE_DIR": ws, "SOFTWIKI_MODE": mode, "PYTHONPATH": root})

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=env, cwd=root
    )

    def _send(msg: dict) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    def _recv_by_id(target_id: int, max_lines: int = 40) -> dict:
        for _ in range(max_lines):
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode())
                if msg.get("id") == target_id:
                    return msg
            except json.JSONDecodeError:
                continue
        return {}

    try:
        _send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "softwiki-shell", "version": "0.1"}
        }})
        _recv_by_id(1)
        _send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": tool_name, "arguments": arguments}})
        resp = _recv_by_id(2)
        if "result" in resp:
            parts = resp["result"].get("content", [])
            return "\n".join(p["text"] for p in parts if p.get("type") == "text")
        if "error" in resp:
            return f"Error: {resp['error'].get('message', 'Unknown')}"
        return "No response from MCP server."
    except Exception as e:
        return f"MCP call failed: {e}"
    finally:
        try:
            proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


# ─── ANSI color helpers ───────────────────────────────────────────────────────
def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape code (no-op if not a TTY)."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def _bold(t):   return _c("1", t)
def _dim(t):    return _c("2", t)
def _blue(t):   return _c("38;5;75", t)
def _cyan(t):   return _c("38;5;87", t)
def _violet(t): return _c("38;5;135", t)
def _green(t):  return _c("38;5;84", t)
def _gray(t):   return _c("38;5;240", t)

# Coder Mini font (patorjk.com) — same half-block character set as opencode
LOGO_LINES = [
    r"             ▄▄",
    r"             ██   ██           ▀▀  ▄▄     ▀▀",
    r"▄█▀▀▀ ▄███▄ ▀██▀ ▀██▀▀ ██   ██ ██  ██ ▄█▀ ██",
    r"▀███▄ ██ ██  ██   ██   ██ █ ██ ██  ████   ██",
    r"▄▄▄█▀ ▀███▀  ██   ██    ██▀██  ██▄ ██ ▀█▄ ██▄",
]

_LOGO_WIDTH = max(len(l) for l in LOGO_LINES)

def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def _print_banner(ws: str, model: str, workflows: dict):
    """Render the Softwiki startup banner to stdout."""
    W = shutil.get_terminal_size((100, 30)).columns

    # Clear screen
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")

    # ── Build all content lines first so we can measure block width ──────────
    tagline = "Research Intelligence Shell"
    sub     = "powered by softwiki-opencode"

    ws_name   = os.path.basename(os.path.abspath(ws))
    mode_name = os.getenv("SOFTWIKI_MODE", "wiki-admin").upper()
    wf_names  = list(workflows.get("workflows", {}).keys())
    wf_str    = "  ".join(_violet(f"/{w}") for w in wf_names) if wf_names else _gray("(none)")

    LABEL_W = 14
    session_name = os.getenv("SOFTWIKI_SESSION_SUFFIX", "null")

    info_items = [
        ("Workspace", ws_name,                _blue),
        ("IDE Mode",  mode_name,              _blue),
        ("Session",   session_name,           _blue),
        ("Model",     model,                  _blue),
        ("Workflows", wf_str,                 _blue),
        ("MCP",       _green("softwiki") + _dim("  ingest · index · search · wiki_build · status"), _blue),
    ]
    info_rows = []
    for key, value, color in info_items:
        icon = {"Workspace": "◉", "IDE Mode": "✸", "Session": "◐", "Model": "◈", "Workflows": "◆", "MCP": "◎"}.get(key, "·")
        label = color(f"{icon} {key}")
        vpad  = " " * max(0, LABEL_W - len(key) - 2)
        info_rows.append(f"{label}{vpad}  {value}")

    # Block width = widest of: logo lines, tagline, info rows (stripped of ANSI)
    block_w = max(
        _LOGO_WIDTH,
        len(tagline),
        len(sub),
        max(len(_strip_ansi(r)) for r in info_rows),
    )
    dw  = min(block_w + 2, W - 4)
    pad = " " * max(0, (W - block_w) // 2)

    # ── Render ────────────────────────────────────────────────────────────────
    print()
    logo_colors = [_blue, _cyan, _violet, _cyan, _blue]
    for i, line in enumerate(LOGO_LINES):
        print(pad + logo_colors[i % len(logo_colors)](_bold(line)))

    print()
    print(pad + _bold(_cyan(tagline)))
    print(pad + _dim(_gray(sub)))
    print()
    print(pad + _gray("─" * dw))
    print()
    for row in info_rows:
        print(pad + row)
    print()
    print(pad + _gray("─" * dw))
    print()
    print(pad + _dim(_gray("Press any key to enter…  (Ctrl-C to exit)")))
    print()

    if sys.stdout.isatty():
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    else:
        pass


def get_workspace_runtime_dir(ws_path: str, abs_project_root: str) -> str:
    import hashlib
    abs_ws = os.path.abspath(ws_path)
    ws_hash = hashlib.md5(abs_ws.encode("utf-8")).hexdigest()[:12]
    ws_name = os.path.basename(abs_ws) or "root"
    folder_name = f"{ws_name}_{ws_hash}"
    return os.path.abspath(os.path.join(abs_project_root, ".softwiki_runtime", folder_name))


# Save original XDG_CONFIG_HOME before any override — used to find user's real config
_ORIGINAL_XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def _global_opencode_dir() -> str:
    return os.path.join(_ORIGINAL_XDG_CONFIG_HOME, "opencode")


def _load_global_opencode_config() -> dict:
    """Read user's real global opencode config (tries .jsonc then .json)."""
    d = _global_opencode_dir()
    for name in ("opencode.jsonc", "opencode.json"):
        path = os.path.join(d, name)
        if os.path.exists(path):
            try:
                import re
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                # Strip single-line comments for jsonc compatibility
                text = re.sub(r'//[^\n]*', '', text)
                return json.loads(text)
            except Exception:
                pass
    return {}


def _build_mcp_config(softwiki_mcp: dict) -> dict:
    """Merge user's global MCPs with softwiki MCP, and add client-side search."""
    global_cfg = _load_global_opencode_config()
    mcps = {
        name: cfg
        for name, cfg in global_cfg.get("mcp", {}).items()
        if name != "softwiki"
    }
    mcps["softwiki"] = softwiki_mcp

    # Client-side search MCP — runs locally, never touches the softwiki server.
    # Priority: Exa > Tavily > (DuckDuckGo via webfetch, no MCP needed)
    exa_key    = os.getenv("EXA_API_KEY", "").strip()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    if exa_key:
        mcps["exa-search"] = {
            "type": "local",
            "command": ["npx", "-y", "exa-mcp-server"],
            "enabled": True,
            "environment": {"EXA_API_KEY": exa_key},
        }
    elif tavily_key:
        mcps["tavily-search"] = {
            "type": "local",
            "command": ["npx", "-y", "tavily-mcp"],
            "enabled": True,
            "environment": {"TAVILY_API_KEY": tavily_key},
        }
    # else: DuckDuckGo via webfetch — agent handles this natively, no MCP needed

    return mcps



def start_shell(model_override: str = None, session_suffix: str = None):
    ws   = _ws_dir()
    root = _project_root()
    os.makedirs(ws, exist_ok=True)

    abs_project_root = root
    runtime_dir = get_workspace_runtime_dir(ws, abs_project_root)

    # 1. Load merged agent soul & workflows
    soul      = _get_agent_soul(ws, root)
    workflows = _get_workflows(ws, root)

    # 2. Format workflows into markdown instructions
    workflows_md  = "\n## Available Workflows & Modes\n"
    workflows_md += ("Below are the research workflows configured for this workspace. "
                     "When a query matches one of these intents, follow the steps exactly.\n\n")

    for wf_id, wf_info in workflows.get("workflows", {}).items():
        name = wf_info.get("name", wf_id)
        desc = wf_info.get("description", "")
        workflows_md += f"### Mode/Workflow: `{wf_id}` ({name})\n"
        if desc:
            workflows_md += f"Description: {desc}\n"
        workflows_md += "Steps:\n"
        for step_num, step_desc in wf_info.get("steps", {}).items():
            workflows_md += f"{step_num}. {step_desc}\n"
        workflows_md += "\n"

    mode = os.getenv("SOFTWIKI_MODE", "wiki-admin")
    if mode not in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]:
        if f"wiki-{mode}" in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]:
            mode = f"wiki-{mode}"
        else:
            mode = "wiki-admin"
            
    session_id = os.getenv("SOFTWIKI_SESSION_ID", "default")
    abs_ws_path = os.path.abspath(ws)

    # Clean up legacy auto-generated files and hidden directories from the workspace directory to prevent clutter
    import glob
    for legacy_pattern in ["AGENTS.md", "AGENTS_*.md", "opencode.json"]:
        for fpath in glob.glob(os.path.join(ws, legacy_pattern)):
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except Exception as e:
                print(f"Failed to remove legacy workspace file {fpath}: {e}")

    for legacy_dir in [os.path.join(ws, ".claude"), os.path.join(ws, ".opencode")]:
        if os.path.exists(legacy_dir):
            try:
                shutil.rmtree(legacy_dir)
            except Exception as e:
                print(f"Failed to remove legacy workspace directory {legacy_dir}: {e}")

    legacy_opencode_config = os.path.join(ws, ".config", "opencode")
    if os.path.exists(legacy_opencode_config):
        try:
            shutil.rmtree(legacy_opencode_config)
        except Exception as e:
            print(f"Failed to remove legacy workspace directory {legacy_opencode_config}: {e}")

    legacy_config = os.path.join(ws, ".config")
    if os.path.exists(legacy_config) and not os.listdir(legacy_config):
        try:
            os.rmdir(legacy_config)
        except Exception as e:
            print(f"Failed to remove empty legacy workspace directory {legacy_config}: {e}")

    # 3. Write instructions for each mode to their respective files in the runtime folder
    agents_paths = {}
    opencode_config_dir = os.path.join(runtime_dir, "opencode")
    os.makedirs(opencode_config_dir, exist_ok=True)
    
    for m in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]:
        m_rules = f"""
## Active Workspace Mode & Security Constraints

You are running in the **{m.upper()}** mode in the Softwiki Research Environment.
Depending on the mode, certain operations are restricted:
- **wiki-study**: READ-ONLY. You can research with websearch and check status. You MUST NOT call softwiki_ingest, softwiki_index, softwiki_wiki_build, or any write operation. You CANNOT submit research either.
- **wiki-work**: WORK mode. You can research with websearch. You MUST NOT call softwiki_ingest or softwiki_index directly. If you find valuable sources during research, use the `submit` workflow to stage them for manager review in the session output directory (`output/{session_id}/`). Do NOT modify the canonical knowledge base.
- **wiki-manage**: KNOWLEDGE MANAGEMENT. You can ingest, index, build wikis, and review/publish submitted work from wiki-work users.
- **wiki-admin**: FULL ADMINISTRATOR. All operations are permitted.

## Strict Operational Boundary (Sandbox Rules)

1. **Project Sandbox Constraint**:
   - You MUST strictly limit your operations and tasks to the softwiki project and the active workspace directory.
   - You MUST NOT read, write, modify, or list files outside the workspace directory `{abs_ws_path}`.
   - You MUST NOT run arbitrary shell commands that exit the project or access external system files.
   
2. **Task Constraint**:
   - You are restricted to performing softwiki-related tasks (ingestion, retrieval, indexing, wiki compilation, database query).
   - If the user asks you to perform tasks unrelated to softwiki (such as system administration, web browsing unrelated to softwiki sources, or modifying code unrelated to softwiki), you MUST politely refuse and state that your operations are restricted to the softwiki research workspace.
"""
        full_instructions = soul + "\n" + workflows_md + "\n" + m_rules
        m_path = os.path.join(opencode_config_dir, f"AGENTS_{m}.md")
        with open(m_path, "w", encoding="utf-8") as f:
            f.write(full_instructions)
        agents_paths[m] = os.path.abspath(m_path)

    # 4. Generate / update local opencode config file in a dedicated config dir (keeping global configs untouched/parallel)
    # Shell model is independent from the Core LLM model.
    # Use SHELL_MODEL / SHELL_API_BASE / SHELL_API_KEY if set; fall back to core settings.
    model_name = model_override \
        or os.getenv("SHELL_MODEL") \
        or os.getenv("ANALYSIS_MODEL", "gemini-2.5-flash")
    api_base   = os.getenv("SHELL_API_BASE") \
        or os.getenv("OPENAI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/")
    api_key_ref = "{env:SHELL_API_KEY}" if os.getenv("SHELL_API_KEY") else "{env:OPENAI_API_KEY}"

    # abs_project_root is already defined at the start of start_shell
    
    python_cmd = os.path.join(abs_project_root, "venv", "bin", "python")
    if not os.path.exists(python_cmd):
        python_cmd = os.path.join(abs_project_root, "venv", "bin", "python3")

    project_root = "."
    rel_ws = os.path.join(".", os.path.relpath(os.path.abspath(ws), abs_project_root))

    mcp_env = {
        "WORKSPACE_DIR": rel_ws,
        "PYTHONPATH": project_root
    }
    if os.getenv("SOFTWIKI_MODE"):
        mcp_env["SOFTWIKI_MODE"] = os.getenv("SOFTWIKI_MODE")
    if os.getenv("SOFTWIKI_SESSION_ID"):
        mcp_env["SOFTWIKI_SESSION_ID"] = os.getenv("SOFTWIKI_SESSION_ID")

    mcp_config = {
        "type": "local",
        "command": [
            python_cmd,
            "-m",
            "softwiki.mcp.server"
        ],
        "cwd": abs_project_root,
        "enabled": True,
        "environment": mcp_env
    }

    agents_config = {
        "sisyphus": {"disable": True},
        "Sisyphus": {"disable": True},
        "build": {"disable": True},
        "Build": {"disable": True},
        "plan": {"disable": True},
        "Plan": {"disable": True},
        "planner": {"disable": True},
        "Planner": {"disable": True},
        "oracle": {"disable": True},
        "Oracle": {"disable": True},
        "researcher": {"disable": True},
        "Researcher": {"disable": True},
        "librarian": {"disable": True},
        "Librarian": {"disable": True},
        "archivist": {"disable": True},
        "Archivist": {"disable": True},
    }
    for m in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]:
        agents_config[m] = {
            "description": f"Softwiki {m.upper()} Agent",
            "mode": "primary",
            "prompt": f"{{file:{agents_paths[m]}}}"
        }

    workspace_config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"gemini-compat/{model_name}",
        "instructions": [agents_paths[mode]],
        "provider": {
            "gemini-compat": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Gemini (OpenAI-compat)",
                "options": {
                    "baseURL": api_base,
                    "apiKey": api_key_ref
                },
                "models": {
                    model_name: {
                        "name": f"Gemini {model_name}",
                        "attachment": True,
                        "reasoning": False
                    }
                }
            }
        },
        "agent": agents_config,
        "mcp": _build_mcp_config(mcp_config),
        "plugin": _load_global_opencode_config().get("plugin", []),
        "tools": {
            "websearch": True,
            "webfetch": True
        }
    }
    
    # Write our config to the isolated runtime dir (XDG_CONFIG_HOME will point here)
    xdg_config_home = runtime_dir
    opencode_config_dir = os.path.join(xdg_config_home, "opencode")
    os.makedirs(opencode_config_dir, exist_ok=True)
    config_path = os.path.join(opencode_config_dir, "opencode.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(workspace_config, f, indent=2)

    # Copy tui.json from global config (TUI plugin list)
    global_tui = os.path.join(_global_opencode_dir(), "tui.json")
    if os.path.exists(global_tui):
        shutil.copy2(global_tui, os.path.join(opencode_config_dir, "tui.json"))

    # Force-recreate node_modules symlink → global opencode node_modules
    # (so oh-my-openagent and other plugins resolve correctly)
    global_nm = os.path.join(_global_opencode_dir(), "node_modules")
    runtime_nm = os.path.join(opencode_config_dir, "node_modules")
    if os.path.isdir(global_nm):
        if os.path.islink(runtime_nm):
            os.unlink(runtime_nm)
        elif os.path.isdir(runtime_nm):
            shutil.rmtree(runtime_nm)
        os.symlink(global_nm, runtime_nm)

    # Also copy package.json so plugin resolution works
    global_pkg = os.path.join(_global_opencode_dir(), "package.json")
    if os.path.exists(global_pkg):
        shutil.copy2(global_pkg, os.path.join(opencode_config_dir, "package.json"))

    # 5. Print Softwiki banner
    _print_banner(ws, f"gemini-compat/{model_name} (shell)", workflows)

    # 6. Check for external opencode executable
    opencode_path = shutil.which("opencode")
    if opencode_path:
        try:
            # Isolate config AND sessions from user's global opencode
            os.environ["XDG_CONFIG_HOME"] = xdg_config_home
            os.environ["XDG_DATA_HOME"]   = xdg_config_home
            os.environ["CLAUDE_CONFIG_DIR"] = os.path.abspath(os.path.join(runtime_dir, ".claude"))
            os.makedirs(os.environ["CLAUDE_CONFIG_DIR"], exist_ok=True)
            for env_var in ["OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"]:
                if env_var in os.environ:
                    del os.environ[env_var]
            # Sessions are stored in our isolated XDG_DATA_HOME, separate from
            # the user's global opencode sessions.
            # --continue resumes the last session in this isolated store (skips
            # home screen). On first launch (empty store) it creates a new session.
            # With a custom suffix, use --session so threads stay distinct.
            # opencode doesn't support creating named sessions via --session.
            # We manage session naming ourselves: default="null", or user-supplied.
            # --continue skips the home screen and resumes/creates a session.
            resolved_suffix = session_suffix or "null"
            os.environ["SOFTWIKI_SESSION_SUFFIX"] = resolved_suffix
            cmd = ["opencode", "--agent", mode, "--continue", abs_project_root]
            os.execvp("opencode", cmd)
        except Exception as e:
            print(f"[!] Failed to launch OpenCode: {e}")
            run_fallback_repl(ws)
    else:
        # Fallback to local Softwiki CLI Shell
        run_fallback_repl(ws)



def _shell_web_search(query: str, top_k: int = 5) -> str:
    """Shell-native web search using BYOK providers. Does NOT go through MCP.

    Checks env vars in order: TAVILY_API_KEY, SERPAPI_KEY, BING_SEARCH_API_KEY.
    If none are set, returns a setup instruction.
    """
    import requests as _req

    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    bing_key    = os.getenv("BING_SEARCH_API_KEY", "").strip()

    if not any([tavily_key, serpapi_key, bing_key]):
        return (
            "Web search is not configured.\n"
            "Add one of the following to your .env file:\n"
            "  TAVILY_API_KEY=...       (recommended, https://tavily.com)\n"
            "  SERPAPI_KEY=...          (https://serpapi.com)\n"
            "  BING_SEARCH_API_KEY=...  (Azure Cognitive Services)"
        )

    results = []
    provider_used = None

    if tavily_key and not results:
        try:
            resp = _req.post(
                "https://api.tavily.com/search",
                json={"query": query, "max_results": top_k, "include_answer": False},
                headers={"Authorization": f"Bearer {tavily_key}"},
                timeout=15
            )
            resp.raise_for_status()
            results = [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in resp.json().get("results", [])
            ]
            provider_used = "Tavily"
        except Exception as e:
            print(f"[web] Tavily error: {e}")

    if serpapi_key and not results:
        try:
            resp = _req.get(
                "https://serpapi.com/search",
                params={"q": query, "num": top_k, "api_key": serpapi_key, "engine": "google"},
                timeout=15
            )
            resp.raise_for_status()
            results = [
                {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
                for r in resp.json().get("organic_results", [])[:top_k]
            ]
            provider_used = "SerpAPI"
        except Exception as e:
            print(f"[web] SerpAPI error: {e}")

    if bing_key and not results:
        try:
            resp = _req.get(
                "https://api.bing.microsoft.com/v7.0/search",
                params={"q": query, "count": top_k, "mkt": "zh-CN"},
                headers={"Ocp-Apim-Subscription-Key": bing_key},
                timeout=15
            )
            resp.raise_for_status()
            results = [
                {"title": r.get("name", ""), "url": r.get("url", ""), "snippet": r.get("snippet", "")}
                for r in resp.json().get("webPages", {}).get("value", [])[:top_k]
            ]
            provider_used = "Bing"
        except Exception as e:
            print(f"[web] Bing error: {e}")

    if not results:
        return "Web search returned no results."

    lines = [f"[Web Search via {provider_used}]\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}\n    {r['url']}\n    {r['snippet']}")
    return "\n\n".join(lines)


def run_fallback_repl(ws: str):
    try:
        import readline  # noqa: F401 – enables arrow-key history on Linux/macOS
    except ImportError:
        pass

    ws_name = os.path.basename(os.path.abspath(ws))
    mode = os.getenv("SOFTWIKI_MODE", "wiki-admin")
    if mode not in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]:
        mode = f"wiki-{mode}" if f"wiki-{mode}" in ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"] else "wiki-admin"

    # Read scope description from scope.md (no softwiki import needed)
    scope_desc = "None (No scope restrictions)"
    for scope_path in (os.path.join(ws, "scope.md"), os.path.join(ws, "configs", "scope.md")):
        if os.path.exists(scope_path):
            try:
                with open(scope_path, encoding="utf-8") as f:
                    for ln in f:
                        stripped = ln.strip()
                        if stripped.startswith("#"):
                            scope_desc = stripped.lstrip("#").strip()
                            break
            except Exception:
                pass
            break

    print("\n\033[1;36m=== Softwiki Shell (fallback REPL) ===\033[0m")
    print(f"Active Workspace: \033[1;33m{ws_name}\033[0m (\033[2m{os.path.abspath(ws)}\033[0m)")
    print(f"Active Scope:     \033[1;33m{scope_desc}\033[0m")
    print(f"Active Mode:      \033[1;33m{mode}\033[0m")
    print("\033[2m(opencode not found – running minimal MCP client shell)\033[0m")
    print("Commands:")
    print("  \033[32m/ask <question>\033[0m      - Query the knowledge base (via MCP)")
    print("  \033[32m/web <query>\033[0m         - Web search (BYOK)")
    print("  \033[32m/ingest <url|path>\033[0m   - Ingest a document (via MCP)")
    print("  \033[32m/index\033[0m               - Rebuild search indexes (via MCP)")
    print("  \033[32m/wiki <topic>\033[0m        - Generate wiki page (via MCP)")
    print("  \033[32m/init\033[0m                - Initialize workspace structure")
    print("  \033[32m/status\033[0m              - Workspace status (via MCP)")
    print("  \033[32m/help\033[0m                - List commands")
    print("  \033[32m/exit\033[0m                - Exit\n")

    _READ_ONLY = {"wiki-study", "study"}
    _WRITE_RESTRICTED = {"wiki-study", "wiki-work", "study", "work"}

    while True:
        try:
            line = input(f"\033[1;35msoftwiki [{ws_name}:{mode}]> \033[0m").strip()
            if not line:
                continue

            # ── /exit ────────────────────────────────────────────────────────
            if line in ("/exit", "/quit"):
                print("Goodbye!")
                break

            # ── /ask ─────────────────────────────────────────────────────────
            elif line.startswith("/ask "):
                q = line[5:].strip()
                if not q:
                    print("Error: Please specify a question.")
                    continue
                print(f"\nResearching: \"{q}\"…\n")
                print(_call_mcp_tool("ask", {"query": q}) + "\n")

            # ── /web ─────────────────────────────────────────────────────────
            elif line.startswith("/web "):
                q = line[5:].strip()
                if not q:
                    print("Error: Please specify a search query.")
                    continue
                print(f"\nSearching the web for: \"{q}\"…\n")
                print(_shell_web_search(q) + "\n")

            # ── /ingest ──────────────────────────────────────────────────────
            elif line.startswith("/ingest "):
                if mode in _WRITE_RESTRICTED:
                    print(f"[提示] ingest 在 [{mode}] 模式下被禁用。请使用 wiki-admin 或 wiki-manage 模式。")
                    continue
                target = line[8:].strip()
                if not target:
                    print("Error: Please specify a URL or local file path.")
                    continue
                is_url = target.startswith("http://") or target.startswith("https://")
                args = {"url": target} if is_url else {"file": os.path.abspath(target)}
                print(f"\nIngesting: {target}…\n")
                print(_call_mcp_tool("ingest", args) + "\n")

            # ── /init ────────────────────────────────────────────────────────
            elif line == "/init":
                if mode in _WRITE_RESTRICTED:
                    print(f"Error: init is disabled in {mode} mode.")
                    continue
                confirm = input(f"Initialize/overwrite workspace '{ws_name}'? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Cancelled.")
                    continue
                root = _project_root()
                cmd = [_python_bin(root), "-m", "softwiki.cli.main",
                       "--workspace", ws, "--mode", mode, "init"]
                env = os.environ.copy()
                env["WORKSPACE_DIR"] = ws
                result = subprocess.run(cmd, env=env, cwd=root)
                if result.returncode != 0:
                    print("Init command exited with errors.")

            # ── /index ───────────────────────────────────────────────────────
            elif line == "/index":
                if mode in _WRITE_RESTRICTED:
                    print(f"[提示] index 在 [{mode}] 模式下被禁用。")
                    continue
                confirm = input("Rebuild all indexes? This may take a while. [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Cancelled.")
                    continue
                print("\nRebuilding indexes…\n")
                print(_call_mcp_tool("index", {}) + "\n")

            # ── /wiki ────────────────────────────────────────────────────────
            elif line.startswith("/wiki "):
                if mode in _READ_ONLY:
                    print(f"[提示] wiki 编译在 [{mode}] 模式下被禁用。")
                    continue
                topic = line[6:].strip()
                if not topic:
                    print("Error: Please specify a topic ID.")
                    continue
                print(f"\nCompiling wiki page for: {topic}…\n")
                print(_call_mcp_tool("wiki_build", {"topic": topic}) + "\n")

            # ── /status ──────────────────────────────────────────────────────
            elif line == "/status":
                print(_call_mcp_tool("status", {}) + "\n")

            # ── /help ────────────────────────────────────────────────────────
            elif line == "/help":
                print("Commands: /ask /web /ingest /index /wiki /init /status /help /exit")

            else:
                print("Unknown command. Type /help for available commands.")

        except KeyboardInterrupt:
            print("\nUse /exit to quit.")
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Runtime error: {e}")


if __name__ == "__main__":
    start_shell()


