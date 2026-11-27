from __future__ import annotations

import asyncio
import contextlib
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
from urllib.parse import urlparse
import httpx
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, StreamingResponse
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
from softwiki.knowledge.nli import judge_candidates
from softwiki.knowledge.cleanup import delete_document_knowledge
from softwiki.permissions import (
    ROLE_ORDER,
    SENSITIVE_CAPABILITIES,
    can,
    current_role,
    granted_role,
    is_sensitive,
    normalize_role,
    reset_downgrade,
    reset_role,
    role_capabilities,
    role_level,
    set_downgrade,
    set_role,
)
from softwiki import audit, netacl
from softwiki.identity import (
    IdentityDenied,
    RequestIdentity,
    UserStore,
    auth_mode,
    check_reauth,
    close_superuser,
    current_identity,
    is_local_address,
    open_superuser,
    reset_context,
    set_context,
    superuser_session,
)
from softwiki.identity.superuser import SuperuserDenied
from softwiki.extraction.processor import run_extraction_pipeline
from softwiki.rag.chunker import build_document_chunks
from softwiki.rag.embedder import WikiEmbedder
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.rag.hybrid_search import HybridSearcher
from softwiki.rag.citations import CitationManager
from softwiki.intelligence.answer_engine import AnswerEngine
from softwiki.intelligence.citation_check import verify_citations
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

AGENT_WEB_URL = (os.getenv("SWAGENT_URL") or os.getenv("AGENT_WEB_URL") or "http://127.0.0.1:6111").rstrip("/")
AGENT_DEFAULT = os.getenv("SWAGENT_DEFAULT") or os.getenv("AGENT_DEFAULT") or "wiki-research"
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "300"))
# opencode serves the global event stream at /global/event (v1) or /event.
AGENT_EVENT_PATH = os.getenv("SWAGENT_EVENT_PATH") or os.getenv("AGENT_EVENT_PATH") or "/global/event"
AGENT_EVENT_HEARTBEAT = float(os.getenv("SWAGENT_EVENT_HEARTBEAT", "15"))

def _safe_db_url():
    try:
        return make_url(get_db_url()).render_as_string(hide_password=True)
    except Exception:
        return "unknown"

def require_capability(capability: str):
    if not can(capability):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{current_role()}' does not allow '{capability}' "
                "(write operations are disabled in study/work modes; "
                "wiki compilation is disabled in study mode)."
            ),
        )

def check_read_only():
    # Backward-compatible alias: callers should prefer require_capability().
    if not can("ingest.write") and not can("index.write") and not can("wiki.apply"):
        raise HTTPException(status_code=403, detail="Write operations are disabled for this role.")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_AUTH_EXEMPT = {
    "/api/login",
    "/api/health",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/auth/providers",
    "/api/auth/login",
    "/api/auth/password",
    "/api/auth/me",
    "/api/auth/superuser",
    "/api/kb",
    "/api/kb/templates",
}

#: Read-only paths never enter the audit log (docs/02-design/auth-oidc.md §7).
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _client_ip(request: Request) -> Optional[str]:
    """Peer address of the connection.

    Deliberately *not* ``X-Forwarded-For``: that header is client-controlled,
    and "what counts as local" is a security decision, not a convenience.
    """
    return request.client.host if request.client else None


def _identity_for_request(request: Request) -> RequestIdentity:
    """Resolve who is calling, per ``SOFTWIKI_AUTH_MODE``."""
    peer = _client_ip(request)
    mode = auth_mode()

    if mode == "off":
        # No identity system: the machine is the superuser. Still give it a row
        # so that kb_scope / override / audit have a concrete owner.
        store = UserStore()
        try:
            user = store.ensure_superuser_row()
            authz = store.authorize_user(user)
        except Exception as exc:  # noqa: BLE001 - a broken table must not lock the operator out
            print(f"[auth] falling back to implicit superuser: {exc}", flush=True)
            return RequestIdentity(source_ip=peer, superuser=True)
        return RequestIdentity(authorization=authz, source_ip=peer, superuser=True)

    # local / oidc / proxy: the identity must have been established by the
    # auth routes — except `proxy`, where a forward-auth proxy has already
    # authenticated the user and injected headers. Headers are only honoured
    # when the TCP peer is a configured trusted proxy, so a direct call cannot
    # forge an identity (see softwiki/identity/proxy.py).
    if mode == "proxy":
        from softwiki.identity.proxy import identity_from_headers

        external = identity_from_headers(request.headers, peer)
        if external is not None:
            store = UserStore()
            try:
                authz = store.authorize(external)
            except IdentityDenied:
                return RequestIdentity(source_ip=peer)
            request.state.identity = RequestIdentity(
                authorization=authz, source_ip=peer, authenticated=True
            )
            return request.state.identity
        # Fall through: no trusted proxy header -> not authenticated.

    session = superuser_session()
    if session is not None:
        store = UserStore()
        try:
            authz = store.authorize_user(store.ensure_superuser_row())
        except Exception as exc:  # noqa: BLE001
            print(f"[auth] superuser row unavailable: {exc}", flush=True)
            return RequestIdentity(source_ip=peer, superuser=True)
        return RequestIdentity(authorization=authz, source_ip=peer, superuser=True)

    established = _identity_from_cookie(request)
    if established is not None:
        return established

    return RequestIdentity(source_ip=peer)


def _downgrade_from_request(request: Request) -> Optional[str]:
    return request.headers.get("X-SoftWiki-Downgrade") or request.cookies.get(
        "softwiki_downgrade"
    )


@app.middleware("http")
async def network_gate_middleware(request: Request, call_next):
    """Refuse peers outside SOFTWIKI_ALLOWED_CIDRS.

    Outermost layer: runs before identity resolution so a blocked peer costs
    nothing and learns nothing. Disabled unless the allowlist is configured.
    """
    if not netacl.enabled():
        return await call_next(request)

    allowed, reason = netacl.check(request.client.host if request.client else None)
    if not allowed:
        audit.record(
            "netacl.deny",
            result="denied",
            target=request.url.path,
            detail=reason or "",
            source_ip=request.client.host if request.client else None,
        )
        return JSONResponse({"detail": f"Forbidden: {reason}"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def role_middleware(request: Request, call_next):
    """Attach identity, role and downgrade to the request."""
    identity = _identity_for_request(request)
    role_token = set_role(identity.role)
    down_token = set_downgrade(_downgrade_from_request(request))
    ctx_token = set_context(identity)
    request.state.role = current_role()
    request.state.granted_role = identity.role
    request.state.identity = identity
    request.state.source_ip = identity.source_ip
    # Re-enter the kb this user last opened. Request-scoped: the ContextVar is
    # restored in `finally`, so it can never leak into another caller.
    kb_token = None
    authz = getattr(identity, "authorization", None)
    if authz is not None and authz.user is not None:
        from softwiki.config import get_workspaces_root
        from softwiki.identity.users import allowed_kbs
        from softwiki.kb.context import enter_kb
        from softwiki.kb.registry import list_kb_infos

        names = [info.name for info in list_kb_infos(get_workspaces_root())]
        visible = allowed_kbs(authz.kb_scope, names)
        restricted = isinstance(authz.kb_scope, (list, tuple, set))
        # A remembered kb wins; a restricted scope falls back to its first kb so
        # the UI never shows one this user cannot open. An unrestricted scope
        # keeps the instance default (do not surprise a `*` deployment).
        target = authz.user.active_kb if authz.user.active_kb in visible else None
        if target is None and restricted and visible:
            target = visible[0]
        if target:
            kb_token = enter_kb(target)

    # Snapshot the caller now: the context vars are reset in `finally`, so
    # calling identity.actor() afterwards would report the env fallback role
    # instead of the role the request actually ran as.
    actor = identity.actor()

    try:
        response = await call_next(request)
    except Exception:
        audit.record(
            f"{request.method} {request.url.path}",
            result="error",
            actor=actor,
            source_ip=identity.source_ip,
        )
        raise
    finally:
        if kb_token is not None:
            from softwiki.kb.context import restore_kb

            restore_kb(kb_token)
        reset_context(ctx_token)
        reset_downgrade(down_token)
        reset_role(role_token)

    # Audit: write and sensitive operations only.
    if request.method not in _READ_METHODS:
        audit.record(
            f"{request.method} {request.url.path}",
            result="ok" if response.status_code < 400 else f"http-{response.status_code}",
            actor=actor,
            source_ip=identity.source_ip,
        )
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Identity gate. Only enforced when not in single-machine mode."""
    mode = auth_mode()
    if mode != "off" and request.url.path not in _AUTH_EXEMPT:
        # Middleware order is not a contract we should rely on: this gate is
        # registered after the role middleware, which makes it run *first*.
        # Resolve the identity here if it has not been resolved yet, otherwise
        # every non-exempt path would answer 401 in proxy/local/oidc mode.
        identity = getattr(request.state, "identity", None)
        if identity is None:
            identity = _identity_for_request(request)
            request.state.identity = identity
        if identity is None or not identity.authenticated:
            return JSONResponse(
                {"detail": "Authentication required", "mode": mode}, status_code=401
            )
        if identity.authorization and identity.authorization.pending:
            return JSONResponse(
                {
                    "detail": "Account pending administrator approval",
                    "identity": identity.identity,
                },
                status_code=403,
            )

    if not auth_enabled():
        return await call_next(request)
    if request.url.path in _AUTH_EXEMPT:
        return await call_next(request)

    # The identity layer above (proxy/local/oidc) has already authenticated the
    # caller. What follows is the legacy session-token flow for deployments that
    # still use it; it must not reject identities it does not know about.
    identity = getattr(request.state, "identity", None)
    if identity is not None and identity.authenticated:
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


class ProviderLoginRequest(BaseModel):
    """Sign in with an external identity.

    ``claims`` is what a standard OIDC provider returned after the browser
    round-trip; ``code`` is for non-standard flows (WeChat) where the backend
    still has to exchange it.
    """

    provider: str
    claims: Optional[Dict] = None
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    state: Optional[str] = None
    #: Passed through to non-standard adapters (WeChat). Until per-provider
    #: secrets are stored, this is how an operator hooks one up.
    app_id: Optional[str] = None
    app_secret: Optional[str] = None


class PasswordLoginRequest(BaseModel):
    """Sign in as the built-in admin (escape hatch)."""

    username: str = "admin"
    password: str


class KbSwitchRequest(BaseModel):
    kb: str


class SuperuserOpenRequest(BaseModel):
    ttl: Optional[str] = None
    token: Optional[str] = None


class ReauthRequest(BaseModel):
    token: str


class DowngradeRequest(BaseModel):
    role: Optional[str] = None


class UserPatch(BaseModel):
    role_override: Optional[str] = None
    kb_scope: Optional[object] = None
    is_active: Optional[bool] = None


class MappingPatch(BaseModel):
    groups: Dict[str, List[str]]


# -- identity: providers -------------------------------------------------


@app.get("/api/auth/providers")
def auth_providers():
    from softwiki.identity import available_adapters

    body = {
        "mode": auth_mode(),
        "adapters": available_adapters(),
        "superuser_token_configured": bool(os.getenv("SOFTWIKI_SUPERUSER_TOKEN", "").strip()),
        "unknown_user_policy": UserStore().unknown_policy(),
    }
    if auth_mode() == "proxy":
        # Diagnostics only: header names and trusted peers, never identities.
        from softwiki.identity.proxy import describe as describe_proxy

        body["proxy"] = describe_proxy()
    return body


@app.post("/api/auth/login")
def auth_login(req: ProviderLoginRequest, request: Request):
    """Establish a session from an external identity."""
    from softwiki.identity import ExternalIdentity, get_adapter

    if auth_mode() == "off":
        raise HTTPException(
            status_code=400,
            detail="Single-machine mode has no identity providers; use /api/auth/superuser",
        )
    try:
        adapter = get_adapter(req.provider)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    issuer_name = f"{req.provider}:{os.getenv('SOFTWIKI_ISSUER_LABEL', req.provider)}"
    try:
        if req.claims:
            identity = adapter.identity_from_claims(issuer_name, req.claims)
        elif req.code:
            identity = adapter.fetch_identity(issuer_name, req.code, redirect_uri=req.redirect_uri)
        else:
            raise HTTPException(
                status_code=400, detail="provide either claims (OIDC) or code (WeChat)"
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = UserStore()
    try:
        authz = store.authorize(identity)
    except IdentityDenied as exc:
        audit.record(
            "auth.login", result="denied", detail=str(exc), source_ip=_client_ip(request)
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    request.state.identity = RequestIdentity(
        authorization=authz, source_ip=_client_ip(request), authenticated=True
    )
    audit.record(
        "auth.login",
        result="ok",
        actor={
            "mode": auth_mode(),
            "identity": authz.identity,
            "role": authz.granted_role,
            "source_ip": _client_ip(request),
        },
        detail=f"pending={authz.pending}",
    )

    response = JSONResponse(
        {
            "identity": authz.identity,
            "role": authz.granted_role,
            "pending": authz.pending,
            "kb_scope": authz.kb_scope,
        }
    )
    response.set_cookie(
        "softwiki_identity",
        json.dumps({"issuer": identity.issuer, "subject": identity.subject}),
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/auth/password")
def auth_password_login(req: PasswordLoginRequest, request: Request):
    """Sign in as the built-in admin.

    Rate limited per peer and audited. This is the only guessable entry point,
    so it is deliberately narrow: one account, no user enumeration, one error
    message for every failure.
    """
    from softwiki.identity.localauth import LOGIN_LIMITER, authenticate
    from softwiki.identity.proxy import client_ip_for_audit

    # Behind the reverse proxy the TCP peer is nginx, so every user would share
    # one rate-limit bucket and every audit row would name the proxy. Use the
    # forwarded address *only* when the peer is a configured trusted proxy.
    peer = _client_ip(request)
    client = client_ip_for_audit(peer, request.headers.get("x-forwarded-for"))
    if not LOGIN_LIMITER.allow(client):
        audit.record("auth.password", result="rate-limited", source_ip=client)
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = authenticate(req.username, req.password)
    if user is None:
        audit.record(
            "auth.password", result="denied", target=str(req.username)[:64], source_ip=client
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    store = UserStore()
    authz = store.authorize_user(user)
    audit.record(
        "auth.password",
        result="ok",
        actor={"identity": authz.identity, "role": authz.granted_role, "source_ip": client},
    )

    response = JSONResponse(
        {
            "identity": authz.identity,
            "role": authz.granted_role,
            "pending": authz.pending,
            "kb_scope": authz.kb_scope,
        }
    )
    response.set_cookie(
        "softwiki_identity",
        json.dumps({"issuer": user.issuer, "subject": user.subject}),
        httponly=True,
        samesite="lax",
    )
    return response


def _identity_from_cookie(request: Request) -> Optional[RequestIdentity]:
    """Rebuild a caller's identity from the session cookie.

    The cookie only carries ``(issuer, subject)`` — the *who*. Role and
    ``kb_scope`` are recomputed from the local tables on every request, so an
    admin's edits take effect without anyone signing in again.
    """
    raw = request.cookies.get("softwiki_identity")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        store = UserStore()
        user = store.find(str(data["issuer"]), str(data["subject"]))
        if user is None:
            return None
        return RequestIdentity(
            authorization=store.authorize_user(user),
            source_ip=_client_ip(request),
            authenticated=True,
        )
    except (ValueError, KeyError, IdentityDenied) as exc:
        print(f"[auth] ignoring bad identity cookie: {exc}", flush=True)
        return None


@app.get("/api/auth/me")
def auth_me(request: Request):
    """Who am I, and what may I do here?"""
    identity = getattr(request.state, "identity", None)
    if identity is None:
        return {"authenticated": False, "mode": auth_mode()}
    return {
        "authenticated": identity.authenticated,
        "mode": auth_mode(),
        "identity": identity.identity,
        "superuser": identity.superuser,
        "granted_role": identity.role,
        "effective_role": current_role(),
        "kb_scope": identity.kb_scope,
        "pending": bool(identity.authorization and identity.authorization.pending),
    }


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    audit.record("auth.logout", result="ok", source_ip=_client_ip(request))
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("softwiki_identity")
    response.delete_cookie("softwiki_downgrade")
    return response


# -- identity: superuser escape hatch ------------------------------------


@app.get("/api/auth/superuser")
def superuser_status(request: Request):
    session = superuser_session()
    peer = _client_ip(request)
    return {
        "mode": auth_mode(),
        "session": session.describe() if session else None,
        "local": is_local_address(peer),
        "source_ip": peer,
    }


@app.post("/api/auth/superuser")
def superuser_open(req: SuperuserOpenRequest, request: Request):
    peer = _client_ip(request)
    try:
        session = open_superuser(source_ip=peer, ttl=req.ttl, token=req.token)
    except SuperuserDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid ttl: {exc}") from exc
    return {"status": "ok", "session": session.describe()}


@app.delete("/api/auth/superuser")
def superuser_close(request: Request):
    close_superuser(source_ip=_client_ip(request))
    return {"status": "ok"}


# -- identity: downgrade --------------------------------------------------


@app.get("/api/auth/downgrade")
def downgrade_status():
    from softwiki.permissions import downgrade_role, granted_role

    return {
        "granted_role": granted_role(),
        "effective_role": current_role(),
        "downgrade": downgrade_role(),
    }


@app.post("/api/auth/downgrade")
def downgrade_set(req: DowngradeRequest, request: Request):
    """Work as a lower role.

    Two refusals matter here:

    * asking for a role **above the granted one** is escalation — always 403;
    * while already downgraded, asking for a role above the *effective* one is
      also refused, because a downgraded session must not undo its own
      constraint. Clear the downgrade by posting the granted role through
      ``/api/auth/downgrade/clear``.
    """
    from softwiki.permissions import ROLE_ORDER, role_level

    identity = getattr(request.state, "identity", None)
    granted = identity.role if identity else current_role()
    target = normalize_role(req.role) if req.role else granted
    effective = current_role()

    if role_level(target) > role_level(granted):
        raise HTTPException(
            status_code=403,
            detail=f"role '{target}' is above granted role '{granted}'",
        )
    if role_level(target) > role_level(effective):
        raise HTTPException(
            status_code=403,
            detail=f"role '{target}' is above the current effective role '{effective}'; clear the downgrade first",
        )

    audit.record(
        "auth.downgrade",
        result="ok",
        detail=f"{granted} -> {target}",
        actor=getattr(request.state, "identity", None).actor()
        if getattr(request.state, "identity", None)
        else None,
        source_ip=_client_ip(request),
    )
    response = JSONResponse({"granted_role": granted, "effective_role": target})
    if target == granted:
        response.delete_cookie("softwiki_downgrade")
    else:
        response.set_cookie("softwiki_downgrade", target, httponly=False, samesite="lax")
    return response


@app.delete("/api/auth/downgrade")
def downgrade_clear(request: Request):
    """Return to the granted role."""
    identity = getattr(request.state, "identity", None)
    granted = identity.role if identity else current_role()
    audit.record(
        "auth.downgrade.clear",
        result="ok",
        detail=f"back to {granted}",
        source_ip=_client_ip(request),
    )
    response = JSONResponse({"granted_role": granted, "effective_role": granted})
    response.delete_cookie("softwiki_downgrade")
    return response


# -- identity: admin ------------------------------------------------------


def _require_admin(request: Request) -> None:
    """Admin surfaces follow the *effective* role: a downgraded admin is locked out.

    That is the point of downgrading — working as study means study everywhere.
    """
    if not can("permissions.write"):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_role()}' cannot manage identities",
        )


def _reauth_guard(request: Request, token: Optional[str], action: str, capability: str) -> None:
    """Sensitive actions need a fresh re-authentication, even for admins."""
    identity = getattr(request.state, "identity", None)
    name = identity.identity if identity else "anonymous"
    if not check_reauth(name, token):
        audit.record(
            action,
            result="denied",
            detail="re-authentication required",
            capability=capability,
            source_ip=_client_ip(request),
        )
        raise HTTPException(status_code=403, detail="re-authentication required")


@app.post("/api/auth/reauth")
def reauth(req: ReauthRequest, request: Request):
    from softwiki.identity import superuser as su

    identity = getattr(request.state, "identity", None)
    name = identity.identity if identity else "anonymous"
    expected = su.reauth_token()
    if expected and not su.check_reauth(name, req.token):
        audit.record("auth.reauth", result="denied", source_ip=_client_ip(request))
        raise HTTPException(status_code=403, detail="invalid re-authentication token")
    su.mark_reauth(name)
    audit.record("auth.reauth", result="ok", source_ip=_client_ip(request))
    return {"status": "ok", "ttl_seconds": su.REAUTH_TTL_SECONDS}


@app.get("/api/admin/users")
def admin_users(request: Request):
    _require_admin(request)
    from softwiki.kb.registry import list_kb_infos

    all_kbs = [kb.name for kb in list_kb_infos(get_workspaces_root())]
    store = UserStore()
    rows = []
    for user in store.load():
        role, pending = store.role_for(user)
        from softwiki.identity.users import visible_kbs

        visible = visible_kbs(user.kb_scope, all_kbs)
        rows.append(
            {
                **user.to_dict(),
                "resolved_role": role,
                "pending": pending,
                "visible_kbs": visible,
                # A typo in kb_scope must not be fatal, but it must be visible.
                "kb_scope_empty": bool(all_kbs) and not visible,
            }
        )
    return {"users": rows, "all_kbs": all_kbs, "unknown_user_policy": store.unknown_policy()}


@app.patch("/api/admin/users/{issuer}/{subject}")
def admin_patch_user(
    issuer: str, subject: str, patch: UserPatch, request: Request, reauth_token: Optional[str] = None
):
    _require_admin(request)
    _reauth_guard(request, reauth_token, "admin.user.update", "permissions.write")
    changes = {k: v for k, v in patch.dict().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="nothing to change")
    if "role_override" in changes and changes["role_override"] not in ROLE_ORDER:
        raise HTTPException(status_code=400, detail="unknown role")
    try:
        user = UserStore().update(issuer, subject, **changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.record(
        "admin.user.update",
        target=f"{issuer}:{subject}",
        result="ok",
        detail=json.dumps(changes, ensure_ascii=False, default=str),
        source_ip=_client_ip(request),
    )
    return user.to_dict()


@app.get("/api/admin/mapping")
def admin_mapping(request: Request):
    _require_admin(request)
    store = UserStore()
    return {"groups": store.mapping(), "unknown_user_policy": store.unknown_policy()}


@app.put("/api/admin/mapping")
def admin_put_mapping(
    patch: MappingPatch, request: Request, reauth_token: Optional[str] = None
):
    _require_admin(request)
    _reauth_guard(request, reauth_token, "admin.mapping.update", "permissions.write")
    store = UserStore()
    store.save_mapping(patch.groups)
    audit.record(
        "admin.mapping.update",
        result="ok",
        detail=json.dumps(patch.groups, ensure_ascii=False),
        source_ip=_client_ip(request),
    )
    return {"groups": store.mapping()}


@app.get("/api/admin/audit")
def admin_audit(request: Request, limit: int = 100):
    _require_admin(request)
    return {"records": audit.read_recent(limit=max(1, min(limit, 1000)))}


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
def ensure_admin_account():
    """Create the built-in admin on first start (no default password).

    Single-machine mode needs no account: every caller already *is* the machine
    administrator. Creating a row there would only confuse the Users panel.
    """
    if auth_mode() == "off":
        return

    from softwiki.identity.localauth import ensure_builtin_admin

    try:
        created, generated = ensure_builtin_admin()
    except Exception as exc:  # noqa: BLE001 - must not stop the API from serving
        print(f"[auth] could not ensure built-in admin: {exc}", flush=True)
        return
    if created and generated:
        print(
            "\n" + "=" * 68
            + "\n  Built-in admin created. Username: admin"
            + f"\n  Password: {generated}"
            + "\n  This is shown once. Change it with scripts/set_admin_password.py"
            + "\n" + "=" * 68,
            flush=True,
        )
    elif created:
        print("[auth] built-in admin created from SOFTWIKI_ADMIN_PASSWORD", flush=True)


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


@app.get("/api/permissions")
def get_permissions(request: Request):
    role = current_role()
    identity = getattr(request.state, "identity", None)
    granted = identity.role if identity is not None else role
    return {
        "role": role,
        "granted_role": granted,
        "downgraded": role != granted,
        "capabilities": role_capabilities(role),
        "roles": ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"],
    }


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
    kb: Optional[str] = None

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


class WikiPageBuildRequest(BaseModel):
    subject: str
    force: bool = False
    # "split" honours the fixed cap by emitting several pages;
    # "fail" refuses oversized subjects (used while piloting).
    oversize: str = "split"

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

class NliScanRequest(BaseModel):
    limit: int = 10
    apply: bool = False

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


@app.get("/api/swa/status")
@app.get("/api/agent/projects")
def agent_projects():
    """The assistant projects the current role may use.

    A "project" is one working scope (work / manage / admin). They share one
    opencode process but differ in the agent profile, which is where the
    permission set lives.
    """
    from softwiki.permissions import current_role, role_rank

    catalog = [
        {
            "id": "work",
            "title": "Work",
            "agent": "wiki-work",
            "min_role": "wiki-work",
            "color": "#3366cc",
            "description": (
                "Draft and edit wiki pages, search the kb, and propose changes. "
                "Cannot publish, ingest or delete."
            ),
        },
        {
            "id": "manage",
            "title": "Manage",
            "agent": "wiki-manage",
            "min_role": "wiki-manage",
            "color": "#ac6600",
            "description": (
                "Everything Work can do, plus ingest, reindex, adjudicate "
                "conflicts and apply proposed changes."
            ),
        },
        {
            "id": "admin",
            "title": "Admin",
            "agent": "wiki-admin",
            "min_role": "wiki-admin",
            "color": "#b32424",
            "description": (
                "Full access, including users, audit, knowledge-base registry "
                "and system maintenance."
            ),
        },
    ]
    rank = role_rank(current_role())
    visible = [p for p in catalog if rank >= role_rank(p["min_role"])]
    return {"role": current_role(), "projects": visible}


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


@app.post("/api/swa/session")
@app.post("/api/agent/session")
def agent_create_session(req: AgentSessionRequest):
    session = _agent_request("POST", "/session", {"title": req.title or "SWAgent"})
    return {"session_id": session.get("id"), "session": session}


@app.post("/api/swa/ask")
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


@app.post("/api/swa/session/{session_id}/abort")
@app.post("/api/agent/session/{session_id}/abort")
def agent_abort(session_id: str):
    _agent_request("POST", f"/session/{session_id}/abort", timeout=15)
    return {"status": "aborted", "session_id": session_id}


@app.delete("/api/swa/session/{session_id}")
@app.delete("/api/agent/session/{session_id}")
def agent_delete(session_id: str):
    _agent_request("DELETE", f"/session/{session_id}", timeout=15)
    return {"status": "deleted", "session_id": session_id}


class AgentPromptRequest(BaseModel):
    question: str
    session_id: str
    agent: Optional[str] = None


def _agent_event_session_id(event: dict) -> Optional[str]:
    props = event.get("properties")
    if not isinstance(props, dict):
        props = {}
    part = props.get("part")
    info = props.get("info")
    candidates = [
        props.get("sessionID"),
        part.get("sessionID") if isinstance(part, dict) else None,
        info.get("sessionID") if isinstance(info, dict) else None,
        event.get("sessionID"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _agent_event_allowed(event: dict, session_id: Optional[str]) -> bool:
    if not session_id:
        return True
    sid = _agent_event_session_id(event)
    return not sid or sid == session_id


def _agent_event_urls() -> List[str]:
    urls = [f"{AGENT_WEB_URL}{AGENT_EVENT_PATH}"]
    if AGENT_EVENT_PATH != "/event":
        urls.append(f"{AGENT_WEB_URL}/event")
    return urls


async def _agent_pump_events(session_id: Optional[str], queue: "asyncio.Queue[Optional[str]]",
                             stop: asyncio.Event) -> None:
    for url in _agent_event_urls():
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
        )
        try:
            request = client.build_request("GET", url, headers={"Accept": "text/event-stream"})
            response = await client.send(request, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            continue
        if response.status_code >= 400:
            await response.aclose()
            await client.aclose()
            continue
        try:
            async for line in response.aiter_lines():
                if stop.is_set():
                    break
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event = payload.get("payload") if isinstance(payload, dict) else None
                if not isinstance(event, dict):
                    event = payload
                if not isinstance(event, dict):
                    continue
                if not _agent_event_allowed(event, session_id):
                    continue
                await queue.put(json.dumps(event, ensure_ascii=False))
        except httpx.HTTPError:
            pass
        finally:
            await response.aclose()
            await client.aclose()
        await queue.put(None)
        return
    await queue.put(None)


async def _agent_event_stream(session_id: Optional[str]):
    queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
    stop = asyncio.Event()
    pump = asyncio.create_task(_agent_pump_events(session_id, queue, stop))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=AGENT_EVENT_HEARTBEAT)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                break
            yield f"data: {item}\n\n"
    finally:
        stop.set()
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump


@app.get("/api/swa/events")
@app.get("/api/agent/events")
def agent_events(session_id: Optional[str] = None):
    return StreamingResponse(
        _agent_event_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/swa/sessions")
@app.get("/api/agent/sessions")
def agent_sessions():
    sessions = _agent_request("GET", "/session", timeout=30) or []
    items = []
    for session in sessions:
        time_info = session.get("time") or {}
        items.append({
            "id": session.get("id"),
            "title": session.get("title"),
            "parent_id": session.get("parentID"),
            "created": time_info.get("created"),
            "updated": time_info.get("updated"),
        })
    items.sort(key=lambda item: item.get("updated") or item.get("created") or 0, reverse=True)
    return {"sessions": items}


@app.get("/api/swa/session/{session_id}/messages")
@app.get("/api/agent/session/{session_id}/messages")
def agent_messages(session_id: str):
    messages = _agent_request("GET", f"/session/{session_id}/message", timeout=60) or []
    return {"session_id": session_id, "messages": messages}


@app.post("/api/swa/prompt")
@app.post("/api/agent/prompt")
def agent_prompt(req: AgentPromptRequest):
    path = f"/session/{req.session_id}/prompt_async"
    body = {
        "agent": req.agent or AGENT_DEFAULT,
        "parts": [{"type": "text", "text": req.question}],
    }
    try:
        _agent_request("POST", path, body, timeout=30)
    except HTTPException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent does not accept prompt_async: {exc.detail}",
        ) from exc
    return {"status": "accepted", "session_id": req.session_id}


@app.get("/api/knowledge/metrics")
def get_knowledge_metrics():
    db = SessionLocal()
    try:
        return knowledge_metrics(db)
    finally:
        db.close()


@app.get("/api/conflicts")
def get_conflicts(status: Optional[str] = None, topic: Optional[str] = None,
                  severity: Optional[str] = None, type: Optional[str] = None,
                  limit: int = 50, offset: int = 0):
    db = SessionLocal()
    try:
        return list_conflicts(db, status=status, topic=topic, severity=severity,
                              ctype=type, limit=limit, offset=offset)
    finally:
        db.close()


@app.post("/api/conflicts/scan")
def scan_knowledge_conflicts(req: ConflictScanRequest):
    require_capability("conflict.adjudicate")
    db = SessionLocal()
    try:
        return scan_conflicts(db, topic=req.topic)
    finally:
        db.close()


@app.post("/api/conflicts/{conflict_id}/adjudicate")
def adjudicate_conflict(conflict_id: int, req: ConflictAdjudicateRequest):
    require_capability("conflict.adjudicate")
    db = SessionLocal()
    try:
        try:
            return adjudicate(db, conflict_id, req.action, actor=req.actor, reason=req.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.post("/api/knowledge/nli/scan")
def scan_nli_conflicts(req: NliScanRequest):
    if req.apply:
        require_capability("nli.scan")
    db = SessionLocal()
    try:
        return judge_candidates(db, limit=min(max(req.limit, 1), 20), apply=req.apply)
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
    from softwiki.kb.context import KbResolutionError, enter_kb, restore_kb

    try:
        previous_kb = enter_kb(req.kb)
    except KbResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
            "citation_check": verify_citations(answer, getattr(engine, "last_citations", [])),
            "mode": req.mode or "normal",
            "workflow": req.workflow,
            "kb": req.kb or os.path.basename(get_workspace_dir()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        restore_kb(previous_kb)

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
    require_capability("ingest.write")
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
            source_name=source_meta.get("source_name") or content.get("source_name") or "Manual Import",
            source_type=source_meta.get("source_type") or ("web" if content.get("url") else "manual_import"),
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
    require_capability("ingest.write")
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
            author = "Unknown"
            published_at = None
            source_url = None
            body = md_text
            if md_text.startswith("---"):
                end = md_text.find("\n---", 3)
                if end != -1:
                    try:
                        import yaml
                        meta = yaml.safe_load(md_text[3:end]) or {}
                        if isinstance(meta, dict):
                            title = meta.get("title") or title
                            author = meta.get("author") or author
                            source_url = meta.get("url") or meta.get("source")
                            raw_date = meta.get("date") or meta.get("published_at")
                            if raw_date:
                                if isinstance(raw_date, datetime):
                                    published_at = raw_date
                                else:
                                    published_at = datetime.fromisoformat(str(raw_date)[:10])
                            body = md_text[end + 4:].lstrip("\n")
                    except Exception as e:
                        print(f"Front matter parse failed for {file.filename}: {e}")
            content = {
                "title": title,
                "author": author,
                "raw_text": body,
                "cleaned_text": body,
                "published_at": published_at,
            }
            content["url"] = source_url
            if source_url:
                content["source_name"] = urlparse(source_url).netloc.replace("www.", "") or "Web Import"
        else:
            content = extract_pdf_content(dest_path)
        content.setdefault("url", None)
        
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
            url=content.get("url"),
            source_name=source_meta.get("source_name") or content.get("source_name") or "Manual Import",
            source_type=source_meta.get("source_type") or ("web" if content.get("url") else "manual_import"),
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

@app.post("/api/kb/extract-pending")
def extract_pending(limit: int = 10):
    """Resume extraction for documents left in pending/extracting.

    Background extraction lives in the API process, so a restart (every deploy)
    strands whatever was queued. Without this the pipeline page would show
    "generating" forever.
    """
    require_capability("ingest.write")
    from softwiki.extraction.processor import run_extraction_pipeline

    limit = max(1, min(limit, 50))
    db = SessionLocal()
    try:
        # Only documents that never produced claims. Re-running extraction on a
        # partially extracted document would append duplicate claims.
        docs = (
            db.query(Document)
            .outerjoin(Claim, Claim.document_id == Document.id)
            .filter(Document.status.in_(("pending", "extracting")), Claim.id.is_(None))
            .order_by(Document.id)
            .limit(limit)
            .all()
        )
        started = []
        for doc in docs:
            if not doc.cleaned_text:
                continue
            run_extraction_pipeline(db, doc.id, doc.cleaned_text, doc.published_at, background=True)
            started.append(doc.id)
    finally:
        db.close()

    _pipeline_cache.clear()
    return {"status": "ok", "started": started, "count": len(started)}


@app.post("/api/index")
def rebuild_index(kb: Optional[str] = None):
    """Chunk all documents and rebuild dense embeddings and BM25 index files.

    Pass `kb` to index a specific knowledge base; omit it to index the active one.
    """
    require_capability("index.write")
    from softwiki.kb.context import KbResolutionError, enter_kb, restore_kb

    try:
        previous_kb = enter_kb(kb)
    except KbResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
        chunk_ids = [c.id for c in all_chunks]
        chunk_texts = [c.text for c in all_chunks]

        vector_ok = False
        try:
            embedder = WikiEmbedder()
            vector_store = LocalVectorStore()
            embeddings = embedder.embed_texts(chunk_texts)
            if os.path.exists(vector_store.get_current_path()):
                os.remove(vector_store.get_current_path())
            vector_store.reset()
            vector_store.add_vectors(chunk_ids, embeddings)
            vector_ok = True
        except Exception as exc:
            # Restricted/air-gapped deployments can still use BM25.
            print(f"[index] vector index skipped: {exc}", flush=True)

        bm25_store = Bm25Store()
        chunk_id_to_text = {c.id: c.text for c in all_chunks}
        bm25_store.rebuild_index(chunk_id_to_text)

        _pipeline_cache.clear()
        return {
            "status": "success",
            "kb": kb or os.path.basename(get_workspace_dir()),
            "indexed_chunks": len(all_chunks),
            "vector_index": vector_ok,
            "bm25_index": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        restore_kb(previous_kb)

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
    require_capability("wiki.build")
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
    require_capability("wiki.apply")
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
    require_capability("wiki.apply")
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
    require_capability("wiki.preview")
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
    require_capability("wiki.apply")
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
    require_capability("wiki.build")
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


@app.get("/api/wiki/pages")
def list_wiki_subject_pages(refresh: bool = False, limit: int = 0):
    """List generated one-subject-per-page wiki pages.

    `refresh=true` recomputes candidate subjects from the graph (no generation).
    """
    from softwiki.wiki.subject_pages import (
        SUBJECT_PAGE_CLAIM_LIMIT, list_generated_pages, subject_candidates,
    )

    db = SessionLocal()
    try:
        listing = list_generated_pages(db)
        body: dict = {
            "limit": SUBJECT_PAGE_CLAIM_LIMIT,
            "generated": listing.get("generated", False),
            "subjects": listing.get("subjects", []),
        }
        if not body["subjects"] or refresh:
            candidates = subject_candidates(db, limit=limit or None)
            body["candidates"] = candidates
            body["candidate_count"] = len(candidates)
        return JSONResponse(body, headers={"Cache-Control": "no-store"})
    finally:
        db.close()


class SubjectRuleRequest(BaseModel):
    subject: str
    action: str = "ignore"  # ignore | unignore | lock | unlock


class WikiPlanRequest(BaseModel):
    kind: str
    kb: Optional[str] = None
    subjects: List[str] = []
    reason: str = ""


class WikiPlanDecision(BaseModel):
    reason: str = ""


@app.post("/api/wiki/plans")
def create_wiki_plan(req: WikiPlanRequest):
    """Propose a wiki change. The agent may do this; a human must approve it."""
    require_capability("wiki.submit")
    from softwiki.wiki.plans import ACTIONS, create_plan

    if req.kind not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"unknown kind {req.kind!r}")
    if not req.subjects:
        raise HTTPException(status_code=400, detail="subjects must not be empty")
    db = SessionLocal()
    try:
        plan = create_plan(
            db, req.kind, {"subjects": req.subjects}, kb=req.kb,
            proposed_by=current_role(), reason=req.reason,
        )
        audit.record("wiki.plan.create", result="ok", target=f"{req.kind}:{plan.id}",
                     detail=f"{len(req.subjects)} subject(s)")
        return {"id": plan.id, "kind": plan.kind, "status": plan.status,
                "subjects": req.subjects, "reason": plan.reason}
    finally:
        db.close()


@app.get("/api/wiki/plans")
def list_wiki_plans(status: Optional[str] = "pending", limit: int = 50):
    from softwiki.wiki.plans import list_plans

    db = SessionLocal()
    try:
        rows = list_plans(db, status=status, limit=limit)
        return {"plans": [
            {
                "id": p.id,
                "kind": p.kind,
                "kb": p.kb,
                "status": p.status,
                "proposed_by": p.proposed_by,
                "approved_by": p.approved_by,
                "reason": p.reason,
                "result": p.result,
                "subjects": (__import__("json").loads(p.payload or "{}") or {}).get("subjects", []),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "applied_at": p.applied_at.isoformat() if p.applied_at else None,
            }
            for p in rows
        ]}
    finally:
        db.close()


@app.post("/api/wiki/plans/{plan_id}/approve")
def approve_wiki_plan(plan_id: int, req: WikiPlanDecision):
    """Approve and execute. Requires wiki.apply — the agent cannot do this."""
    require_capability("wiki.apply")
    from softwiki.wiki.plans import decide, get_plan

    db = SessionLocal()
    try:
        plan = get_plan(db, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="plan not found")
        try:
            result = decide(db, plan, True, decided_by=current_role(), reason=req.reason)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        audit.record("wiki.plan.approve", result=result.get("status", "ok"),
                     target=f"{plan.kind}:{plan.id}", detail=plan.kind)
        return result
    finally:
        db.close()


@app.post("/api/wiki/plans/{plan_id}/reject")
def reject_wiki_plan(plan_id: int, req: WikiPlanDecision):
    require_capability("wiki.apply")
    from softwiki.wiki.plans import decide, get_plan

    db = SessionLocal()
    try:
        plan = get_plan(db, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="plan not found")
        try:
            result = decide(db, plan, False, decided_by=current_role(), reason=req.reason)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        audit.record("wiki.plan.reject", result="ok", target=f"{plan.kind}:{plan.id}")
        return result
    finally:
        db.close()


@app.get("/api/wiki/subject-rules")
def get_subject_rules():
    """Which subjects are excluded from generation, and which are hand-locked."""
    from softwiki.wiki.subject_rules import load

    return load()


@app.post("/api/wiki/subject-rules")
def set_subject_rule(req: SubjectRuleRequest):
    from softwiki.wiki import subject_rules as rules

    subject = req.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject is required")
    require_capability("wiki.apply")
    if req.action == "ignore":
        return rules.add_ignore(subject)
    if req.action == "unignore":
        return rules.remove_ignore(subject)
    if req.action == "lock":
        return rules.set_locked(subject, True)
    if req.action == "unlock":
        return rules.set_locked(subject, False)
    raise HTTPException(status_code=400, detail=f"unknown action {req.action!r}")


@app.post("/api/wiki/reconcile")
def reconcile_wiki_subjects(budget: int = 0):
    """Queue entity pages that are missing or stale.

    On a fresh kb this enqueues the first batch of subjects; afterwards it only
    queues subjects whose claim count moved. `budget=0` uses the configured cap.
    """
    require_capability("wiki.apply")
    from softwiki.wiki.auto_pages import reconcile

    db = SessionLocal()
    try:
        # Manual endpoint = the user pressing "start generation": bootstrapping allowed.
        return {"status": "success", **reconcile(db, budget=budget or None, allow_initial=True)}
    finally:
        db.close()


@app.post("/api/wiki/pages/build")
def build_wiki_subject_page(req: WikiPageBuildRequest):
    """Generate page(s) for one subject. Never truncates silently."""
    require_capability("wiki.apply")
    from softwiki.wiki.subject_pages import generate_subject_pages

    db = SessionLocal()
    try:
        try:
            result = generate_subject_pages(
                db, req.subject, force=req.force, oversize=req.oversize,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        return {"status": "success", **result}
    finally:
        db.close()


@app.get("/api/wiki/pages/{slug}")
def get_wiki_subject_page(slug: str):
    from softwiki.wiki.subject_pages import read_page

    db = SessionLocal()
    try:
        page = read_page(db, slug)
        if page is None:
            raise HTTPException(status_code=404, detail=f"Wiki page '{slug}' not found")
        return page
    finally:
        db.close()


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
def list_documents(limit: Optional[int] = None, offset: int = 0):
    """Lists ingested documents with metadata.

    Without `limit` the full list is returned (compatibility); with `limit` the
    response is a bounded page so the UI never ships tens of thousands of rows.
    """
    db = SessionLocal()
    try:
        query = db.query(Document).order_by(Document.id.desc())
        if limit is not None:
            total = query.count()
            documents = query.offset(max(0, offset)).limit(max(1, min(limit, 500))).all()
            rows = [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "url": doc.url,
                    "source_name": doc.source_name,
                    "source_type": doc.source_type,
                    "published_at": doc.published_at.strftime('%Y-%m-%d') if doc.published_at else "Unknown",
                    "collected_at": doc.collected_at.strftime('%Y-%m-%d') if doc.collected_at else "Unknown",
                    "author": doc.author,
                    "trust_level": doc.trust_level,
                }
                for doc in documents
            ]
            return {"items": rows, "total": total, "limit": limit, "offset": offset}
        documents = query.all()
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
def list_claims(limit: Optional[int] = None, offset: int = 0):
    """Lists extracted claims.

    Without `limit` returns the full list (compatibility); with `limit` a bounded
    page plus the total count.
    """
    db = SessionLocal()
    try:
        query = db.query(Claim).order_by(Claim.published_at.desc())
        if limit is not None:
            total = query.count()
            claims = query.offset(max(0, offset)).limit(max(1, min(limit, 500))).all()
            return {
                "items": [
                    {
                        "id": c.id,
                        "document_id": c.document_id,
                        "text": c.text,
                        "actor": c.actor,
                        "topic": c.topic,
                        "stance": c.stance,
                        "confidence": c.confidence,
                        "published_at": c.published_at.strftime('%Y-%m-%d') if c.published_at else "Unknown",
                    }
                    for c in claims
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        claims = query.all()
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
    require_capability("document.delete")
    db = SessionLocal()
    try:
        try:
            result = delete_document_knowledge(db, doc_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"status": "success", "message": f"Document {doc_id} successfully deleted.", **result}
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


@app.get("/api/graph/overview")
def graph_overview(limit: int = 60):
    """A small graph worth drawing.

    The full graph is too large to lay out in a browser (thousands of nodes and
    edges), so the panel starts from a handful of the best-connected entities
    and expands on demand through ``/api/graph/subgraph``.
    """
    from sqlalchemy import func, or_

    db = SessionLocal()
    try:
        limit = max(5, min(limit, 300))
        totals: Dict[int, int] = {}
        name_totals: Dict[str, int] = {}

        # Prefer resolved entity ids (schema v3); fall back to names for rows
        # that normalization could not resolve.
        for column in (Relationship.source_entity_id, Relationship.target_entity_id):
            rows = (
                db.query(column, func.count())
                .filter(Relationship.status == "active")
                .filter(column.isnot(None))
                .group_by(column)
                .all()
            )
            for entity_id, count in rows:
                totals[entity_id] = totals.get(entity_id, 0) + count

        for column in (Relationship.source_name, Relationship.target_name):
            rows = (
                db.query(column, func.count())
                .filter(Relationship.status == "active")
                .filter(Relationship.source_entity_id.is_(None))
                .group_by(column)
                .all()
            )
            for name, count in rows:
                name_totals[name] = name_totals.get(name, 0) + count

        top_ids = [entity_id for entity_id, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]]
        top_names = {name for name, _ in sorted(name_totals.items(), key=lambda kv: -kv[1])[:limit]}

        entities = db.query(Entity).filter(Entity.id.in_(top_ids)).all() if top_ids else []
        if top_names:
            extra = db.query(Entity).filter(Entity.name.in_(top_names)).all()
            seen = {ent.id for ent in entities}
            entities.extend(ent for ent in extra if ent.id not in seen)

        selected_ids = {ent.id for ent in entities}
        selected_names = {ent.name for ent in entities}

        conditions = []
        if selected_ids:
            conditions.append(Relationship.source_entity_id.in_(selected_ids))
            conditions.append(Relationship.target_entity_id.in_(selected_ids))
        if selected_names:
            conditions.append(Relationship.source_name.in_(selected_names))
            conditions.append(Relationship.target_name.in_(selected_names))
        relationships = (
            db.query(Relationship)
            .filter(Relationship.status == "active")
            .filter(or_(*conditions))
            .order_by(Relationship.weight.desc(), Relationship.confidence.desc())
            .limit(limit * 20)
            .all()
        ) if conditions else []

        return {
            "entities": [
                {
                    "id": ent.id,
                    "name": ent.name,
                    "type": ent.type,
                    "description": ent.description,
                    "degree": totals.get(ent.id, name_totals.get(ent.name, 0)),
                }
                for ent in entities
            ],
            "relationships": [_rel_payload(rel) for rel in relationships],
            "total_entities": db.query(Entity).filter(Entity.merged_into.is_(None)).count(),
            "total_relationships": db.query(Relationship)
            .filter(Relationship.status == "active")
            .count(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


def _rel_payload(rel) -> dict:
    return {
        "id": rel.id,
        "source_name": rel.source_name,
        "target_name": rel.target_name,
        "source_entity_id": getattr(rel, "source_entity_id", None),
        "target_entity_id": getattr(rel, "target_entity_id", None),
        "relation_type": rel.relation_type,
        "description": rel.description,
        "document_id": rel.document_id,
        "confidence": rel.confidence,
        "weight": getattr(rel, "weight", None),
        "evidence_count": getattr(rel, "evidence_count", None),
        "canonical_claim_id": getattr(rel, "canonical_claim_id", None),
        "published_at": rel.published_at.strftime("%Y-%m-%d") if rel.published_at else "Unknown",
    }


@app.get("/api/graph/subgraph")
def graph_subgraph(entity: str, depth: int = 1, limit: int = 80):
    """Neighbourhood of one entity, for click-to-expand."""
    from softwiki.source_store.models import EntityAlias
    from softwiki.graph.resolution import normalize_entity_name
    from sqlalchemy import or_

    db = SessionLocal()
    try:
        if not entity.strip():
            raise HTTPException(status_code=400, detail="entity is required")
        depth = max(1, min(depth, 2))
        limit = max(5, min(limit, 400))

        key = normalize_entity_name(entity)
        root_entity = db.query(Entity).filter(Entity.name == entity.strip()).first()
        if root_entity is None:
            root_entity = (
                db.query(Entity)
                .filter(Entity.merged_into.is_(None))
                .filter(Entity.normalized_name == key)
                .first()
            )
        if root_entity is None:
            alias = db.query(EntityAlias).filter(EntityAlias.normalized == key).first()
            if alias:
                root_entity = db.query(Entity).filter(Entity.id == alias.entity_id).first()
        if root_entity is not None and root_entity.merged_into:
            root_entity = db.query(Entity).filter(Entity.id == root_entity.merged_into).first() or root_entity

        selected_ids = {root_entity.id} if root_entity is not None else set()
        selected_names = {root_entity.name} if root_entity is not None else {entity}
        frontier_ids = set(selected_ids)
        frontier_names = set(selected_names)
        relationships: Dict[int, object] = {}

        for _ in range(depth):
            if not frontier_ids and not frontier_names:
                break
            conditions = []
            if frontier_ids:
                ids = list(frontier_ids)
                conditions.append(Relationship.source_entity_id.in_(ids))
                conditions.append(Relationship.target_entity_id.in_(ids))
            if frontier_names:
                names = list(frontier_names)
                conditions.append(Relationship.source_name.in_(names))
                conditions.append(Relationship.target_name.in_(names))
            rows = (
                db.query(Relationship)
                .filter(Relationship.status == "active")
                .filter(or_(*conditions))
                .order_by(Relationship.weight.desc(), Relationship.confidence.desc())
                .limit(limit * 4)
                .all()
            )
            next_ids = set()
            next_names = set()
            for rel in rows:
                if len(relationships) >= limit * 2:
                    break
                relationships[rel.id] = rel
                for entity_id, side in ((rel.source_entity_id, rel.source_name),
                                        (rel.target_entity_id, rel.target_name)):
                    if entity_id and entity_id not in selected_ids:
                        selected_ids.add(entity_id)
                        next_ids.add(entity_id)
                    elif side and side not in selected_names:
                        selected_names.add(side)
                        next_names.add(side)
            frontier_ids = next_ids
            frontier_names = next_names

        conditions = []
        if selected_ids:
            conditions.append(Entity.id.in_(selected_ids))
        if selected_names:
            conditions.append(Entity.name.in_(selected_names))
        entities = db.query(Entity).filter(or_(*conditions)).all() if conditions else []
        return {
            "root": root_entity.name if root_entity is not None else entity,
            "entities": [
                {
                    "id": ent.id,
                    "name": ent.name,
                    "type": ent.type,
                    "description": ent.description,
                }
                for ent in entities
            ],
            "relationships": [_rel_payload(rel) for rel in relationships.values()],
            "truncated": len(relationships) >= limit * 2,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/graph/search")
def graph_search(q: str = "", limit: int = 12):
    """Entity suggestions for the graph studio search box."""
    from softwiki.source_store.models import EntityAlias
    from softwiki.graph.resolution import normalize_entity_name

    db = SessionLocal()
    try:
        limit = max(1, min(limit, 50))
        query = (q or "").strip()
        if not query:
            return {"items": []}
        from softwiki.intelligence.graph_claim import link_entities

        items: list[dict] = []
        seen: set[int] = set()
        for seed in link_entities(db, query, limit=limit):
            entity_id = seed.get("entity_id")
            if entity_id in seen:
                continue
            seen.add(entity_id)
            items.append({
                "id": entity_id,
                "name": seed["name"],
                "type": seed.get("type"),
                "degree": seed.get("degree", 0),
                "matched_alias": seed.get("alias"),
            })

        if len(items) < limit:
            key = normalize_entity_name(query)
            rows = (
                db.query(Entity)
                .filter(Entity.merged_into.is_(None))
                .filter(
                    Entity.name.ilike(f"%{query}%")
                    | Entity.normalized_name.ilike(f"%{key}%")
                )
                .limit(limit)
                .all()
            )
            alias_rows = (
                db.query(EntityAlias.entity_id)
                .filter(EntityAlias.normalized.ilike(f"%{key}%"))
                .limit(limit)
                .all()
            )
            alias_ids = [row[0] for row in alias_rows if row[0] not in seen]
            if alias_ids:
                rows += db.query(Entity).filter(Entity.id.in_(alias_ids)).all()
            for entity in rows:
                if entity.id in seen:
                    continue
                seen.add(entity.id)
                items.append({
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "degree": 0,
                    "matched_alias": None,
                })
        return {"items": items[:limit]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/graph/entity")
def graph_entity(name: str = "", id: int | None = None):
    """Entity card: aliases, degree, strongest edges, claims and wiki page."""
    from softwiki.source_store.models import (
        CanonicalClaim, Document, EntityAlias,
    )
    from softwiki.graph.resolution import normalize_entity_name

    db = SessionLocal()
    try:
        entity = None
        if id is not None:
            entity = db.query(Entity).filter(Entity.id == id).first()
        if entity is None and name.strip():
            entity = db.query(Entity).filter(Entity.name == name.strip()).first()
        if entity is None and name.strip():
            key = normalize_entity_name(name)
            entity = (
                db.query(Entity)
                .filter(Entity.merged_into.is_(None))
                .filter(Entity.normalized_name == key)
                .first()
            )
            if entity is None:
                alias = db.query(EntityAlias).filter(EntityAlias.normalized == key).first()
                if alias:
                    entity = db.query(Entity).filter(Entity.id == alias.entity_id).first()
        if entity is None:
            raise HTTPException(status_code=404, detail="entity not found")

        canonical = entity
        if entity.merged_into:
            canonical = db.query(Entity).filter(Entity.id == entity.merged_into).first() or entity

        aliases = [row.alias for row in db.query(EntityAlias).filter(EntityAlias.entity_id == canonical.id).all()]
        merged_from = [
            row.name for row in db.query(Entity)
            .filter(Entity.merged_into == canonical.id)
            .all()
        ]

        edge_filter = (Relationship.source_entity_id == canonical.id) | (
            Relationship.target_entity_id == canonical.id
        )
        edges = (
            db.query(Relationship)
            .filter(Relationship.status == "active")
            .filter(edge_filter)
            .order_by(Relationship.weight.desc(), Relationship.confidence.desc())
            .limit(60)
            .all()
        )

        doc_ids = {rel.document_id for rel in edges if rel.document_id}
        docs = {
            doc.id: doc.title
            for doc in db.query(Document).filter(Document.id.in_(doc_ids)).all()
        } if doc_ids else {}

        claim_ids = {rel.canonical_claim_id for rel in edges if rel.canonical_claim_id}
        claims = (
            db.query(CanonicalClaim)
            .filter(CanonicalClaim.id.in_(claim_ids))
            .filter(CanonicalClaim.status.in_(["active", "disputed"]))
            .all()
        ) if claim_ids else []

        wiki = None
        try:
            from softwiki.wiki.subject_pages import read_subject_page
            page = read_subject_page(db, canonical.name)
            if page:
                wiki = {"slug": page["slug"], "content": page["content"][:1500]}
        except Exception:
            wiki = None

        return {
            "entity": {
                "id": canonical.id,
                "name": canonical.name,
                "type": canonical.type,
                "description": canonical.description,
                "normalized_name": canonical.normalized_name,
                "aliases": sorted(set(aliases)),
                "merged_from": merged_from,
            },
            "degree": len(edges),
            "edges": [
                {**_rel_payload(rel), "document_title": docs.get(rel.document_id)}
                for rel in edges
            ],
            "claims": [
                {
                    "id": claim.id,
                    "text": claim.text,
                    "actor": claim.actor,
                    "topic": claim.topic,
                    "status": claim.status,
                    "confidence": claim.confidence,
                    "evidence_count": claim.evidence_count,
                    "document_id": claim.primary_document_id,
                    "page_start": claim.primary_page_start,
                    "page_end": claim.primary_page_end,
                }
                for claim in claims
            ],
            "wiki": wiki,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/graph/path")
def graph_path(source: str, target: str, max_hops: int = 2):
    """Shortest relationship path between two entities (for path highlighting)."""
    from softwiki.graph.resolution import normalize_entity_name

    db = SessionLocal()
    try:
        max_hops = max(1, min(int(max_hops), 3))

        def resolve(value: str):
            value = (value or "").strip()
            if not value:
                return None
            entity = db.query(Entity).filter(Entity.name == value).first()
            if entity is None:
                key = normalize_entity_name(value)
                entity = (
                    db.query(Entity)
                    .filter(Entity.merged_into.is_(None))
                    .filter(Entity.normalized_name == key)
                    .first()
                )
            return entity

        start = resolve(source)
        end = resolve(target)
        if start is None or end is None:
            raise HTTPException(status_code=404, detail="source or target entity not found")
        if start.merged_into:
            start = db.query(Entity).filter(Entity.id == start.merged_into).first() or start
        if end.merged_into:
            end = db.query(Entity).filter(Entity.id == end.merged_into).first() or end

        frontier = {start.id}
        parents: dict[int, tuple[int, int]] = {}
        visited = {start.id}
        found = False
        for _ in range(max_hops):
            if not frontier or found:
                break
            rows = (
                db.query(Relationship)
                .filter(Relationship.status == "active")
                .filter(
                    Relationship.source_entity_id.in_(frontier)
                    | Relationship.target_entity_id.in_(frontier)
                )
                .order_by(Relationship.weight.desc(), Relationship.confidence.desc())
                .limit(600)
                .all()
            )
            next_frontier = set()
            for rel in rows:
                for a, b in ((rel.source_entity_id, rel.target_entity_id),
                             (rel.target_entity_id, rel.source_entity_id)):
                    if a is None or b is None or a not in frontier or b in visited:
                        continue
                    visited.add(b)
                    parents[b] = (a, rel.id)
                    next_frontier.add(b)
                    if b == end.id:
                        found = True
                        break
                if found:
                    break
            frontier = next_frontier

        if end.id not in parents and start.id != end.id:
            raise HTTPException(status_code=404, detail="no path within max_hops")

        node_ids = [end.id]
        edge_ids = []
        cursor = end.id
        while cursor != start.id:
            parent, edge_id = parents[cursor]
            edge_ids.append(edge_id)
            node_ids.append(parent)
            cursor = parent
        node_ids.reverse()
        edge_ids.reverse()

        nodes = db.query(Entity).filter(Entity.id.in_(node_ids)).all()
        node_map = {node.id: node for node in nodes}
        edges = db.query(Relationship).filter(Relationship.id.in_(edge_ids)).all()
        edge_map = {edge.id: edge for edge in edges}

        return {
            "nodes": [
                {
                    "id": node_id,
                    "name": node_map[node_id].name if node_id in node_map else str(node_id),
                    "type": node_map[node_id].type if node_id in node_map else None,
                }
                for node_id in node_ids
            ],
            "edges": [_rel_payload(edge_map[eid]) for eid in edge_ids if eid in edge_map],
            "hops": len(edge_ids),
        }
    except HTTPException:
        raise
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
    from softwiki.kb.context import current_kb_name

    all_ws = list_workspaces()
    active = current_kb_name() or os.path.basename(get_workspace_dir())
    return {"workspaces": all_ws, "active": active}

class WorkspaceSwitchRequest(BaseModel):
    workspace: str


class KbCreateRequest(BaseModel):
    name: str
    template: str = "generic"
    description: str = ""
    language: Optional[str] = "zh"
    dry_run: bool = True
    reauth_token: Optional[str] = None


@app.get("/api/kb/templates")
def kb_templates():
    from softwiki.kb.registry_state import BUILTIN_TEMPLATES, template_dir

    return {
        "templates": [
            {"name": name, "has_files": template_dir(name) is not None}
            for name in BUILTIN_TEMPLATES
        ]
    }


@app.post("/api/kb/create")
def kb_create(req: KbCreateRequest, request: Request):
    """Knowledge base wizard: plan first, then create.

    ``dry_run=True`` (the default) returns the plan without touching disk, so an
    operator can review exactly which files would be written before committing.
    """
    from softwiki.kb.registry_state import create_kb, plan_create

    require_capability("kb.create")
    identity = current_identity()
    created_by = identity.identity if identity else "superuser"

    try:
        plan = plan_create(
            req.name,
            template=req.template,
            description=req.description,
            language=req.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.dry_run:
        return {"dry_run": True, "plan": plan.to_dict()}

    _reauth_guard(request, req.reauth_token, "kb.create", "kb.create")
    try:
        result = create_kb(plan, created_by=created_by)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit.record(
        "kb.create",
        target={"kb": plan.name, "template": plan.template},
        result="ok",
        detail=json.dumps({"written": result["written"]}, ensure_ascii=False),
        source_ip=_client_ip(request),
    )
    return {"dry_run": False, "plan": plan.to_dict(), "result": result}


@app.post("/api/kb/{name}/provision")
def kb_provision(name: str, request: Request, reauth_token: Optional[str] = None):
    """Create the database for an existing kb directory (idempotent).

    Needed for kbs that were registered before creation provisioned their
    database, and for retrying after a transient database-server failure.
    """
    from softwiki.config import get_workspaces_root
    from softwiki.kb.health import invalidate as invalidate_kb_health
    from softwiki.kb.provision import ensure_kb_database

    require_capability("kb.create")
    path = os.path.join(get_workspaces_root(), name)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail=f"Knowledge base '{name}' not found")
    _reauth_guard(request, reauth_token, "kb.provision", "kb.create")

    result = ensure_kb_database(path)
    invalidate_kb_health()
    audit.record(
        "kb.provision",
        target={"kb": name},
        result="ok" if result.get("created") else "error",
        detail=json.dumps(result, ensure_ascii=False),
        source_ip=_client_ip(request),
    )
    if not result.get("created"):
        raise HTTPException(status_code=400, detail=result.get("error") or "provisioning failed")
    return result


@app.get("/api/kb/registry")
def kb_registry(request: Request):
    """Every kb on disk with its registration state."""
    from softwiki.kb.registry_state import KbRegistry

    require_capability("read.*")
    return {"kbs": KbRegistry().records()}


@app.post("/api/kb/{name}/unregister")
def kb_unregister(name: str, request: Request, reauth_token: Optional[str] = None):
    """Unhook a kb from softwiki.

    This is the inverse of kb creation, **not** a delete: the database, the raw
    documents and the configuration all stay on disk, so registering the same
    name again brings it back. Removing files is an operator concern.
    """
    from softwiki.kb.registry_state import KbRegistry

    require_capability("kb.unregister")
    _reauth_guard(request, reauth_token, "kb.unregister", "kb.unregister")
    identity = current_identity()
    record = KbRegistry().unregister(
        name, unregistered_by=identity.identity if identity else "superuser"
    )
    audit.record(
        "kb.unregister",
        target={"kb": name},
        result="ok",
        detail="data on disk retained",
        source_ip=_client_ip(request),
    )
    return {"name": name, **record.to_dict()}


@app.post("/api/kb/{name}/register")
def kb_register(name: str, request: Request, reauth_token: Optional[str] = None):
    """Bring an unhooked kb back into softwiki."""
    from softwiki.kb.registry_state import KbRegistry

    require_capability("kb.create")
    _reauth_guard(request, reauth_token, "kb.register", "kb.create")
    identity = current_identity()
    try:
        record = KbRegistry().register(
            name, created_by=identity.identity if identity else "superuser"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.record("kb.register", target={"kb": name}, result="ok", source_ip=_client_ip(request))
    return {"name": name, **record.to_dict()}

def _kb_infos_for_caller() -> tuple[str, list, str]:
    """Kbs this caller may see, plus the active one.

    One place for the rule shared by /api/kb and /api/kb/stats: registered on
    disk and inside the identity's ``kb_scope``.
    """
    from softwiki.config import get_workspaces_root
    from softwiki.kb.context import current_kb_name
    from softwiki.kb.registry import list_kb_infos
    from softwiki.kb.registry_state import KbRegistry
    from softwiki.identity.users import visible_kbs

    root = get_workspaces_root()
    registered = set(KbRegistry(root).registered_names())
    identity = current_identity()
    scope = identity.kb_scope if identity else "*"

    infos = [info for info in list_kb_infos(root) if info.name in registered]
    visible = set(visible_kbs(scope, [info.name for info in infos]))
    infos = [info for info in infos if info.name in visible]

    active = current_kb_name() or os.path.basename(get_workspace_dir())
    return root, infos, active


@app.get("/api/kb")
def list_knowledge_bases(verify: bool = False):
    """List knowledge bases with the topics each one covers.

    Only kbs that are (a) registered and (b) inside the caller's ``kb_scope``
    are listed, so an unregistered kb disappears for agents and users alike
    while its data stays on disk.

    ``verify=true`` additionally probes each kb's database, because a directory
    can exist while its database was never created in this instance (the UI
    must not offer a kb that answers with 500). The probe is cached for a few
    seconds; the default stays filesystem-only, per design D1.
    """
    _root, infos, active = _kb_infos_for_caller()

    probed: dict[str, tuple] = {}
    if verify:
        from softwiki.kb.health import probe_kb

        for info in infos:
            probed[info.name] = probe_kb(info.path)

    def _entry(info) -> dict:
        entry = {
            "name": info.name,
            "description": info.description,
            "description_source": info.description_source,
            "language": info.language,
            "tags": info.tags,
            "has_index": info.has_index,
            "web_url": info.web_url,
            "topics": [
                {"group": g.name, "topics": g.topics} for g in info.groups
            ],
        }
        if verify:
            available, reason = probed.get(info.name, (True, None))
            entry["available"] = available
            entry["unavailable_reason"] = reason
        return entry

    return {
        "active": active,
        "verified": verify,
        "kbs": [_entry(info) for info in infos],
    }


#: Per-kb counts are expensive to recompute and change slowly; cache briefly so
#: the home dashboard can poll without opening every kb's database each time.
_KB_STATS_TTL_SECONDS = 30.0
_kb_stats_cache: dict[str, tuple[float, dict]] = {}


def _kb_counts(info) -> dict:
    """Row counts for one kb, read from its own database.

    Returns ``{"available": bool, "reason": str|None, "counts": {...}}`` and
    never raises: a broken/unbuilt kb should render as unavailable on the
    dashboard instead of taking the whole endpoint down.
    """
    from softwiki.config import db_url_for_workspace
    from softwiki.kb.health import probe_kb

    available, reason = probe_kb(info.path)
    if not available:
        return {"available": False, "reason": reason, "counts": None}

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = db_url_for_workspace(info.path)
    engine = create_engine(url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        counts = {
            "documents": db.query(Document).count(),
            "chunks": db.query(Chunk).count(),
            "claims": db.query(Claim).count(),
            "entities": db.query(Entity).count(),
            "relationships": db.query(Relationship).count(),
            "events": db.query(Event).count(),
        }
        return {"available": True, "reason": None, "counts": counts}
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a reason
        return {"available": False, "reason": str(exc)[:200], "counts": None}
    finally:
        db.close()
        engine.dispose()


@app.get("/api/kb/stats")
def kb_stats():
    """Counts for every kb this callers can see, for the cross-kb dashboard.

    The active kb is included with ``active=true``. Kbs whose directory exists
    but whose database was never created in this instance come back with
    ``available=false`` and a reason, so the UI can grey them out instead of
    pretending they have zero documents.
    """
    import time as _time

    _root, infos, active = _kb_infos_for_caller()
    now = _time.monotonic()
    entries = []
    for info in infos:
        cached = _kb_stats_cache.get(info.name)
        if cached and now - cached[0] < _KB_STATS_TTL_SECONDS:
            counts = cached[1]
        else:
            counts = _kb_counts(info)
            _kb_stats_cache[info.name] = (now, counts)
        entries.append({
            "name": info.name,
            "description": info.description,
            "web_url": info.web_url,
            "active": info.name == active,
            **counts,
        })

    totals = {"documents": 0, "chunks": 0, "claims": 0, "entities": 0, "relationships": 0, "events": 0}
    for entry in entries:
        if not entry["counts"]:
            continue
        for key in totals:
            totals[key] += entry["counts"].get(key, 0)

    return {"active": active, "kbs": entries, "totals": totals, "cached_seconds": _KB_STATS_TTL_SECONDS}


#: Pipeline status changes slowly; the page polls, so cache briefly.
_PIPELINE_TTL_SECONDS = 15.0
_pipeline_cache: dict[str, tuple[float, dict]] = {}


def _count_html(root: str) -> int:
    total = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        total += sum(1 for name in filenames if name.endswith(".html"))
    return total


@app.get("/api/kb/pipeline")
def kb_pipeline():
    """Where each stage of this kb stands, and what it depends on.

    The calculation lives in `softwiki.kb.pipeline` because the MCP tool
    `softwiki_pipeline_status` reports the same thing to the assistant; two
    implementations would drift.
    """
    import time as _time

    from softwiki.config import get_workspace_dir
    from softwiki.kb.context import current_kb_name
    from softwiki.kb.pipeline import snapshot

    kb = current_kb_name() or os.path.basename(get_workspace_dir())
    now = _time.monotonic()
    cached = _pipeline_cache.get(kb)
    if cached and now - cached[0] < _PIPELINE_TTL_SECONDS:
        return cached[1]

    ws = get_workspace_dir()
    db = SessionLocal()
    try:
        body = snapshot(db, kb, ws)
        _pipeline_cache[kb] = (now, body)
        return body
    finally:
        db.close()


@app.post("/api/workspace")
def switch_workspace(req: WorkspaceSwitchRequest, request: Request):
    """Switch the active workspace at runtime."""
    require_capability("system.admin")
    if not auth_enabled():
        # Without auth there is no per-user workspace, so this would change the
        # workspace for every caller sharing the process. Use ask(kb=...) instead.
        raise HTTPException(
            status_code=403,
            detail=(
                "Switching the active workspace requires authentication. "
                "Pass kb=<name> to /api/ask instead, or list them with /api/workspaces."
            ),
        )
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

@app.post("/api/kb/switch")
def switch_kb(req: KbSwitchRequest, request: Request):
    """Remember which kb this user is looking at.

    Per user, not per process: two people on the same instance can be in
    different knowledge bases. The kb must be inside the caller's ``kb_scope``;
    switching is a preference, never a privilege escalation.
    """
    from softwiki.config import get_workspaces_root
    from softwiki.identity.users import UserStore, visible_kbs
    from softwiki.kb.registry import list_kb_infos

    identity = getattr(request.state, "identity", None)
    if identity is None or identity.authorization is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    # In `off` mode there is no login: the machine itself is the superuser, so
    # "which kb am I looking at" is a local preference rather than a session.
    # Without this the switcher answered 401 and every kb looked unselectable.
    if not identity.authenticated and not identity.superuser:
        raise HTTPException(status_code=401, detail="Authentication required")

    authz = identity.authorization
    names = [info.name for info in list_kb_infos(get_workspaces_root())]
    if req.kb not in names:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{req.kb}' not found")
    if req.kb not in visible_kbs(authz.kb_scope, names):
        raise HTTPException(status_code=403, detail="Knowledge base not in your scope")

    user = authz.user
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    UserStore().update(user.issuer, user.subject, active_kb=req.kb)
    audit.record("kb.switch", result="ok", target=req.kb, source_ip=identity.source_ip)
    return {"status": "ok", "active": req.kb}


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
    require_capability("system.admin")
    if not auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Switching the active workspace requires authentication.",
        )
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

