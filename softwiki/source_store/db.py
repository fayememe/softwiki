import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from softwiki.config import get_db_url

Base = declarative_base()

# Engines are keyed by database URL so that a multi-kb instance does not tear
# a pool down every time it serves a different kb. The cache is bounded: with
# one database per kb the number can otherwise grow with the number of kbs.
_ENGINE_CACHE_MAX = int(os.getenv("SOFTWIKI_ENGINE_CACHE_MAX", "32"))
_engines = {}
_engine_order = []  # least-recently-used first
_sessionmakers = {}


def _dispose_evicted_engine(engine) -> None:
    try:
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - disposal failure must not break requests
        print(f"[db] failed to dispose engine: {exc}", flush=True)


def get_engine():
    db_url = get_db_url()
    engine = _engines.get(db_url)
    if engine is not None:
        try:
            _engine_order.remove(db_url)
        except ValueError:
            pass
        _engine_order.append(db_url)
        return engine

    # SQLite in-process access needs the flag; PostgreSQL rejects it.
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args)
    _engines[db_url] = engine
    _engine_order.append(db_url)

    # Evict least recently used engines beyond the cap (never the one just added).
    while len(_engine_order) > max(1, _ENGINE_CACHE_MAX):
        stale_url = _engine_order.pop(0)
        stale = _engines.pop(stale_url, None)
        _sessionmakers.pop(stale_url, None)
        if stale is not None:
            _dispose_evicted_engine(stale)

    return engine

def get_sessionmaker():
    engine = get_engine()
    key = str(engine.url)
    sessionmaker_for_url = _sessionmakers.get(key)
    if sessionmaker_for_url is None or sessionmaker_for_url.kw.get("bind") is not engine:
        # Auto-create tables for the active engine
        init_tables()
        sessionmaker_for_url = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        _sessionmakers[key] = sessionmaker_for_url
    return sessionmaker_for_url

def get_db():
    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()

def _ensure_columns(engine, table, columns):
    from sqlalchemy import inspect, text
    existing = {c["name"] for c in inspect(engine).get_columns(table)}
    for name, ddl in columns:
        if name not in existing:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _ensure_indexes(engine, statements):
    from sqlalchemy import text
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:
            print(f"Index migration skipped ({stmt}): {e}")


def init_tables():
    """Utility to create tables in the active workspace database."""
    # Import models so Base.metadata is populated even when the caller has
    # not imported the ORM models yet.
    from softwiki.source_store import models as _models  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    try:
        _ensure_columns(engine, "documents", [
            ("status", "VARCHAR(50) DEFAULT 'completed'"),
            ("family_id", "VARCHAR(200)"),
            ("revision", "VARCHAR(80)"),
            ("supersedes_document_id", "INTEGER"),
        ])
        _ensure_columns(engine, "chunks", [
            ("page_start", "INTEGER"),
            ("page_end", "INTEGER"),
            ("char_start", "INTEGER"),
            ("char_end", "INTEGER"),
        ])
        _ensure_columns(engine, "claims", [
            ("canonical_id", "VARCHAR(100)"),
            ("canonical_key", "VARCHAR(64)"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("valid_from", "TIMESTAMP"),
            ("valid_to", "TIMESTAMP"),
            ("value_normalized", "VARCHAR(200)"),
            ("subject", "VARCHAR(300)"),
            ("predicate", "VARCHAR(200)"),
            ("object", "VARCHAR(500)"),
            ("qualifiers", "TEXT"),
            ("structure_hash", "VARCHAR(64)"),
        ])
        _ensure_columns(engine, "canonical_claims", [
            ("subject", "VARCHAR(300)"),
            ("predicate", "VARCHAR(200)"),
            ("object", "VARCHAR(500)"),
            ("qualifiers", "TEXT"),
            ("structure_hash", "VARCHAR(64)"),
        ])
        _ensure_columns(engine, "entities", [
            ("normalized_name", "VARCHAR(200)"),
            ("aliases", "TEXT"),
            ("merged_into", "INTEGER"),
        ])
        _ensure_columns(engine, "relationships", [
            ("canonical_claim_id", "VARCHAR(100)"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("valid_from", "TIMESTAMP"),
            ("valid_to", "TIMESTAMP"),
            ("source_entity_id", "INTEGER"),
            ("target_entity_id", "INTEGER"),
            ("weight", "FLOAT DEFAULT 1.0"),
            ("evidence_count", "INTEGER DEFAULT 1"),
        ])
        _ensure_columns(engine, "wiki_rebuild_tasks", [
            ("kind", "VARCHAR(20) DEFAULT 'topic'"),
        ])
        _ensure_columns(engine, "events", [
            ("canonical_claim_id", "VARCHAR(100)"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
        ])
        _ensure_indexes(engine, [
            "CREATE INDEX IF NOT EXISTS ix_documents_family_id ON documents (family_id)",
            "CREATE INDEX IF NOT EXISTS ix_entities_normalized_name ON entities (normalized_name)",
            "CREATE INDEX IF NOT EXISTS ix_entities_merged_into ON entities (merged_into)",
            "CREATE INDEX IF NOT EXISTS ix_entity_aliases_normalized ON entity_aliases (normalized)",
            "CREATE INDEX IF NOT EXISTS ix_relationships_source_entity_id ON relationships (source_entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_relationships_target_entity_id ON relationships (target_entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_relationships_status_weight ON relationships (status, weight)",
            "CREATE INDEX IF NOT EXISTS ix_claims_canonical_id ON claims (canonical_id)",
            "CREATE INDEX IF NOT EXISTS ix_claims_canonical_key ON claims (canonical_key)",
            "CREATE INDEX IF NOT EXISTS ix_claims_status ON claims (status)",
            "CREATE INDEX IF NOT EXISTS ix_claims_structure_hash ON claims (structure_hash)",
            "CREATE INDEX IF NOT EXISTS ix_canonical_claims_structure_hash ON canonical_claims (structure_hash)",
            "CREATE INDEX IF NOT EXISTS ix_relationships_canonical_claim_id ON relationships (canonical_claim_id)",
            "CREATE INDEX IF NOT EXISTS ix_relationships_status ON relationships (status)",
            "CREATE INDEX IF NOT EXISTS ix_events_canonical_claim_id ON events (canonical_claim_id)",
            "CREATE INDEX IF NOT EXISTS ix_events_status ON events (status)",
        ])
    except Exception as e:
        print(f"Database migration failed: {e}")

class SessionLocal:
    """Wrapper class that dynamically resolves sessionmaker based on current workspace."""
    def __new__(cls, *args, **kwargs):
        return get_sessionmaker()(*args, **kwargs)

