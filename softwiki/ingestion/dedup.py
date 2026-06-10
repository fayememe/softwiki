import hashlib
from sqlalchemy.orm import Session
from softwiki.source_store.document_repo import DocumentRepository

def calculate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def is_duplicate_hash(db: Session, text_hash: str) -> bool:
    doc = DocumentRepository.get_document_by_hash(db, text_hash)
    return doc is not None

def is_duplicate_url(db: Session, url: str) -> bool:
    if not url:
        return False
    doc = DocumentRepository.get_document_by_url(db, url)
    return doc is not None
