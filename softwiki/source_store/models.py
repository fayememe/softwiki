from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import relationship
from softwiki.source_store.db import Base

class SourceConfig(Base):
    __tablename__ = "sources"

    id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50))  # official, news, think_tank, academic, etc.
    url = Column(String(500))
    trust_level = Column(String(50))  # high, medium, low
    source_country = Column(String(100))
    language = Column(String(10))

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=True)
    source_name = Column(String(200), nullable=True)
    source_type = Column(String(100), nullable=True)
    source_country = Column(String(100), nullable=True)
    published_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow)
    language = Column(String(50), nullable=True)
    author = Column(String(200), nullable=True)
    raw_text = Column(Text, nullable=False)
    cleaned_text = Column(Text, nullable=False)
    hash = Column(String(64), unique=True, nullable=False)
    trust_level = Column(String(50), nullable=True)
    topics = Column(String(500), nullable=True)
    status = Column(String(50), default="completed", nullable=True)
    family_id = Column(String(200), nullable=True, index=True)
    revision = Column(String(80), nullable=True)
    supersedes_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="document", cascade="all, delete-orphan")
    relationships = relationship("Relationship", back_populates="document", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    section = Column(String(200), nullable=True)
    published_at = Column(DateTime, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="chunks")

class Claim(Base):
    __tablename__ = "claims"

    id = Column(String(100), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    actor = Column(String(100), nullable=False)
    topic = Column(String(100), nullable=False)
    stance = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    published_at = Column(DateTime, nullable=True)
    canonical_id = Column(String(100), nullable=True, index=True)
    canonical_key = Column(String(64), nullable=True, index=True)
    status = Column(String(20), default="active", nullable=False, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    value_normalized = Column(String(200), nullable=True)

    document = relationship("Document", back_populates="claims")

class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), unique=True, nullable=False)
    type = Column(String(100), nullable=True)  # person, organization, place, topic, concept, etc.
    description = Column(Text, nullable=True)

class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(150), nullable=False)
    target_name = Column(String(150), nullable=False)
    relation_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    confidence = Column(Float, default=1.0)
    published_at = Column(DateTime, nullable=True)
    canonical_claim_id = Column(String(100), nullable=True, index=True)
    status = Column(String(20), default="active", nullable=False, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="relationships")

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=False)
    topic = Column(String(100), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    confidence = Column(Float, default=1.0)
    canonical_claim_id = Column(String(100), nullable=True, index=True)
    status = Column(String(20), default="active", nullable=False, index=True)

    document = relationship("Document", back_populates="events")


class CanonicalClaim(Base):
    __tablename__ = "canonical_claims"

    id = Column(String(100), primary_key=True)
    canonical_key = Column(String(64), unique=True, nullable=False, index=True)
    text = Column(Text, nullable=False)
    actor = Column(String(100), nullable=False)
    topic = Column(String(100), nullable=False)
    stance = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False, default=0.5)
    status = Column(String(20), default="active", nullable=False, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    supersedes_claim_id = Column(String(100), nullable=True)
    primary_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    primary_page_start = Column(Integer, nullable=True)
    primary_page_end = Column(Integer, nullable=True)
    value_normalized = Column(String(200), nullable=True)
    evidence_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(100), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_id = Column(String(100), ForeignKey("canonical_claims.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    quote = Column(Text, nullable=True)
    quote_hash = Column(String(64), nullable=True)
    source_name = Column(String(200), nullable=True)
    source_revision = Column(String(80), nullable=True)
    trust_level = Column(String(50), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("claim_id", "quote_hash", name="uq_claim_evidence_quote"),
    )


class Contradiction(Base):
    __tablename__ = "contradictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_a_id = Column(String(100), ForeignKey("canonical_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(String(100), ForeignKey("canonical_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(30), nullable=False, default="source_conflict")
    severity = Column(String(20), nullable=False, default="medium")
    status = Column(String(30), nullable=False, default="open", index=True)
    auto_resolved = Column(Boolean, default=False, nullable=False)
    resolution = Column(Text, nullable=True)
    resolved_by = Column(String(80), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("claim_a_id", "claim_b_id", "type", name="uq_contradiction_pair"),
    )


class Adjudication(Base):
    __tablename__ = "adjudications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contradiction_id = Column(Integer, ForeignKey("contradictions.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(40), nullable=False)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    actor = Column(String(80), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WikiArtifactState(Base):
    __tablename__ = "wiki_artifact_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(120), unique=True, nullable=False, index=True)
    prompt_version = Column(String(120), nullable=True)
    model = Column(String(120), nullable=True)
    claim_set_hash = Column(String(64), nullable=True)
    status_counts_json = Column(Text, nullable=True)
    built_at = Column(DateTime, nullable=True)
    stale_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="editor")
    active_workspace = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), nullable=False)
    workspace = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")

    __table_args__ = (UniqueConstraint("username", "workspace", name="uq_workspace_member"),)
