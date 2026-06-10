import re
from datetime import datetime
from typing import List, Dict, Any

def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    if not text:
        return []

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_length = 0
    current_section = "General"

    header_pattern = re.compile(r'^#+\s+(.+)$')

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        header_match = header_pattern.match(para)
        if header_match:
            current_section = header_match.group(1)
            
        para_len = len(para)
        
        if para_len > chunk_size:
            if current_chunk:
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "section": current_section
                })
                current_chunk = []
                current_length = 0
                
            sentences = re.split(r'(?<=[.!?]) +', para)
            for sentence in sentences:
                sentence_len = len(sentence)
                if current_length + sentence_len > chunk_size and current_chunk:
                    chunks.append({
                        "text": " ".join(current_chunk),
                        "section": current_section
                    })
                    overlap_chunk = []
                    overlap_len = 0
                    for s in reversed(current_chunk):
                        if overlap_len + len(s) < chunk_overlap:
                            overlap_chunk.insert(0, s)
                            overlap_len += len(s)
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_length = overlap_len
                
                current_chunk.append(sentence)
                current_length += sentence_len
        else:
            if current_length + para_len > chunk_size and current_chunk:
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "section": current_section
                })
                if para_len < chunk_overlap:
                    current_chunk = [current_chunk[-1]] if current_chunk else []
                    current_length = len(current_chunk[0]) if current_chunk else 0
                else:
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(para)
            current_length += para_len

    if current_chunk:
        chunks.append({
            "text": "\n\n".join(current_chunk),
            "section": current_section
        })

    return chunks

def build_document_chunks(
    doc_id: int,
    text: str,
    metadata: Dict[str, Any],
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    raw_chunks = chunk_text(text, chunk_size, chunk_overlap)
    processed_chunks = []
    
    title = metadata.get("title", "Untitled")
    source_name = metadata.get("source_name", "Unknown Source")
    published_at = metadata.get("published_at")
    
    date_str = ""
    if isinstance(published_at, datetime):
        date_str = published_at.strftime("%Y-%m-%d")
    elif isinstance(published_at, str):
        date_str = published_at[:10]
        
    for idx, rc in enumerate(raw_chunks):
        section = rc["section"]
        body_text = rc["text"]
        
        header = f"[Document: {title} | Source: {source_name}"
        if date_str:
            header += f" | Date: {date_str}"
        if section and section != "General":
            header += f" | Section: {section}"
        header += "]\n"
        
        context_text = header + body_text
        
        processed_chunks.append({
            "document_id": doc_id,
            "chunk_index": idx,
            "text": context_text,
            "title": title,
            "section": section,
            "published_at": published_at
        })
        
    return processed_chunks
