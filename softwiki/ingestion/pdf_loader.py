import os
from datetime import datetime
from pypdf import PdfReader
from softwiki.ingestion.normalize import normalize_text

def extract_pdf_content(file_path: str) -> dict:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found at {file_path}")

    reader = PdfReader(file_path)
    metadata = reader.metadata or {}
    title = metadata.get("/Title") or os.path.basename(file_path).replace(".pdf", "").replace("_", " ").replace("-", " ")
    author = metadata.get("/Author") or "Unknown Author"
    
    published_at = None
    creation_date_str = metadata.get("/CreationDate")
    if creation_date_str:
        try:
            date_clean = creation_date_str.replace("D:", "")[:8]
            published_at = datetime.strptime(date_clean, "%Y%m%d")
        except Exception:
            published_at = None
            
    if not published_at:
        try:
            mtime = os.path.getmtime(file_path)
            published_at = datetime.fromtimestamp(mtime)
        except Exception:
            published_at = datetime.utcnow()

    raw_text_parts = []
    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        raw_text_parts.append(page_text)
        
    raw_text = "\n--- Page Break ---\n".join(raw_text_parts)
    cleaned_text = normalize_text(raw_text)

    return {
        "title": str(title),
        "author": str(author),
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "published_at": published_at
    }
