"""Pipeline snapshot for one knowledge base.

One implementation shared by `GET /api/kb/pipeline` (the 资料流程 page) and the
MCP tool `softwiki_pipeline_status`, so the agent and the UI can never disagree
about what is stale.

The pipeline is two branches, not one line:

    documents ──extract──> claims ──project──> graph / timeline
        │                    └──compose──> wiki pages ──publish──> static portal
        └──chunk/embed──> retrieval index
"""

import os
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

#: kb -> operation currently running in this process ("index"). Long operations
#: cannot be seen from the database, so they report themselves here.
BUILDING: Dict[str, str] = {}

from softwiki.source_store.models import (
    CanonicalClaim,
    Chunk,
    Claim,
    Document,
    Entity,
    Event,
    Relationship,
    WikiArtifactState,
    WikiRebuildTask,
)


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else None


def _count_html(root: str) -> int:
    total = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        total += sum(1 for name in filenames if name.endswith(".html"))
    return total


def snapshot(db: Session, kb: str, workspace: str) -> Dict:
    status_rows = db.query(Document.status, func.count(Document.id)).group_by(Document.status).all()
    doc_status = {(status or "completed"): int(count) for status, count in status_rows}
    docs_total = sum(doc_status.values())
    docs_unfinished = sum(doc_status.get(key, 0) for key in ("pending", "extracting", "failed"))
    oldest_unfinished = (
        db.query(func.min(Document.collected_at))
        .filter(Document.status.in_(("pending", "extracting")))
        .scalar()
    )

    chunks = db.query(func.count(Chunk.id)).scalar() or 0
    docs_without_chunks = (
        db.query(func.count(Document.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .filter(Chunk.id.is_(None))
        .scalar()
        or 0
    )

    claims_raw = db.query(func.count(Claim.id)).scalar() or 0
    canonical = db.query(func.count(CanonicalClaim.id)).scalar() or 0
    disputed = (
        db.query(func.count(CanonicalClaim.id))
        .filter(CanonicalClaim.status == "disputed")
        .scalar()
        or 0
    )
    docs_without_claims = (
        db.query(func.count(Document.id))
        .outerjoin(Claim, Claim.document_id == Document.id)
        .filter(Claim.id.is_(None))
        .scalar()
        or 0
    )

    entities = db.query(func.count(Entity.id)).scalar() or 0
    relationships = db.query(func.count(Relationship.id)).scalar() or 0
    rel_unprojected = (
        db.query(func.count(Relationship.id))
        .filter(Relationship.canonical_claim_id.is_(None))
        .scalar()
        or 0
    )
    docs_without_relationships = (
        db.query(func.count(Document.id))
        .outerjoin(Relationship, Relationship.document_id == Document.id)
        .filter(Relationship.id.is_(None))
        .scalar()
        or 0
    )

    events = db.query(func.count(Event.id)).scalar() or 0
    events_unprojected = (
        db.query(func.count(Event.id))
        .filter(Event.canonical_claim_id.is_(None))
        .scalar()
        or 0
    )

    wiki_stale = (
        db.query(func.count(WikiArtifactState.id))
        .filter(WikiArtifactState.stale_at.is_not(None))
        .scalar()
        or 0
    )
    task_rows = (
        db.query(WikiRebuildTask.status, func.count(WikiRebuildTask.id))
        .group_by(WikiRebuildTask.status)
        .all()
    )
    tasks = {status: int(count) for status, count in task_rows}
    # Who is being generated right now (or next in line), so the UI can show
    # actual work instead of just a number.
    active_rows = (
        db.query(WikiRebuildTask)
        .filter(WikiRebuildTask.status.in_(("pending", "running")))
        .order_by(WikiRebuildTask.status.desc(), WikiRebuildTask.updated_at.asc())
        .limit(8)
        .all()
    )
    active_tasks = [
        {
            "topic": row.topic,
            "kind": getattr(row, "kind", "topic"),
            "status": row.status,
            "attempts": row.attempts,
            "started_at": row.started_at.isoformat() + "Z" if row.started_at else None,
        }
        for row in active_rows
    ]

    doc_unfinished_detail = {
        key: doc_status.get(key, 0) for key in ("pending", "extracting", "failed")
    }

    vectors = None
    try:
        vectors = db.execute(text("SELECT count(*) FROM chunk_embeddings")).scalar()
    except Exception:
        db.rollback()
        vectors = None

    from softwiki.config import get_index_path
    from softwiki.wiki.subject_pages import list_generated_pages

    pages = list_generated_pages(db)
    wiki_subjects = len(pages.get("subjects") or [])
    wiki_generated = bool(pages.get("generated"))
    wiki_built_at = db.query(func.max(WikiArtifactState.built_at)).scalar()
    # Subject pages are files (exports/wiki/pages/index.json); the artifact table
    # only tracks curated topic pages. Use whichever is newer for "built".
    pages_index = os.path.join(workspace, "exports", "wiki", "pages", "index.json")
    pages_mtime = os.path.getmtime(pages_index) if os.path.exists(pages_index) else None
    built_candidates = [ts for ts in (
        wiki_built_at.timestamp() if wiki_built_at else None, pages_mtime
    ) if ts]
    built_at = max(built_candidates) if built_candidates else None

    bm25_path = get_index_path("bm25_index.pkl")
    bm25_mtime = os.path.getmtime(bm25_path) if os.path.exists(bm25_path) else None

    portal_root = os.path.join(workspace, "exports", "wikiweb", kb)
    portal_index = os.path.join(portal_root, "index.html")
    portal_exists = os.path.exists(portal_index)
    portal_mtime = os.path.getmtime(portal_index) if portal_exists else None
    portal_pages = _count_html(portal_root) if portal_exists else 0

    index_stale = docs_total > 0 and (
        chunks == 0
        or docs_without_chunks > 0
        or (vectors is not None and vectors < chunks)
    )
    portal_older = bool(
        portal_exists
        and wiki_built_at is not None
        and portal_mtime is not None
        and portal_mtime < wiki_built_at.timestamp()
    )

    return {
        "kb": kb,
        "documents": {
            "total": docs_total,
            "by_status": doc_status,
            "unfinished": docs_unfinished,
            "in_progress": doc_unfinished_detail,
            "without_chunks": docs_without_chunks,
            "without_claims": docs_without_claims,
            "without_relationships": docs_without_relationships,
            "oldest_unfinished": (
                oldest_unfinished.isoformat() + "Z" if oldest_unfinished else None
            ),
        },
        "index": {
            "building": BUILDING.get(kb),
            "chunks": int(chunks),
            "vectors": vectors,
            "vector_backend": os.getenv("SOFTWIKI_VECTOR_BACKEND", "file"),
            "bm25_built_at": _iso(bm25_mtime),
            "stale": index_stale,
        },
        "claims": {
            "raw": int(claims_raw),
            "canonical": int(canonical),
            "disputed": int(disputed),
            "running": docs_unfinished > 0,
        },
        "graph": {
            "entities": int(entities),
            "relationships": int(relationships),
            "unprojected": int(rel_unprojected),
            "stale": canonical > 0 and entities == 0,
        },
        "timeline": {
            "events": int(events),
            "unprojected": int(events_unprojected),
            "stale": canonical > 0 and events == 0,
        },
        "wiki": {
            "generated": wiki_generated,
            "subject_pages": wiki_subjects,
            "stale": int(wiki_stale),
            "tasks": tasks,
            "running": (tasks.get("pending", 0) + tasks.get("running", 0)) > 0,
            "active": active_tasks,
            "built_at": _iso(built_at),
        },
        "portal": {
            "exists": portal_exists,
            "built_at": _iso(portal_mtime),
            "pages": portal_pages,
            "stale": portal_older or (portal_exists is False and wiki_subjects > 0),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def describe(snap: Dict) -> str:
    """Render the snapshot as a short management report (used by MCP)."""
    d = snap["documents"]
    idx = snap["index"]
    claims = snap["claims"]
    graph = snap["graph"]
    timeline = snap["timeline"]
    wiki = snap["wiki"]
    portal = snap["portal"]

    def line(ok: bool, text_: str) -> str:
        return f"- {'OK ' if ok else 'NEEDS WORK'} {text_}"

    lines = [
        f"知识库：{snap['kb']}",
        "检索链路：",
        line(not idx["stale"], f"索引 {idx['chunks']} 分块 / {idx['vectors']} 向量"
             + ("（需重建）" if idx["stale"] else "")),
        line(d["without_chunks"] == 0, f"无分块文档 {d['without_chunks']}"),
        "",
        "知识链路：",
        line(d["unfinished"] == 0, f"文档 {d['total']} 篇，待抽取 {d['unfinished']}"),
        line(claims["canonical"] > 0, f"论断 {claims['raw']} → 规范化 {claims['canonical']}"
             f"（争议 {claims['disputed']}）"),
        line(graph["unprojected"] == 0, f"图谱 {graph['entities']} 实体 / {graph['relationships']} 关系，"
             f"未挂 claim {graph['unprojected']}"),
        line(timeline["unprojected"] == 0, f"时间线 {timeline['events']} 事件，"
             f"未挂 claim {timeline['unprojected']}"),
        "",
        "发布链路：",
        line(wiki["generated"] and wiki["stale"] == 0,
             f"Wiki 页面 {wiki['subject_pages']} 个，过期 {wiki['stale']}，"
             f"队列 {wiki['tasks']}"),
        line(portal["exists"] and not portal["stale"],
             f"静态门户 {'已生成' if portal['exists'] else '未生成'}，{portal['pages']} 页"
             + (f"，生成于 {portal['built_at']}" if portal["built_at"] else "")),
    ]
    return "\n".join(lines)
