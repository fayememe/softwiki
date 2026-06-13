"""Web search for SoftWiki Core. No API key needed for DuckDuckGo (default)."""

import os
from typing import Optional, List

def search_web(query: str, top_k: int = 5) -> Optional[List[str]]:
    """Search the web. Tries providers in order: DuckDuckGo > Tavily > SerpAPI > Bing.
    Returns list of formatted results or None if all fail.
    """
    # 1. DuckDuckGo (free, no key)
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=top_k))
            if results:
                return [f"({r['title']}) {r['body'][:300]} [{r['href']}]" for r in results if r.get('title')]
    except Exception:
        pass

    # 2. Tavily (requires TAVILY_API_KEY)
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if tavily_key:
        try:
            import requests
            resp = requests.post("https://api.tavily.com/search", json={
                "api_key": tavily_key, "query": query, "max_results": top_k,
                "include_answer": False, "include_raw_content": False,
            }, timeout=15)
            results = resp.json().get("results", [])
            if results:
                return [f"({r.get('title','')}) {r.get('content','')} [{r.get('url','')}]" for r in results]
        except Exception:
            pass

    # 3. SerpAPI (requires SERPAPI_KEY)
    serp_key = os.getenv("SERPAPI_KEY", "").strip()
    if serp_key:
        try:
            import requests
            resp = requests.get("https://serpapi.com/search", params={
                "api_key": serp_key, "q": query, "engine": "google", "num": top_k,
            }, timeout=15)
            results = resp.json().get("organic_results", [])
            if results:
                return [f"({r.get('title','')}) {r.get('snippet','')} [{r.get('link','')}]" for r in results]
        except Exception:
            pass

    # 4. Bing (requires BING_SEARCH_API_KEY)
    bing_key = os.getenv("BING_SEARCH_API_KEY", "").strip()
    if bing_key:
        try:
            import requests
            resp = requests.get("https://api.bing.microsoft.com/v7.0/search", params={"q": query, "count": top_k},
                headers={"Ocp-Apim-Subscription-Key": bing_key}, timeout=15)
            results = resp.json().get("webPages", {}).get("value", [])
            if results:
                return [f"({r.get('name','')}) {r.get('snippet','')} [{r.get('url','')}]" for r in results]
        except Exception:
            pass

    return None
