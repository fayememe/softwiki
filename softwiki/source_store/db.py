import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from softwiki.config import get_db_url

Base = declarative_base()

# Lazy database engines to adapt to changing workspaces at runtime
_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    db_url = get_db_url()
    # If engine is not initialized, or the active database URL has changed
    if _engine is None or str(_engine.url) != db_url:
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        _engine = create_engine(db_url, connect_args=connect_args)
    return _engine

def get_sessionmaker():
    global _SessionLocal
    engine = get_engine()
    # Re-bind sessionmaker if engine changes
    if _SessionLocal is None or _SessionLocal.kw.get("bind") != engine:
        # Auto-create tables for the active engine
        init_tables()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal

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
        _ensure_columns(engine, "relationships", [
            ("canonical_claim_id", "VARCHAR(100)"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("valid_from", "TIMESTAMP"),
            ("valid_to", "TIMESTAMP"),
        ])
        _ensure_columns(engine, "events", [
            ("canonical_claim_id", "VARCHAR(100)"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
        ])
        _ensure_indexes(engine, [
            "CREATE INDEX IF NOT EXISTS ix_documents_family_id ON documents (family_id)",
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

