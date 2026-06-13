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

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model_name, temperature, max_tokens
