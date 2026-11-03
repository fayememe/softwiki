"""Fetch trial-corpus documents locally and stage them as markdown.

The trial hosts (trial-host) cannot reach most upstream sources, so documents are
fetched here, cleaned to plain text, and later pushed as ``.md`` files whose
YAML front matter carries title/author/date/url for provenance.

Usage:
    python scripts/trial_fetch.py --kb coffee --out /tmp/trial/coffee \
        --sources wiki,rss,urls,europepmc --target 180
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trial_sources as catalog

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

UA = "SoftWikiKB/1.0 (internal research trial; +https://github.com/operator/softwiki; operator@localhost)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en"}
MAX_CHARS = 40000
WIKI_API = "https://en.wikipedia.org/w/api.php"

SKIP_TAGS = ["script", "style", "noscript", "nav", "footer", "aside", "form", "iframe", "svg"]


def make_soup(content, prefer: str = "html"):
    for builder in ([prefer, "lxml", "html.parser"] if prefer == "xml" else ["lxml", "html.parser"]):
        try:
            return BeautifulSoup(content, builder)
        except Exception:
            continue
    return BeautifulSoup(content, "html.parser")
SKIP_HINTS = ("cookie", "newsletter", "subscribe", "advert", "share", "comment", "related")


def slugify(value: str, limit: int = 80) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (value[:limit] or "doc").strip("-")


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
    return value.strip()


def soup_to_text(soup: BeautifulSoup) -> str:
    for tag in list(soup.find_all(True)):
        if getattr(tag, "decomposed", False) or tag.parent is None:
            continue
        if tag.name in SKIP_TAGS:
            tag.decompose()
            continue
        marker = " ".join(
            filter(None, [tag.get("id") or "", " ".join(tag.get("class") or [])])
        ).lower()
        if any(hint in marker for hint in SKIP_HINTS):
            tag.decompose()

    candidates = []
    for sel in ("article", "main", "[role=main]", "div.post-content", "div.entry-content", "body"):
        for node in soup.select(sel):
            text = "\n\n".join(
                clean_text(p.get_text(" ", strip=True))
                for p in node.find_all(["p", "h2", "h3", "li"])
            )
            candidates.append((len(text), text))
    if not candidates:
        return ""
    return max(candidates)[1]


def write_doc(out_dir: str, slug: str, meta: dict, body: str) -> str:
    body = body[:MAX_CHARS].strip()
    lines = ["---"]
    for key in ("title", "author", "date", "url"):
        value = meta.get(key)
        if value:
            lines.append(f"{key}: {json.dumps(str(value))}")
    lines.append("---")
    lines.append("")
    path = os.path.join(out_dir, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n" + body + "\n")
    return path


def fetch_wikipedia(session: httpx.Client, titles) -> list[tuple[str, dict, str]]:
    def one(title: str):
        page = {}
        for attempt in range(4):
            try:
                response = session.get(
                    WIKI_API,
                    params={
                        "action": "query",
                        "prop": "extracts|revisions",
                        "explaintext": "1",
                        "rvprop": "timestamp",
                        "rvlimit": "1",
                        "format": "json",
                        "redirects": "1",
                        "titles": title,
                    },
                )
                response.raise_for_status()
                page = next(iter(response.json().get("query", {}).get("pages", {}).values()), {})
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(3 * (attempt + 1))
                    continue
                print(f"  wiki failed {title}: HTTP {status}")
                return None
            except Exception as exc:
                print(f"  wiki failed {title}: {type(exc).__name__}")
                return None
        resolved = page.get("title")
        extract = page.get("extract") or ""
        if not resolved or page.get("missing") is not None or len(extract) < 500:
            print(f"  skip wiki: {resolved or title} ({len(extract)} chars)")
            return None
        revisions = page.get("revisions") or []
        revision_date = revisions[0].get("timestamp", "")[:10] if revisions else None
        meta = {
            "title": resolved,
            "author": "Wikipedia contributors",
            "date": revision_date,
            "url": f"https://en.wikipedia.org/wiki/{resolved.replace(' ', '_')}",
        }
        return (f"wiki-{slugify(resolved)}", meta, extract)

    titles = list(titles)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, titles))
    return [item for item in results if item]


def feed_entries(session: httpx.Client, feed_url: str) -> list[dict]:
    try:
        response = session.get(feed_url)
        response.raise_for_status()
    except Exception as exc:
        print(f"  feed failed {feed_url}: {type(exc).__name__}")
        return []

    try:
        root = ET.fromstring(response.content)
    except Exception:
        return feed_entries_regex(response.text)

    entries = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = link = date = None
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link" and not link:
                link = (child.text or "").strip() or child.get("href")
            elif tag in ("pubDate", "published", "updated") and not date:
                date = (child.text or "").strip()
        if link and title:
            entries.append({"url": link, "title": title, "date": date})
    return entries


def feed_entries_regex(text: str) -> list[dict]:
    entries = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", text, re.S | re.I):
        title = re.search(r"<title[^>]*>(.*?)</title>", block, re.S | re.I)
        link = re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I)
        href = re.search(r'<link[^>]+href="([^"]+)"', block, re.I)
        date = re.search(r"<(?:pubDate|published|updated)[^>]*>(.*?)</", block, re.S | re.I)
        url = (link.group(1).strip() if link else "") or (href.group(1) if href else "")
        if not url:
            continue
        entries.append(
            {
                "url": html.unescape(url),
                "title": clean_text(re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1))) if title else "",
                "date": date.group(1).strip() if date else "",
            }
        )
    return entries
    return entries


def parse_date(value: str):
    if not value:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    return match.group(0) if match else None


def fetch_article(session: httpx.Client, url: str) -> tuple[dict, str] | None:
    try:
        response = session.get(url)
        response.raise_for_status()
    except Exception as exc:
        print(f"  fetch failed {url}: {type(exc).__name__}")
        return None
    soup = make_soup(response.text)
    body = soup_to_text(soup)
    if len(body) < 800:
        print(f"  thin body {url} ({len(body)} chars)")
        return None
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"]
    published = soup.find("meta", attrs={"property": "article:published_time"})
    date = parse_date(published["content"]) if published and published.get("content") else None
    author = soup.find("meta", attrs={"name": "author"})
    return (
        {
            "title": clean_text(title or urlparse(url).path),
            "author": (author["content"] if author and author.get("content") else None),
            "date": date,
            "url": url,
        },
        body,
    )


def fetch_europepmc(session: httpx.Client, query: str, limit: int) -> list[tuple[str, dict, str]]:
    docs = []
    try:
        response = session.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": limit,
                "resultType": "core",
            },
        )
        response.raise_for_status()
        results = response.json().get("resultList", {}).get("result", [])
    except Exception as exc:
        print(f"  europepmc search failed: {exc}")
        return docs

    for hit in results:
        pmcid = hit.get("pmcid")
        if not pmcid:
            continue
        try:
            full = session.get(
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
            )
            full.raise_for_status()
        except Exception:
            continue
        soup = make_soup(full.text, "xml")
        paragraphs = [
            clean_text(node.get_text(" ", strip=True))
            for node in soup.find_all(["p", "title"])
        ]
        body = "\n\n".join(p for p in paragraphs if p)
        if len(body) < 1500:
            continue
        meta = {
            "title": hit.get("title") or pmcid,
            "author": hit.get("authorString"),
            "date": parse_date(hit.get("firstPublicationDate") or ""),
            "url": f"https://europepmc.org/article/MED/{hit.get('pmid')}" if hit.get("pmid") else f"https://europepmc.org/{pmcid}",
        }
        docs.append((f"pmc-{pmcid.lower()}", meta, body))
    return docs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", required=True, choices=["coffee", "ai-history"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--sources", default="wiki,rss,urls,europepmc")
    parser.add_argument("--target", type=int, default=180)
    parser.add_argument("--rss-per-feed", type=int, default=25)
    parser.add_argument("--pmc-limit", type=int, default=80)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    docs: list[tuple[str, dict, str]] = []
    seen_slugs: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=40, follow_redirects=True) as session:
        if "wiki" in wanted:
            titles = list(catalog.wiki_titles(args.kb))
            print(f"[wiki] {len(titles)} titles")
            docs.extend(fetch_wikipedia(session, titles))

        if "urls" in wanted:
            for url in catalog.urls(args.kb):
                result = fetch_article(session, url)
                if result:
                    meta, body = result
                    docs.append((f"web-{slugify(meta['title'])}", meta, body))

        if "rss" in wanted:
            for feed in catalog.feeds(args.kb):
                entries = feed_entries(session, feed)[: args.rss_per_feed]
                print(f"[rss] {feed} -> {len(entries)}")
                for entry in entries:
                    result = fetch_article(session, entry["url"])
                    if not result:
                        continue
                    meta, body = result
                    meta["title"] = meta.get("title") or entry["title"]
                    meta["date"] = meta.get("date") or parse_date(entry["date"])
                    docs.append((f"web-{slugify(meta['title'])}", meta, body))
                    time.sleep(0.4)

        if "europepmc" in wanted:
            for query in catalog.EUROPEPMC.get(args.kb, []):
                print(f"[europepmc] {query}")
                docs.extend(fetch_europepmc(session, query, args.pmc_limit))

    kept = 0
    report = {"written": [], "duplicate": [], "empty": []}
    for slug, meta, body in docs:
        if kept >= args.target:
            break
        if slug in seen_slugs:
            report["duplicate"].append(slug)
            continue
        if len(body) < 800:
            report["empty"].append(slug)
            continue
        seen_slugs.add(slug)
        write_doc(args.out, slug, meta, body)
        report["written"].append({"slug": slug, "title": meta.get("title"), "chars": min(len(body), MAX_CHARS), "url": meta.get("url")})
        kept += 1

    with open(os.path.join(args.out, "_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(f"written={len(report['written'])} dup={len(report['duplicate'])} empty={len(report['empty'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
