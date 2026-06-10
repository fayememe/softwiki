from sqlalchemy.orm import Session
from typing import List, Optional
from softwiki.source_store.models import Document, Chunk, Claim, SourceConfig, Entity, Relationship, Event

class DocumentRepository:
    @staticmethod
    def get_document(db: Session, doc_id: int) -> Optional[Document]:
        return db.query(Document).filter(Document.id == doc_id).first()

    @staticmethod
    def get_document_by_hash(db: Session, doc_hash: str) -> Optional[Document]:
        return db.query(Document).filter(Document.hash == doc_hash).first()

    @staticmethod
    def get_document_by_url(db: Session, url: str) -> Optional[Document]:
        return db.query(Document).filter(Document.url == url).first()

    @staticmethod
    def create_document(db: Session, document: Document) -> Document:
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def get_all_documents(db: Session) -> List[Document]:
        return db.query(Document).all()

    @staticmethod
    def create_chunks(db: Session, chunks: List[Chunk]) -> List[Chunk]:
        db.add_all(chunks)
        db.commit()
        return chunks

    @staticmethod
    def delete_document_chunks(db: Session, doc_id: int):
        db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
        db.commit()

    @staticmethod
    def get_all_chunks(db: Session) -> List[Chunk]:
        return db.query(Chunk).all()

    @staticmethod
    def get_chunks_by_ids(db: Session, chunk_ids: List[int]) -> List[Chunk]:
        return db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()

    @staticmethod
    def create_claim(db: Session, claim: Claim) -> Claim:
        existing = db.query(Claim).filter(Claim.id == claim.id).first()
        if existing:
            existing.text = claim.text
            existing.actor = claim.actor
            existing.topic = claim.topic
            existing.stance = claim.stance
            existing.confidence = claim.confidence
            existing.published_at = claim.published_at
            db.commit()
            db.refresh(existing)
            return existing
        else:
            db.add(claim)
            db.commit()
            db.refresh(claim)
            return claim

    @staticmethod
    def get_claims_by_topic(db: Session, topic: str) -> List[Claim]:
        return db.query(Claim).filter(Claim.topic == topic).all()

    @staticmethod
    def get_claims_by_actor(db: Session, actor: str) -> List[Claim]:
        return db.query(Claim).filter(Claim.actor == actor).all()

    @staticmethod
    def get_claims_by_actor_and_topic(db: Session, actor: str, topic: str) -> List[Claim]:
        return db.query(Claim).filter(Claim.actor == actor, Claim.topic == topic).all()

    @staticmethod
    def get_all_claims(db: Session) -> List[Claim]:
        return db.query(Claim).all()

    @staticmethod
    def save_source_config(db: Session, source: SourceConfig) -> SourceConfig:
        existing = db.query(SourceConfig).filter(SourceConfig.id == source.id).first()
        if existing:
            existing.name = source.name
            existing.type = source.type
            existing.url = source.url
            existing.trust_level = source.trust_level
            existing.source_country = source.source_country
            existing.language = source.language
            db.commit()
            db.refresh(existing)
            return existing
        else:
            db.add(source)
            db.commit()
            db.refresh(source)
            return source

    @staticmethod
    def get_source_config(db: Session, source_id: str) -> Optional[SourceConfig]:
        return db.query(SourceConfig).filter(SourceConfig.id == source_id).first()

    @staticmethod
    def get_all_source_configs(db: Session) -> List[SourceConfig]:
        return db.query(SourceConfig).all()

    # --- Entity operations ---
    @staticmethod
    def get_entity_by_name(db: Session, name: str) -> Optional[Entity]:
        return db.query(Entity).filter(Entity.name == name).first()

    @staticmethod
    def create_entity(db: Session, entity: Entity) -> Entity:
        existing = db.query(Entity).filter(Entity.name == entity.name).first()
        if existing:
            if entity.type: existing.type = entity.type
            if entity.description: existing.description = entity.description
            db.commit()
            db.refresh(existing)
            return existing
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    @staticmethod
    def get_all_entities(db: Session) -> List[Entity]:
        return db.query(Entity).all()

    # --- Relationship operations ---
    @staticmethod
    def create_relationship(db: Session, rel: Relationship) -> Relationship:
        db.add(rel)
        db.commit()
        db.refresh(rel)
        return rel

    @staticmethod
    def get_all_relationships(db: Session) -> List[Relationship]:
        return db.query(Relationship).all()

    @staticmethod
    def get_relationships_by_document(db: Session, doc_id: int) -> List[Relationship]:
        return db.query(Relationship).filter(Relationship.document_id == doc_id).all()

    # --- Event operations ---
    @staticmethod
    def create_event(db: Session, event: Event) -> Event:
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def get_all_events(db: Session) -> List[Event]:
        return db.query(Event).all()

    @staticmethod
    def get_events_by_document(db: Session, doc_id: int) -> List[Event]:
        return db.query(Event).filter(Event.document_id == doc_id).all()

    @staticmethod
    def get_events_by_topic(db: Session, topic: str) -> List[Event]:
        return db.query(Event).filter(Event.topic == topic).all()

