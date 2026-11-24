import os
import yaml
from openai import OpenAI
from softwiki.config import get_config_path

def get_llm_client_and_params(profile_name: str):
    """Reads configs/model_profiles.yaml and returns (client, model_name, temperature, max_tokens)
    
    If model_profiles.yaml does not exist or has invalid/missing keys,
    it falls back to default settings and environment variables.
    """
    profiles = {}
    profiles_path = get_config_path("model_profiles.yaml")
    
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = yaml.safe_load(f).get("profiles", {}) or {}
        except Exception as e:
            print(f"Error loading model profiles: {e}")

    profile = profiles.get(profile_name, {})
    
    provider = profile.get("provider", "openai").lower()
    model_name = profile.get("model")
    temperature = profile.get("temperature", 0.0)
    max_tokens = profile.get("max_tokens")

    # Fallback to standard environment variables if profile is missing values
    if not model_name:
        if profile_name == "cheap_extraction":
            model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")
        elif profile_name == "high_quality_analysis":
            model_name = os.getenv("ANALYSIS_MODEL", "gpt-4o")
        elif profile_name == "wiki_compilation":
            model_name = os.getenv("WIKI_MODEL", "gemini-2.5-pro")
        else:
            model_name = "gpt-4o-mini"

    # API key and base URL resolution (profile takes priority, then env vars)
    api_key = profile.get("api_key") or None
    base_url = profile.get("api_base") or None

    if not api_key:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider in ["gemini", "google"]:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        elif provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")

    if not base_url:
        if provider in ["gemini", "google"]:
            base_url = os.getenv("OPENAI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta/"
        elif provider == "ollama":
            base_url = os.getenv("OLLAMA_API_BASE") or "http://localhost:11434/v1"
        elif provider == "deepseek":
            base_url = "https://api.deepseek.com/v1"
        else:
            base_url = os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1"

    is_valid_key = bool(api_key and not api_key.startswith("your_"))

    if not is_valid_key:
        return None, model_name, temperature, max_tokens

    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
    _disable_thinking(client)
    return client, model_name, temperature, max_tokens


def _disable_thinking(client) -> None:
    """Some OpenAI-compatible gateways spend max_tokens on hidden reasoning.

    When LLM_DISABLE_THINKING=1, add thinking={"type":"disabled"} via
    extra_body. Servers that do not support it generally ignore unknown fields.
    """
    if os.getenv("LLM_DISABLE_THINKING", "").lower() not in ("1", "true", "yes"):
        return

    original = client.chat.completions.create

    def create(*args, **kwargs):
        extra = dict(kwargs.get("extra_body") or {})
        extra.setdefault("thinking", {"type": "disabled"})
        kwargs["extra_body"] = extra
        return original(*args, **kwargs)

    client.chat.completions.create = create


def create_chat_completion(client, attempts: int = 3, **kwargs):
    """Chat completion with retry/backoff for transient gateway errors (504/502).

    Bulk re-extraction fans out many concurrent calls; gateways answer some of
    them with 5xx. Retrying is much cheaper than a silent quality loss, and it
    keeps the caller's fallback path for genuine failures.
    """
    import random
    import time

    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - retried below
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(min(8, 2 ** attempt) + random.random())
    raise last_error  # type: ignore[misc]
