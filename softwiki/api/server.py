from __future__ import annotations

import json
import os
import re
import sys
import threading
import uuid
import shutil
import time
from datetime import datetime
from typing import List, Optional, Dict
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.engine import make_url

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from softwiki.config import get_workspace_dir, get_db_url, get_config_path, get_export_dir, is_module_enabled, set_workspace_dir, list_workspaces, get_workspaces_root, set_request_workspace
from softwiki.source_store.db import SessionLocal
from softwiki.source_store.models import Document, Claim, Chunk, Entity, Relationship, Event, User, WorkspaceMember, CanonicalClaim, ClaimEvidence, Contradiction, WikiArtifactState, WikiArtifactVersion
from softwiki.auth import auth_enabled, create_token, verify_password, verify_token
from softwiki.auth_db import get_auth_session
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.ingestion.web_loader import extract_web_content
from softwiki.ingestion.pdf_loader import extract_pdf_content
from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash, is_duplicate_url
from softwiki.knowledge.versioning import assign_document_version
from softwiki.knowledge.conflicts import list_conflicts, scan_conflicts, adjudicate, metrics as knowledge_metrics
from softwiki.knowledge.wiki_queue import enqueue_stale_wiki, pending_count
from softwiki.extraction.processor import run_extraction_pipeline
from softwiki.rag.chunker import build_document_chunks
from softwiki.rag.embedder import WikiEmbedder
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.rag.hybrid_search import HybridSearcher
from softwiki.rag.citations import CitationManager
from softwiki.intelligence.answer_engine import AnswerEngine
from softwiki.wiki.page_generator import WikiPageGenerator
from softwiki.wiki.interventions import (
    list_interventions,
    save_intervention,
    delete_intervention,
    compose_interventions,
    preview_dir,
)
from softwiki.wiki.coverage import compute_coverage

app = FastAPI(title="Softwiki REST API", version="0.1.0")

AGENT_WEB_URL = os.getenv("AGENT_WEB_URL", "http://127.0.0.1:6111").rstrip("/")
AGENT_DEFAULT = os.getenv("AGENT_DEFAULT", "wiki-research")
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "300"))

def _safe_db_url():
    try:
        return make_url(get_db_url()).render_as_string(hide_password=True)
    except Exception:
        return "unknown"

def check_read_only():
    if os.getenv("SOFTWIKI_MODE") in ["study", "work", "wiki-study", "wiki-work"]:
        raise HTTPException(status_code=403, detail="Write operations are disabled in study/work modes.")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_AUTH_EXEMPT = {"/api/login", "/api/health", "/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not auth_enabled():
        return await call_next(request)
    if request.url.path in _AUTH_EXEMPT:
        return await call_next(request)

    token = request.cookies.get("softwiki_session")
    header = request.headers.get("Authorization", "")
    if not token and header.startswith("Bearer "):
        token = header[7:]
    username = verify_token(token) if token else None
    if not username:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)

    db = get_auth_session()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        workspace = user.active_workspace or os.path.basename(get_workspace_dir())
        ws_path = os.path.join(get_workspaces_root(), workspace)
        if os.path.isdir(os.path.join(ws_path, ".softwiki")):
            set_request_workspace(ws_path)

        if user.role != "admin":
            member = db.query(WorkspaceMember).filter_by(
                username=username, workspace=workspace
            ).first()
            if member is None and db.query(WorkspaceMember).count() > 0:
                return JSONResponse({"detail": "Workspace access denied"}, status_code=403)

        request.state.user = user
        return await call_next(request)
    finally:
        db.close()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.on_event("startup")
def warm_indexes():
    try:
        from softwiki.rag.vector_store import LocalVectorStore
        from softwiki.rag.bm25_store import Bm25Store
        LocalVectorStore()
        Bm25Store()
    except Exception as e:
        print(f"Index warmup skipped: {e}")


@app.on_event("startup")
def start_wiki_worker():
    if os.getenv("WIKI_REBUILD_WORKER", "0") not in ("1", "true", "yes"):
        return
    from softwiki.knowledge.wiki_queue import worker_loop
    threading.Thread(target=worker_loop, name="wiki-rebuild-worker", daemon=True).start()
    print("Wiki rebuild worker started")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
def login(req: LoginRequest):
    db = get_auth_session()
    try:
        user = db.query(User).filter(User.username == req.username).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = create_token(user.username)
        response = JSONResponse({
            "token": token,
            "username": user.username,
            "role": user.role,
            "workspace": user.active_workspace,
        })
        response.set_cookie("softwiki_session", token, httponly=True, samesite="lax")
        return response
    finally:
        db.close()


@app.post("/api/logout")
def logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("softwiki_session")
    return response


@app.get("/api/me")
def me(request: Request):
    if not auth_enabled():
        return {
            "auth": False,
            "username": None,
            "role": "anonymous",
            "workspace": os.path.basename(get_workspace_dir()),
        }
    user = getattr(request.state, "user", None)
    return {
        "auth": True,
        "username": user.username if user else None,
        "role": user.role if user else None,
        "workspace": user.active_workspace if user else None,
    }


class AskRequest(BaseModel):
    question: str
    workflow: Optional[str] = None
    mode: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None

class IngestUrlRequest(BaseModel):
    url: str
    source_id: Optional[str] = None

class WikiBuildRequest(BaseModel):
    topic: str

class WikiInterventionRequest(BaseModel):
    id: Optional[str] = None
    scope: str = "global"
    text: str = ""
    enabled: bool = True
    priority: int = 100

class WikiPreviewRequest(BaseModel):
    topic: Optional[str] = None
    topics: Optional[List[str]] = None
    intervention: Optional[str] = None
    include_saved: bool = True

class WikiApplyRequest(BaseModel):
    topics: List[str]
    intervention: Optional[str] = None
    include_saved: bool = True

class ConflictScanRequest(BaseModel):
    topic: Optional[str] = None

class ConflictAdjudicateRequest(BaseModel):
    action: str
    actor: str = "wiki-admin"
    reason: str = ""

@app.get("/api/status")
def get_status():
    """Returns database size, workspace folder, collections counts, and active modules."""
    db = SessionLocal()
    try:
        doc_count = db.query(Document).count()
        claim_count = db.query(Claim).count()
        chunk_count = db.query(Chunk).count()
        entity_count = db.query(Entity).count()
        rel_count = db.query(Relationship).count()
        event_count = db.query(Event).count()
        
        modules = {
            "rag": is_module_enabled("rag"),
            "graph": is_module_enabled("graph"),
            "claimdb": is_module_enabled("claimdb"),
            "timeline": is_module_enabled("timeline"),
            "llmwiki": is_module_enabled("llmwiki"),
        }
        
        return {
            "workspace": get_workspace_dir(),
            "database_url": _safe_db_url(),
            "counts": {
                "documents": doc_count,
                "chunks": chunk_count,
                "claims": claim_count,
                "entities": entity_count,
                "relationships": rel_count,
                "events": event_count
            },
            "modules": modules
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

def _build_sources(engine):
    rag_map = {}
    for result in getattr(engine, "last_search_results", []):
        doc = result.get("document")
        chunk = result.get("chunk")
        key = (
            getattr(doc, "id", None),
            getattr(chunk, "page_start", None),
            getattr(chunk, "page_end", None),
        )
        rag_map.setdefault(key, result)

    sources = []
    for citation in getattr(engine, "last_citations", []):
        key = (
            citation.get("doc_id"),
            citation.get("page_start"),
            citation.get("page_end"),
        )
        result = rag_map.get(key)
        sources.append({
            "citation_num": citation.get("num"),
            "title": citation.get("title"),
            "url": citation.get("url"),
            "source_name": citation.get("source_name"),
            "published_at": citation.get("published_at") or "Unknown",
            "page_start": citation.get("page_start"),
            "page_end": citation.get("page_end"),
            "text": result["chunk"].text if result else citation.get("text", ""),
            "score": float(result["score"]) if result else 0.0,
        })
    return sources


# ── Browser agent proxy (opencode web) ──────────────────────────────────────

class AgentAskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    agent: Optional[str] = None


class AgentSessionRequest(BaseModel):
    title: Optional[str] = None


def _agent_request(method: str, path: str, payload: Optional[dict] = None,
                   timeout: int = 60):
    url = f"{AGENT_WEB_URL}{path}"
    try:
        resp = requests.request(method, url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent unavailable at {AGENT_WEB_URL}: {exc}",
        ) from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise HTTPException(status_code=502, detail=f"Agent error: {detail}")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def _agent_tool_parts(messages: List[dict]) -> List[dict]:
    tools = []
    for msg in messages:
        for part in msg.get("parts", []):
            if part.get("type") != "tool":
                continue
            state = part.get("state") or {}
            output = state.get("output")
            if output is not None and not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)
            tools.append({
                "name": part.get("tool"),
                "status": state.get("status"),
                "input": state.get("input") or {},
                "output": (output or "")[:8000],
            })
    return tools


_SOURCE_RE = re.compile(
    r"^\[(?P<score>[0-9.]+)\]\s+(?P<title>.*?):\s+"
    r"\[Document:\s*(?P<doc>.*?)\s*\|\s*Source:\s*(?P<source>.*?)\s*\|\s*"
    r"Date:\s*(?P<date>.*?)\s*\|\s*Pages?:\s*(?P<page_start>\d+)"
    r"(?:-(?P<page_end>\d+))?\]",
    re.MULTILINE,
)


_ANSWER_REF_LINE_RE = re.compile(r"^\[(?P<num>\d+)\]\s*(?P<body>.+?)\s*$", re.MULTILINE)
_ANSWER_REF_INLINE_RE = re.compile(
    r"\[(?P<num>\d+)\]\s*\((?P<title>[^()\n]+?),\s*"
    r"(?:pp?\.\s*)?(?P<start>\d+)(?:\s*[-–]\s*(?P<end>\d+))?\)"
)


def _clean_ref_title(title: str) -> str:
    # Strip a trailing parenthesized date, e.g. "PCSA (2023-02-06" / "(2023-02-06)".
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)?\s*$", "", title)
    title = re.split(r",\s*(?:\d{4}-\d{2}-\d{2}|pp?\.)", title, maxsplit=1)[0]
    title = re.sub(r",\s*Manual Import\s*$", "", title)
    return title.strip(" ()")


def _lookup_doc_meta(title: str, start: int, end: int) -> dict | None:
    """Fill source metadata from the KB when the agent cites a page the
    top-k search payload did not include."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.title == title).first()
        if doc is None:
            doc = db.query(Document).filter(Document.title.contains(title)).first()
        if doc is None:
            return None
        published = doc.published_at.strftime("%Y-%m-%d") if doc.published_at else "Unknown"
        chunk = (
            db.query(Chunk)
            .filter(
                Chunk.document_id == doc.id,
                Chunk.page_start.isnot(None),
                Chunk.page_end.isnot(None),
                Chunk.page_start <= end,
                Chunk.page_end >= start,
            )
            .first()
        )
        if chunk is None:
            chunk = db.query(Chunk).filter(Chunk.document_id == doc.id).first()
        return {
            "title": doc.title,
            "source_name": doc.source_name or "Unknown",
            "published_at": published,
            "url": doc.url,
            "text": (chunk.text[:800] if chunk else ""),
        }
    except Exception:
        return None
    finally:
        db.close()


def _parse_answer_refs(answer: str) -> list[dict]:
    """Parse the agent's reference list, e.g.

    [1] ARM PrimeCell ... Manual, 2017-05-23, pp. 3-6, 23
    [6] ARM PrimeCell ... Manual, 2017-05-23, p. 23
    [4] (ARM PrimeCell ..., p. 23)
    """
    refs = []
    seen = set()
    for match in _ANSWER_REF_LINE_RE.finditer(answer or ""):
        num = int(match.group("num"))
        body = match.group("body").strip()
        if body.startswith("(") and body.endswith(")"):
            body = body[1:-1].strip()
        # Drop a trailing date/source so the title split is stable.
        title = _clean_ref_title(body)
        page_match = re.search(r"pp?\.\s*(\d+)(?:\s*[-–]\s*(\d+))?", body)
        if not title or not page_match:
            continue
        start = int(page_match.group(1))
        end = int(page_match.group(2) or start)
        key = (num, title, start, end)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"num": num, "title": title, "start": start, "end": end})

    # Also accept inline parenthesized citations, e.g. "[4] (Title, p. 23)".
    for match in _ANSWER_REF_INLINE_RE.finditer(answer or ""):
        num = int(match.group("num"))
        title = _clean_ref_title(match.group("title").strip())
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        key = (num, title, start, end)
        if key in seen:
            continue
        # A line reference already carries this citation; do not duplicate it.
        if any(r["num"] == num and r["start"] == start and r["end"] == end for r in refs):
            continue
        seen.add(key)
        refs.append({"num": num, "title": title, "start": start, "end": end})
    return refs



def _agent_sources(tools: List[dict], answer: str = "") -> List[dict]:
    tool_sources = []
    seen = set()
    for tool in tools:
        if tool.get("name") not in (
            "softwiki_search", "softwiki_retrieve", "softwiki_ask",
        ):
            continue
        output = tool.get("output") or ""
        for match in _SOURCE_RE.finditer(output):
            key = (
                match.group("title").strip(),
                match.group("page_start"),
                match.group("page_end"),
            )
            if key in seen:
                continue
            seen.add(key)
            page_start = int(match.group("page_start"))
            page_end = int(match.group("page_end") or page_start)
            tail = output[match.end():]
            chunk_text = tail.split("\n[", 1)[0].strip()[:800]
            tool_sources.append({
                "citation_num": len(tool_sources) + 1,
                "title": match.group("title").strip(),
                "url": None,
                "source_name": match.group("source").strip(),
                "published_at": match.group("date").strip(),
                "page_start": page_start,
                "page_end": page_end,
                "text": chunk_text,
                "score": float(match.group("score") or 0),
            })

    # If the agent wrote an explicit reference list, prefer it: its [n]
    # numbering is what the answer text actually uses.
    refs = _parse_answer_refs(answer or "")
    if not refs:
        return tool_sources

    result = []
    for ref in refs:
        title = ref["title"]
        start = ref["start"]
        end = ref["end"]
        match = next(
            (
                src for src in tool_sources
                if (src["title"] == title or title in src["title"] or src["title"] in title)
                and src["page_start"] <= end and src["page_end"] >= start
            ),
            None,
        )
        meta = None if match else _lookup_doc_meta(title, start, end)
        result.append({
            "citation_num": ref["num"],
            "title": title,
            "url": (match or meta or {}).get("url"),
            "source_name": (match or meta or {}).get("source_name", "Unknown"),
            "published_at": (match or meta or {}).get("published_at", "Unknown"),
            "page_start": start,
            "page_end": end,
            "text": (match or meta or {}).get("text", ""),
            # Agent citations are not ranked results. A retrieval score here
            # would be misleading as a confidence percentage, so the UI hides
            # it for every answer-parsed source.
            "score": None,
        })
    return result


def _agent_final_message(messages: List[dict], baseline: int) -> Optional[dict]:
    for msg in reversed(messages[baseline:]):
        info = msg.get("info") or {}
        if info.get("role") != "assistant":
            continue
        finish = info.get("finish")
        if info.get("error"):
            return msg
        if finish and finish != "tool-calls":
            return msg
    return None


def _agent_answer_text(message: dict) -> str:
    texts = []
    for part in message.get("parts", []):
        if part.get("type") == "text" and part.get("text"):
            texts.append(part["text"])
    return "\n\n".join(texts).strip()


@app.get("/api/agent/status")
def agent_status():
    """Health and agent inventory for the opencode browser agent."""
    try:
        agents = _agent_request("GET", "/agent", timeout=10) or []
        config = _agent_request("GET", "/config", timeout=10) or {}
        mcp = _agent_request("GET", "/mcp", timeout=10) or {}
    except HTTPException as exc:
        return JSONResponse(
            {"available": False, "url": AGENT_WEB_URL, "error": exc.detail},
            status_code=503,
        )
    primary = [
        {"name": a.get("name"), "description": a.get("description")}
        for a in agents
        if a.get("mode") == "primary"
    ]
    return {
        "available": True,
        "url": AGENT_WEB_URL,
        "agents": primary,
        "default_agent": config.get("default_agent"),
        "model": config.get("model"),
        "mcp": mcp,
    }


@app.post("/api/agent/session")
def agent_create_session(req: AgentSessionRequest):
    session = _agent_request("POST", "/session", {"title": req.title or "SoftWiki Agent"})
    return {"session_id": session.get("id"), "session": session}


@app.post("/api/agent/ask")
def agent_ask(req: AgentAskRequest):
    """Send a question to the opencode agent and wait for the final answer.

    Returns the answer, parsed KB sources, and every tool call (for the UI's
    research-step trail). This is the non-streaming L2 endpoint.
    """
    session_id = req.session_id
    if not session_id:
        session = _agent_request("POST", "/session", {"title": req.question[:60]})
        session_id = session.get("id")
    if not session_id:
        raise HTTPException(status_code=502, detail="Agent did not return a session id")

    baseline_messages = _agent_request(
        "GET", f"/session/{session_id}/message", timeout=30
    ) or []
    baseline = len(baseline_messages)

    try:
        _agent_request("POST", f"/session/{session_id}/message", {
            "agent": req.agent or AGENT_DEFAULT,
            "parts": [{"type": "text", "text": req.question}],
        }, timeout=AGENT_TIMEOUT)
    except HTTPException:
        # A long-running prompt may time out at the HTTP layer while the
        # agent is still working. Poll below; only fail if no message appears.
        pass

    deadline = time.time() + AGENT_TIMEOUT
    final = None
    messages = baseline_messages
    while time.time() < deadline:
        messages = _agent_request(
            "GET", f"/session/{session_id}/message", timeout=30
        ) or []
        final = _agent_final_message(messages, baseline)
        if final is not None:
            break
        time.sleep(1.5)

    if final is None:
        raise HTTPException(
            status_code=504,
            detail=f"Agent did not finish within {AGENT_TIMEOUT}s (session {session_id})",
        )

    info = final.get("info") or {}
    tools = _agent_tool_parts(messages[baseline:])
    answer = _agent_answer_text(final)
    error = info.get("error")
    if error:
        message = error.get("data", {}).get("message") if isinstance(error, dict) else str(error)
        return JSONResponse(
            {
                "session_id": session_id,
                "answer": "",
                "sources": _agent_sources(tools, answer),
                "tools": tools,
                "message_id": info.get("id"),
                "error": message or "Agent error",
            }
        )

    return {
        "session_id": session_id,
        "answer": answer,
        "sources": _agent_sources(tools, answer),
        "tools": tools,
        "message_id": info.get("id"),
    }


@app.post("/api/agent/session/{session_id}/abort")
def agent_abort(session_id: str):
    _agent_request("POST", f"/session/{session_id}/abort", timeout=15)
    return {"status": "aborted", "session_id": session_id}


@app.delete("/api/agent/session/{session_id}")
def agent_delete(session_id: str):
    _agent_request("DELETE", f"/session/{session_id}", timeout=15)
    return {"status": "deleted", "session_id": session_id}


@app.get("/api/knowledge/metrics")
def get_knowledge_metrics():
    db = SessionLocal()
    try:
        return knowledge_metrics(db)
    finally:
        db.close()


@app.get("/api/conflicts")
def get_conflicts(status: Optional[str] = None):
    db = SessionLocal()
    try:
        return {"conflicts": list_conflicts(db, status=status)}
    finally:
        db.close()


@app.post("/api/conflicts/scan")
def scan_knowledge_conflicts(req: ConflictScanRequest):
    check_read_only()
    db = SessionLocal()
    try:
        return scan_conflicts(db, topic=req.topic)
    finally:
        db.close()


@app.post("/api/conflicts/{conflict_id}/adjudicate")
def adjudicate_conflict(conflict_id: int, req: ConflictAdjudicateRequest):
    check_read_only()
    db = SessionLocal()
    try:
        try:
            return adjudicate(db, conflict_id, req.action, actor=req.actor, reason=req.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.get("/api/canonical-claims")
def list_canonical_claims(status: Optional[str] = None, topic: Optional[str] = None,
                          limit: int = 100):
    db = SessionLocal()
    try:
        query = db.query(CanonicalClaim).order_by(CanonicalClaim.updated_at.desc())
        if status:
            query = query.filter(CanonicalClaim.status == status)
        if topic:
            query = query.filter(CanonicalClaim.topic == topic)
        rows = query.limit(min(max(limit, 1), 500)).all()
        return {"claims": [
            {
                "id": c.id,
                "text": c.text,
                "actor": c.actor,
                "topic": c.topic,
                "stance": c.stance,
                "confidence": c.confidence,
                "status": c.status,
                "value_normalized": c.value_normalized,
                "subject": c.subject,
                "predicate": c.predicate,
                "object": c.object,
                "qualifiers": c.qualifiers,
                "structure_hash": c.structure_hash,
                "evidence_count": c.evidence_count,
                "primary_document_id": c.primary_document_id,
                "primary_page_start": c.primary_page_start,
                "primary_page_end": c.primary_page_end,
                "valid_from": c.valid_from.isoformat() if c.valid_from else None,
                "valid_to": c.valid_to.isoformat() if c.valid_to else None,
            }
            for c in rows
        ]}
    finally:
        db.close()


@app.get("/api/canonical-claims/{claim_id}/evidence")
def canonical_claim_evidence(claim_id: str):
    db = SessionLocal()
    try:
        rows = db.query(ClaimEvidence).filter(ClaimEvidence.canonical_id == claim_id).all()
        return {"evidence": [
            {
                "id": e.id,
                "claim_id": e.claim_id,
                "document_id": e.document_id,
                "page_start": e.page_start,
                "page_end": e.page_end,
                "quote": e.quote,
                "source_name": e.source_name,
                "source_revision": e.source_revision,
                "trust_level": e.trust_level,
                "published_at": e.published_at.isoformat() if e.published_at else None,
            }
            for e in rows
        ]}
    finally:
        db.close()


@app.post("/api/ask")
def ask_question(req: AskRequest):
    """Executes CJK-aware hybrid search and synthesizes an answer using LLM."""
    db = SessionLocal()
    try:
        engine = AnswerEngine()
        answer = engine.ask(
            db,
            req.question,
            history=req.history,
            workflow=req.workflow,
            mode=req.mode or "normal",
        )
        return {
            "answer": answer,
            "sources": _build_sources(engine),
            "mode": req.mode or "normal",
            "workflow": req.workflow,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

class ReportRequest(BaseModel):
    question: str
    template: str = "research-report"
    workflow: Optional[str] = None


@app.post("/api/report")
def create_report(req: ReportRequest):
    check_read_only()
    from softwiki.intelligence.report import generate_report
    db = SessionLocal()
    try:
        return generate_report(db, req.question, req.template, workflow=req.workflow)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/report/{report_id}")
def download_report(report_id: str):
    safe = os.path.basename(report_id)
    path = os.path.join(get_export_dir("reports"), safe, "report.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="text/markdown", filename=f"{safe}.md")


@app.get("/api/report/{report_id}/manifest")
def report_manifest(report_id: str):
    safe = os.path.basename(report_id)
    path = os.path.join(get_export_dir("reports"), safe, "manifest.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.post("/api/ingest/url")
def ingest_url(req: IngestUrlRequest):
    """Ingest a web URL into the active workspace database and extracts claims."""
    check_read_only()
    db = SessionLocal()
    try:
        source_meta = {}
        if req.source_id:
            src_config = DocumentRepository.get_source_config(db, req.source_id)
            if src_config:
                source_meta = {
                    "source_name": src_config.name,
                    "source_type": src_config.type,
                    "source_country": src_config.source_country,
                    "trust_level": src_config.trust_level,
                    "language": src_config.language
                }
                
        content = extract_web_content(req.url)
        content["url"] = req.url
        
        title = content["title"]
        author = content["author"]
        raw_text = content["raw_text"]
        cleaned_text = content["cleaned_text"]
        published_at = content["published_at"]
        
        # Check scope
        from softwiki.intelligence.scope_guard import check_scope
        is_in_scope, reason = check_scope(f"Title: {title}\nContent:\n{cleaned_text[:2000]}", item_type="document")
        if not is_in_scope:
            return {"status": "skipped", "reason": f"out of scope: {reason}"}
            
        text_hash = calculate_hash(cleaned_text)
        if is_duplicate_hash(db, text_hash):
            return {"status": "skipped", "reason": "content hash duplicate"}
        existing_url = DocumentRepository.get_document_by_url(db, req.url) if req.url else None
        if existing_url and existing_url.hash == text_hash:
            return {"status": "skipped", "reason": "url and content duplicate"}
            
        doc = Document(
            title=title,
            url=req.url,
            source_name=source_meta.get("source_name", "Manual Import"),
            source_type=source_meta.get("source_type", "manual_import"),
            source_country=source_meta.get("source_country", "unknown"),
            trust_level=source_meta.get("trust_level", "medium"),
            language=source_meta.get("language", "en"),
            author=author,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            hash=text_hash,
            published_at=published_at,
            collected_at=datetime.utcnow()
        )
        assign_document_version(db, doc)
        doc = DocumentRepository.create_document(db, doc)
        assign_document_version(db, doc)
        db.commit()
        
        # Run extraction pipeline in background
        run_extraction_pipeline(db, doc.id, cleaned_text, published_at, background=True)
            
        return {
            "status": "success",
            "document_id": doc.id,
            "title": doc.title,
            "extraction": "pending"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/ingest/file")
def ingest_file(file: UploadFile = File(...), source_id: Optional[str] = Form(None)):
    """Uploads a PDF file, saves it to workspace, and extracts claims."""
    check_read_only()
    db = SessionLocal()
    try:
        # Resolve destination path in workspace raw/pdf directory
        raw_pdf_dir = os.path.join(get_workspace_dir(), "raw", "pdf")
        os.makedirs(raw_pdf_dir, exist_ok=True)
        dest_path = os.path.join(raw_pdf_dir, file.filename)
        
        # Save file to disk
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        source_meta = {}
        if source_id:
            src_config = DocumentRepository.get_source_config(db, source_id)
            if src_config:
                source_meta = {
                    "source_name": src_config.name,
                    "source_type": src_config.type,
                    "source_country": src_config.source_country,
                    "trust_level": src_config.trust_level,
                    "language": src_config.language
                }
                
        # Handle markdown files directly (read as plain text)
        if file.filename and file.filename.lower().endswith(".md"):
            raw_md_dir = os.path.join(get_workspace_dir(), "raw", "md")
            os.makedirs(raw_md_dir, exist_ok=True)
            md_dest = os.path.join(raw_md_dir, file.filename)
            # Save to raw/md first
            with open(dest_path, "r", encoding="utf-8") as src, open(md_dest, "w", encoding="utf-8") as dst:
                md_text = src.read()
                dst.write(md_text)
            title = os.path.splitext(file.filename)[0]
            content = {
                "title": title,
                "author": "Unknown",
                "raw_text": md_text,
                "cleaned_text": md_text,
                "published_at": None,
            }
        else:
            content = extract_pdf_content(dest_path)
        content["url"] = None
        
        title = content["title"] or file.filename
        author = content["author"]
        raw_text = content["raw_text"]
        cleaned_text = content["cleaned_text"]
        published_at = content["published_at"]
        
        # Check scope
        from softwiki.intelligence.scope_guard import check_scope
        is_in_scope, reason = check_scope(f"Title: {title}\nContent:\n{cleaned_text[:2000]}", item_type="document")
        if not is_in_scope:
            return {"status": "skipped", "reason": f"out of scope: {reason}"}
            
        text_hash = calculate_hash(cleaned_text)
        if is_duplicate_hash(db, text_hash):
            return {"status": "skipped", "reason": "content hash duplicate"}
            
        doc = Document(
            title=title,
            url=None,
            source_name=source_meta.get("source_name", "Manual Import"),
            source_type=source_meta.get("source_type", "manual_import"),
            source_country=source_meta.get("source_country", "unknown"),
            trust_level=source_meta.get("trust_level", "medium"),
            language=source_meta.get("language", "en"),
            author=author,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            hash=text_hash,
            published_at=published_at,
            collected_at=datetime.utcnow()
        )
        assign_document_version(db, doc)
        doc = DocumentRepository.create_document(db, doc)
        assign_document_version(db, doc)
        db.commit()
        
        # Run extraction pipeline in background
        run_extraction_pipeline(db, doc.id, cleaned_text, published_at, background=True)
            
        return {
            "status": "success",
            "document_id": doc.id,
            "title": doc.title,
            "extraction": "pending"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/index")
def rebuild_index():
    """Chunk all documents and rebuild dense embeddings and BM25 index files."""
    check_read_only()
    db = SessionLocal()
    try:
        documents = DocumentRepository.get_all_documents(db)
        if not documents:
            return {"status": "success", "indexed_chunks": 0, "message": "No documents to index."}
            
        for doc in documents:
            DocumentRepository.delete_document_chunks(db, doc.id)
            meta = {
                "title": doc.title,
                "source_name": doc.source_name,
                "published_at": doc.published_at
            }
            chunks_data = build_document_chunks(doc.id, doc.cleaned_text, meta)
            
            db_chunks = DocumentRepository.build_chunk_models(chunks_data)
            DocumentRepository.create_chunks(db, db_chunks)
            
        all_chunks = DocumentRepository.get_all_chunks(db)
        embedder = WikiEmbedder()
        vector_store = LocalVectorStore()
        
        chunk_ids = [c.id for c in all_chunks]
        chunk_texts = [c.text for c in all_chunks]
        
        embeddings = embedder.embed_texts(chunk_texts)
        if os.path.exists(vector_store.get_current_path()):
            os.remove(vector_store.get_current_path())
        vector_store.reset()

        vector_store.add_vectors(chunk_ids, embeddings)
        
        bm25_store = Bm25Store()
        chunk_id_to_text = {c.id: c.text for c in all_chunks}
        bm25_store.rebuild_index(chunk_id_to_text)
        
        return {
            "status": "success",
            "indexed_chunks": len(all_chunks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/wiki/rebuild-tasks")
def list_wiki_rebuild_tasks(status: Optional[str] = None, limit: int = 50):
    from softwiki.source_store.models import WikiRebuildTask
    db = SessionLocal()
    try:
        q = db.query(WikiRebuildTask).order_by(WikiRebuildTask.created_at.desc())
        if status:
            q = q.filter(WikiRebuildTask.status == status)
        rows = q.limit(min(max(limit, 1), 200)).all()
        return {
            "tasks": [
                {
                    "id": t.id,
                    "topic": t.topic,
                    "reason": t.reason,
                    "status": t.status,
                    "attempts": t.attempts,
                    "max_attempts": t.max_attempts,
                    "error": t.error,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "finished_at": t.finished_at.isoformat() if t.finished_at else None,
                }
                for t in rows
            ],
            "counts": pending_count(db),
        }
    finally:
        db.close()


@app.post("/api/wiki/rebuild-stale")
def rebuild_stale_wiki():
    check_read_only()
    db = SessionLocal()
    try:
        created = enqueue_stale_wiki(db)
        return {"enqueued": created, "counts": pending_count(db)}
    finally:
        db.close()


@app.get("/api/wiki/topics")
def list_wiki_topics():
    """Lists available topics defined in topics.yaml."""
    import yaml
    topics_path = get_config_path("topics.yaml")
    if not os.path.exists(topics_path):
        db = SessionLocal()
        try:
            unique_topics = db.query(Claim.topic).distinct().all()
            topics_dict = {}
            for row in unique_topics:
                t = row[0]
                if t and t != "general":
                    topics_dict[t] = {
                        "aliases": [t],
                        "related": []
                    }
            return JSONResponse(
                {"topics": topics_dict},
                headers={"Cache-Control": "no-store"},
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()
        
    try:
        with open(topics_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return JSONResponse(data, headers={"Cache-Control": "no-store"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/wiki/coverage")
def wiki_claim_coverage():
    """Claim coverage against the curated topics.yaml map (canonical + aliases)."""
    db = SessionLocal()
    try:
        return compute_coverage(db)
    finally:
        db.close()


@app.get("/api/wiki/interventions")
def get_wiki_interventions():
    """List saved prompt interventions (global / group / topic scopes)."""
    return {"interventions": list_interventions()}


@app.post("/api/wiki/interventions")
def create_or_update_wiki_intervention(req: WikiInterventionRequest):
    try:
        saved = save_intervention(
            scope=req.scope,
            text=req.text,
            intervention_id=req.id,
            enabled=req.enabled,
            priority=req.priority,
        )
        return {"status": "success", "intervention": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/wiki/interventions/{intervention_id}")
def remove_wiki_intervention(intervention_id: str):
    if not delete_intervention(intervention_id):
        raise HTTPException(status_code=404, detail="Intervention not found")
    return {"status": "deleted", "id": intervention_id}


def _preview_diagnostics(content: str, generator, elapsed_ms: int) -> dict:
    headings = [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for m in re.finditer(r"^(#{1,4})\s+(.+)$", content or "", re.MULTILINE)
    ]
    citations = len(re.findall(r"\[\d+\]", content or ""))
    warnings = []
    if generator.last_fallback:
        warnings.append("LLM unavailable or failed; fallback template used, intervention was not applied.")
    if not headings:
        warnings.append("No markdown headings detected.")
    if citations == 0:
        warnings.append("No [n] citations detected.")
    if "UNDEF" in (content or ""):
        warnings.append("Output contains UNDEF placeholders.")
    return {
        "headings": headings,
        "citation_count": citations,
        "warnings": warnings,
        "elapsed_ms": elapsed_ms,
        "model": generator.last_model,
        "fallback": generator.last_fallback,
        "claims_total": getattr(generator, "last_claims_total", 0),
        "claims_used": getattr(generator, "last_claims_used", 0),
    }


@app.post("/api/wiki/preview")
def preview_wiki_page(req: WikiPreviewRequest):
    """Generate preview pages without touching canonical wiki files.

    This is the closed-loop testing endpoint: change the optional intervention,
    preview selected topics, inspect, and iterate.
    """
    topics = [t.strip() for t in (req.topics or ([req.topic] if req.topic else [])) if t and t.strip()]
    if not topics:
        raise HTTPException(status_code=400, detail="Provide topic or topics")
    if len(topics) > 3:
        raise HTTPException(status_code=400, detail="Preview at most 3 topics per run")

    run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    out_dir = preview_dir(run_id)
    db = SessionLocal()
    results = []
    try:
        for topic in topics:
            started = datetime.utcnow()
            generator = WikiPageGenerator()
            intervention = compose_interventions(
                topic, adhoc=req.intervention or "", include_saved=req.include_saved
            )
            try:
                path = generator.generate_topic_page(
                    db,
                    topic,
                    force_rebuild=True,
                    intervention=intervention,
                    output_dir=out_dir,
                )
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
                diag = _preview_diagnostics(content, generator, elapsed_ms)
                results.append({
                    "topic": topic,
                    "preview_path": path,
                    "content": content,
                    "intervention_applied": bool(intervention),
                    "intervention_chars": len(intervention),
                    **diag,
                })
            except Exception as e:
                results.append({"topic": topic, "error": str(e)})
        return {"run_id": run_id, "preview_dir": out_dir, "results": results}
    finally:
        db.close()


@app.post("/api/wiki/apply")
def apply_wiki_interventions(req: WikiApplyRequest):
    """Write canonical wiki pages using saved + ad-hoc interventions.

    Preview first, then apply. The caller is responsible for choosing topics.
    """
    check_read_only()
    topics = [t.strip() for t in req.topics if t and t.strip()]
    if not topics:
        raise HTTPException(status_code=400, detail="Provide topics")
    db = SessionLocal()
    results = []
    try:
        for topic in topics:
            started = datetime.utcnow()
            generator = WikiPageGenerator()
            intervention = compose_interventions(
                topic, adhoc=req.intervention or "", include_saved=req.include_saved
            )
            try:
                path = generator.generate_topic_page(
                    db, topic, force_rebuild=True, intervention=intervention
                )
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
                results.append({
                    "topic": topic,
                    "filepath": path,
                    "content": content,
                    "intervention_applied": bool(intervention),
                    "model": generator.last_model,
                    "fallback": generator.last_fallback,
                    "claims_total": getattr(generator, "last_claims_total", 0),
                    "claims_used": getattr(generator, "last_claims_used", 0),
                    "elapsed_ms": elapsed_ms,
                })
            except Exception as e:
                results.append({"topic": topic, "error": str(e)})
        return {"status": "success", "results": results}
    finally:
        db.close()


@app.post("/api/wiki/build")
def build_wiki_page(req: WikiBuildRequest):
    """Generates and writes topic wiki page to workspace exports."""
    if os.getenv("SOFTWIKI_MODE") in ["study", "wiki-study"]:
        raise HTTPException(status_code=403, detail="Wiki compilation is disabled in study mode.")
    db = SessionLocal()
    try:
        generator = WikiPageGenerator()
        filepath = generator.generate_topic_page(db, req.topic)
        
        # Read the file to return its markdown content
        content = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
        return {
            "status": "success",
            "filepath": filepath,
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/wiki/page/{topic}")
def get_wiki_page(topic: str):
    """Read an already-generated wiki page without rebuilding it."""
    
    export_dir = get_export_dir("wiki/topics")
    filepath = os.path.join(export_dir, f"{topic}.md")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Wiki page '{topic}' not found. Build it first.")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    import time
    mtime = os.path.getmtime(filepath)
    db = SessionLocal()
    try:
        state = db.query(WikiArtifactState).filter(WikiArtifactState.topic == topic).first()
        stale = bool(state and state.stale_at)
        stale_at = state.stale_at.isoformat() if state and state.stale_at else None
    finally:
        db.close()
    return {
        "topic": topic,
        "content": content,
        "filepath": filepath,
        "built_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
        "stale": stale,
        "stale_at": stale_at,
    }


@app.get("/api/wiki/history/{topic}")
def get_wiki_history(topic: str, limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.query(WikiArtifactVersion).filter(
            WikiArtifactVersion.topic == topic
        ).order_by(WikiArtifactVersion.created_at.desc()).limit(min(max(limit, 1), 200)).all()
        return {"versions": [
            {
                "id": v.id,
                "topic": v.topic,
                "content_hash": v.content_hash,
                "claim_set_hash": v.claim_set_hash,
                "prompt_version": v.prompt_version,
                "model": v.model,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in rows
        ]}
    finally:
        db.close()


@app.get("/api/wiki/history/{topic}/{version_id}")
def get_wiki_history_version(topic: str, version_id: int):
    db = SessionLocal()
    try:
        v = db.query(WikiArtifactVersion).filter(
            WikiArtifactVersion.id == version_id,
            WikiArtifactVersion.topic == topic,
        ).first()
        if v is None:
            raise HTTPException(status_code=404, detail="Wiki history version not found")
        return {
            "id": v.id,
            "topic": v.topic,
            "content": v.content,
            "content_hash": v.content_hash,
            "claim_set_hash": v.claim_set_hash,
            "prompt_version": v.prompt_version,
            "model": v.model,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
    finally:
        db.close()


@app.get("/api/documents")
def list_documents():
    """Lists all ingested documents with metadata."""
    db = SessionLocal()
    try:
        documents = db.query(Document).order_by(Document.id.desc()).all()
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "source_name": doc.source_name,
                "source_type": doc.source_type,
                "published_at": doc.published_at.strftime('%Y-%m-%d') if doc.published_at else "Unknown",
                "collected_at": doc.collected_at.strftime('%Y-%m-%d') if doc.collected_at else "Unknown",
                "author": doc.author,
                "trust_level": doc.trust_level
            }
            for doc in documents
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/claims")
def list_claims():
    """Lists all extracted claims with actor and stance."""
    db = SessionLocal()
    try:
        claims = db.query(Claim).order_by(Claim.published_at.desc()).all()
        return [
            {
                "id": c.id,
                "document_id": c.document_id,
                "text": c.text,
                "actor": c.actor,
                "topic": c.topic,
                "stance": c.stance,
                "confidence": c.confidence,
                "published_at": c.published_at.strftime('%Y-%m-%d') if c.published_at else "Unknown"
            }
            for c in claims
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int):
    """Deletes a document from the database (cascade deletes chunks, claims, events, relationships)."""
    check_read_only()
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        db.delete(doc)
        db.commit()
        return {"status": "success", "message": f"Document {doc_id} successfully deleted."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/timeline")
def list_timeline():
    """Lists all timeline events sorted chronologically."""
    db = SessionLocal()
    try:
        events = db.query(Event).filter(Event.status == "active").order_by(Event.event_date.asc()).all()
        return [
            {
                "id": ev.id,
                "title": ev.title,
                "description": ev.description,
                "event_date": ev.event_date.strftime('%Y-%m-%d') if ev.event_date else "Unknown",
                "topic": ev.topic,
                "document_id": ev.document_id,
                "confidence": ev.confidence
            }
            for ev in events
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/graph")
def list_graph():
    """Lists entities and relationships forming the knowledge graph."""
    db = SessionLocal()
    try:
        entities = db.query(Entity).all()
        relationships = db.query(Relationship).filter(Relationship.status == "active").all()
        return {
            "entities": [
                {
                    "id": ent.id,
                    "name": ent.name,
                    "type": ent.type,
                    "description": ent.description
                }
                for ent in entities
            ],
            "relationships": [
                {
                    "id": rel.id,
                    "source_name": rel.source_name,
                    "target_name": rel.target_name,
                    "relation_type": rel.relation_type,
                    "description": rel.description,
                    "document_id": rel.document_id,
                    "confidence": rel.confidence,
                    "published_at": rel.published_at.strftime('%Y-%m-%d') if rel.published_at else "Unknown"
                }
                for rel in relationships
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/modules")
def list_modules():
    """Returns status of all modular subsystems."""
    return {
        "rag": is_module_enabled("rag"),
        "graph": is_module_enabled("graph"),
        "claimdb": is_module_enabled("claimdb"),
        "timeline": is_module_enabled("timeline"),
        "llmwiki": is_module_enabled("llmwiki")
    }

# ── Workspace management ──

@app.get("/api/workflows")
def list_workflows():
    from softwiki.intelligence.workflows import load_workflows
    return {"workflows": load_workflows()}


@app.get("/api/workspaces")
def get_workspaces():
    """List all available workspaces and indicate which is active."""
    all_ws = list_workspaces()
    active = os.path.basename(get_workspace_dir())
    return {"workspaces": all_ws, "active": active}

class WorkspaceSwitchRequest(BaseModel):
    workspace: str

@app.post("/api/workspace")
def switch_workspace(req: WorkspaceSwitchRequest, request: Request):
    """Switch the active workspace at runtime."""
    ws_path = os.path.join(get_workspaces_root(), req.workspace)
    ws_path = os.path.abspath(ws_path)
    if not os.path.isdir(os.path.join(ws_path, ".softwiki")):
        raise HTTPException(status_code=404, detail=f"Workspace '{req.workspace}' not found or not initialized.")

    if auth_enabled():
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        db = get_auth_session()
        try:
            if user.role != "admin":
                member = db.query(WorkspaceMember).filter_by(
                    username=user.username, workspace=req.workspace
                ).first()
                if member is None and db.query(WorkspaceMember).count() > 0:
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            db.query(User).filter(User.id == user.id).update(
                {"active_workspace": req.workspace}
            )
            db.commit()
        finally:
            db.close()
        set_request_workspace(ws_path)
    else:
        set_workspace_dir(ws_path)

    return {"status": "ok", "workspace": get_workspace_dir()}

# ── Standalone Wiki (no dashboard required) ──

_WIKI_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #202122; background: #f8f9fa; }
.wrapper { display: flex; height: 100vh; }
.sidebar { width: 220px; min-width: 220px; background: #fff; border-right: 1px solid #a2a9b1; display: flex; flex-direction: column; overflow: hidden; }
.sidebar-header { padding: 14px 16px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #54595d; border-bottom: 1px solid #eaecf0; }
.sidebar-body { flex: 1; overflow-y: auto; padding: 4px 0; }
.sidebar-group-label { padding: 6px 16px 2px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #72777d; }
.sidebar-item { display: block; padding: 5px 16px 5px 20px; color: #0645ad; text-decoration: none; font-size: 13px; }
.sidebar-item:hover { background: #eaf3fb; text-decoration: underline; }
.sidebar-item.active { background: #eaf3fb; color: #202122; font-weight: 600; }
.sidebar-ws { padding: 8px 12px; border-bottom: 1px solid #eaecf0; }
.ws-select { width: 100%; font-size: 12px; padding: 4px 6px; border: 1px solid #a2a9b1; border-radius: 2px; font-family: inherit; background: #fff; cursor: pointer; }
.article { flex: 1; overflow-y: auto; padding: 24px 48px 80px; max-width: 860px; margin: 0 auto; width: 100%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.article h1 { font-size: 28px; font-weight: 400; border-bottom: 1px solid #a2a9b1; padding-bottom: 6px; margin-bottom: 16px; font-family: Georgia, 'Linux Libertine', serif; }
.article h2 { font-size: 20px; font-weight: 400; border-bottom: 1px solid #a2a9b1; padding-bottom: 4px; margin: 1em 0 0.5em; font-family: Georgia, 'Linux Libertine', serif; }
.article h3 { font-size: 16px; font-weight: 600; margin: 1em 0 0.4em; }
.article p { margin: 0.5em 0; line-height: 1.65; font-family: Georgia, 'Linux Libertine', serif; font-size: 14px; }
.article ul, .article ol { padding-left: 30px; margin: 0.4em 0; }
.article a { color: #0645ad; text-decoration: none; }
.article a:hover { text-decoration: underline; }
.article code { background: #f8f9fa; padding: 1px 4px; border: 1px solid #eaecf0; font-size: 13px; font-family: 'Consolas', 'Courier New', monospace; }
.article pre { background: #f8f9fa; border: 1px solid #a2a9b1; padding: 12px 16px; overflow-x: auto; margin: 1em 0; }
.article table { border-collapse: collapse; margin: 1em 0; font-size: 13px; width: 100%; }
.article th, .article td { border: 1px solid #a2a9b1; padding: 6px 10px; text-align: left; }
.article th { background: #eaecf0; font-weight: 700; }
.article tr:nth-child(even) { background: #f8f9fa; }
.article .meta { font-size: 12px; color: #54595d; margin-bottom: 16px; }
.footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #a2a9b1; font-size: 11px; color: #54595d; }
"""

def _build_sidebar(topics: dict, active: str = "") -> str:
    items = ""
    groups = {}
    for key, info in topics.items():
        g = info.get("group", "Other")
        groups.setdefault(g, []).append((key, info.get("name", key)))
    for g, ks in groups.items():
        items += f'<div class="sidebar-group-label">{g}</div>'
        for key, name in ks:
            cls = ' active' if key == active else ''
            items += f'<a class="sidebar-item{cls}" href="/wiki/{key}">{name}</a>'

    # Build workspace switcher
    ws_name = os.path.basename(get_workspace_dir())
    all_ws = list_workspaces()
    ws_opts = ""
    for w in all_ws:
        sel = " selected" if w == ws_name else ""
        ws_opts += f'<option value="{w}"{sel}>{w}</option>'
    switcher = f"""<div class="sidebar-ws">
<form method="POST" action="/wiki/switch" id="ws-form">
<select name="workspace" onchange="document.getElementById('ws-form').submit()" class="ws-select">{ws_opts}</select>
</form></div>"""
    return switcher + items

@app.get("/wiki", response_class=HTMLResponse)
def wiki_index():
    import yaml
    topics_path = get_config_path("topics.yaml")
    ws_name = os.path.basename(get_workspace_dir())
    if not os.path.exists(topics_path):
        return HTMLResponse(f"<html><body><h1>{ws_name}</h1><p>No topics configured.</p></body></html>")
    with open(topics_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    topics = data.get("topics", data)
    sidebar = _build_sidebar(topics)
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{ws_name} — Wiki</title>
<style>{_WIKI_CSS}</style></head><body><div class="wrapper">
<div class="sidebar"><div class="sidebar-header">Topics</div><div class="sidebar-body">{sidebar}</div></div>
<div class="article"><h1>{ws_name}</h1><p>Select a topic from the sidebar.</p><div class="footer">SoftWiki</div></div>
</div></body></html>""")

@app.post("/wiki/switch")
def wiki_switch_workspace(workspace: str = Form(...)):
    """Switch workspace from the wiki UI."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ws_path = os.path.join(project_root, "workspace", workspace)
    ws_path = os.path.abspath(ws_path)
    if os.path.isdir(os.path.join(ws_path, ".softwiki")):
        set_workspace_dir(ws_path)
    return RedirectResponse(url="/wiki", status_code=302)

@app.get("/wiki/{topic}", response_class=HTMLResponse)
def wiki_page(topic: str):
    import yaml, markdown, re
    topics_path = get_config_path("topics.yaml")
    export_dir = get_export_dir("wiki/topics")
    filepath = os.path.join(export_dir, f"{topic}.md")
    ws_name = os.path.basename(get_workspace_dir())

    topics = {}
    if os.path.exists(topics_path):
        with open(topics_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        topics = data.get("topics", data)
    sidebar = _build_sidebar(topics, active=topic)

    if not os.path.exists(filepath):
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Not Found</title>
<style>{_WIKI_CSS}</style></head><body><div class="wrapper">
<div class="sidebar"><div class="sidebar-header">Topics</div><div class="sidebar-body">{sidebar}</div></div>
<div class="article"><h1>Not Found</h1><p>Wiki page &quot;{topic}&quot; not found.</p>
<div class="footer"><a href="/wiki">← Back</a> · SoftWiki</div></div></div></body></html>""", status_code=404)

    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'\[([^\]]+)\]\(wiki://([^)]+)\)', r'[\1](/wiki/\2)', content)
    html_body = markdown.markdown(content, extensions=['extra', 'tables', 'fenced_code'])

    title = topic.replace("-", " ").title()
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title} — {ws_name}</title>
<style>{_WIKI_CSS}</style></head><body><div class="wrapper">
<div class="sidebar"><div class="sidebar-header">Topics</div><div class="sidebar-body">{sidebar}</div></div>
<div class="article"><div class="meta"><a href="/wiki">← Back</a></div>
{html_body}
<div class="footer"><a href="/wiki/{topic}?raw=1">Source</a> · SoftWiki</div></div>
</div></body></html>""")

