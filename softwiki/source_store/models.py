from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
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

    document = relationship("Document", back_populates="events")

