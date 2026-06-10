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

def init_tables():
    """Utility to create tables in the active workspace database."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    
    # Check if 'status' column exists in 'documents' (migration for existing database schemas)
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("documents")]
        if "status" not in columns:
            with engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(text("ALTER TABLE documents ADD COLUMN status VARCHAR(50) DEFAULT 'completed'"))
    except Exception as e:
        print(f"Database migration failed: {e}")

class SessionLocal:
    """Wrapper class that dynamically resolves sessionmaker based on current workspace."""
    def __new__(cls, *args, **kwargs):
        return get_sessionmaker()(*args, **kwargs)

