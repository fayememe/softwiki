import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from softwiki.config import get_workspaces_root
from softwiki.source_store.db import Base
from softwiki.source_store.models import User, WorkspaceMember

_engine = None
_sessionmaker = None


def get_auth_engine():
    global _engine
    url = os.getenv("SOFTWIKI_AUTH_DB")
    if not url:
        root = get_workspaces_root()
        os.makedirs(root, exist_ok=True)
        url = f"sqlite:///{os.path.join(root, '.softwiki-auth.db')}"
    if _engine is None or str(_engine.url) != url:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args)
        Base.metadata.create_all(_engine, tables=[User.__table__, WorkspaceMember.__table__])
    return _engine


def get_auth_session():
    global _sessionmaker
    engine = get_auth_engine()
    if _sessionmaker is None or _sessionmaker.kw.get("bind") is not engine:
        _sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _sessionmaker()
