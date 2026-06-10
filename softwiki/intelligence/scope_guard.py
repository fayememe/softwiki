import os
import sys
from softwiki.config import get_workspace_dir
from softwiki.intelligence.llm_client import get_llm_client_and_params

def get_scope_file_path() -> str:
    """Finds the scope.md file in the workspace directory or configs directory."""
    # 1. Check <workspace_dir>/scope.md
    path1 = os.path.join(get_workspace_dir(), "scope.md")
    if os.path.exists(path1):
        return path1
    # 2. Check <workspace_dir>/config/scope.md
    path2 = os.path.join(get_workspace_dir(), "config", "scope.md")
    if os.path.exists(path2):
        return path2
    return None

def check_scope(text: str, item_type: str = "document") -> tuple[bool, str]:
    """Checks if the given text is within the scope of the knowledge base.
    
    Args:
        text: The content to check.
        item_type: The type of content (e.g., 'document', 'query', 'search_query', 'wiki_topic').
        
    Returns:
        (is_in_scope, reason)
    """
    scope_path = get_scope_file_path()
    if not scope_path:
        # Default to True (in scope) if no scope file is defined.
        return True, "No scope.md defined, bypassing check."
        
    try:
        with open(scope_path, "r", encoding="utf-8") as f:
            scope_content = f.read().strip()
    except Exception as e:
        return True, f"Failed to read scope.md: {e}. Bypassing check."

    if not scope_content:
        return True, "scope.md is empty, bypassing check."

    # Retrieve LLM client using 'cheap_extraction' or fall back to 'high_quality_analysis'
    client, model_name, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
    if not client:
        client, model_name, temperature, max_tokens = get_llm_client_and_params("high_quality_analysis")
        
    if not client:
        # If no LLM client configured, log a warning to stderr and bypass check
        print("Warning: No LLM client configured for scope checking. Bypassing check.", file=sys.stderr)
        return True, "No LLM client configured."

    system_prompt = f"""You are a Scope Guard agent for a research knowledge base.
Your job is to determine whether a given item (which could be a document, a user question, a web search query, or a wiki topic) is within the defined scope of this knowledge base.

Here is the defined scope of the knowledge base:
---
{scope_content}
---

Analyze the item content carefully. If the item is relevant to the defined scope (even if partially or broadly, but not completely off-topic), it is IN_SCOPE. If it is completely unrelated or explicitly out of scope, it is OUT_OF_SCOPE.

Your response must be in one of the following formats:
If it is in scope:
IN_SCOPE: <brief explanation of why it is in scope>

If it is out of scope:
OUT_OF_SCOPE: <clear, user-friendly explanation of why it is out of scope and how it exceeds the scope>

Ensure your explanation is in the same language as the item content (e.g. Chinese if the item is Chinese, English if the item is English).
"""

    user_content = f"Item Type: {item_type}\nItem Content:\n{text}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.0,
            max_tokens=256
        )
        result = response.choices[0].message.content.strip()
        if result.startswith("OUT_OF_SCOPE"):
            reason = result.split("OUT_OF_SCOPE:", 1)[-1].strip()
            return False, reason
        elif result.startswith("IN_SCOPE"):
            reason = result.split("IN_SCOPE:", 1)[-1].strip()
            return True, reason
        else:
            # Fallback parsing
            if "out of scope" in result.lower() or "out_of_scope" in result.lower():
                return False, result
            return True, result
    except Exception as e:
        print(f"Warning: Scope checking failed due to LLM error: {e}. Bypassing check.", file=sys.stderr)
        return True, f"LLM error: {e}"
