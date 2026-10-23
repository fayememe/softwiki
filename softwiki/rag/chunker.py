import re
from datetime import datetime
from typing import List, Dict, Any

PAGE_BREAK = "--- Page Break ---"


def _page_ranges(text: str) -> List[Dict[str, int]]:
    if PAGE_BREAK not in text:
        return []
    ranges = []
    cursor = 0
    for page_no, part in enumerate(text.split(PAGE_BREAK), 1):
        start = cursor
        end = start + len(part)
        ranges.append({"page_no": page_no, "start": start, "end": end})
        cursor = end + len(PAGE_BREAK)
    return ranges


def _page_for_offset(ranges: List[Dict[str, int]], offset: int | None) -> int | None:
    if not ranges or offset is None:
        return None
    for item in ranges:
        if item["start"] <= offset < item["end"]:
            return item["page_no"]
    if offset < ranges[0]["start"]:
        return ranges[0]["page_no"]
    return ranges[-1]["page_no"]

def _split_oversized(text: str, size: int, overlap: int) -> List[str]:
    overlap = max(0, min(overlap, size // 4))
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        pieces.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return pieces


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    if not text:
        return []
    if chunk_size <= 0:
        chunk_size = 1000
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 4))

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_length = 0
    current_section = "General"
    header_pattern = re.compile(r'^#+\s+(.+)$')

    def flush():
        nonlocal current_chunk, current_length
        if current_chunk:
            chunks.append({"text": "\n\n".join(current_chunk), "section": current_section})
            current_chunk = []
            current_length = 0

    def add_piece(piece: str):
        nonlocal current_chunk, current_length
        if len(piece) > chunk_size:
            flush()
            for part in _split_oversized(piece, chunk_size, chunk_overlap):
                chunks.append({"text": part, "section": current_section})
            return
        if current_chunk and current_length + 2 + len(piece) > chunk_size:
            flush()
        separator = 2 if current_chunk else 0
        current_chunk.append(piece)
        current_length += separator + len(piece)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        header_match = header_pattern.match(para)
        if header_match:
            current_section = header_match.group(1)
        if len(para) <= chunk_size:
            add_piece(para)
            continue
        flush()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?。！？])\s*', para) if s.strip()]
        for sentence in sentences:
            add_piece(sentence)
    flush()

    cursor = 0
    for chunk in chunks:
        piece = chunk["text"]
        probe = piece[:40]
        offset = text.find(probe, cursor) if probe else -1
        if offset < 0 and probe:
            offset = text.find(probe)
        if offset < 0:
            offset = cursor
        chunk["start"] = offset
        chunk["end"] = min(offset + len(piece), len(text))
        cursor = max(cursor, chunk["end"])
    return chunks

def build_document_chunks(
    doc_id: int,
    text: str,
    metadata: Dict[str, Any],
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    page_ranges = _page_ranges(text)
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
        
    for rc in raw_chunks:
        section = rc["section"]
        body_text = rc["text"].replace(PAGE_BREAK, "").strip()
        if not body_text:
            continue

        start = rc.get("start")
        end = rc.get("end")
        page_start = _page_for_offset(page_ranges, start)
        page_end = _page_for_offset(page_ranges, max((end or 0) - 1, start or 0))

        header = f"[Document: {title} | Source: {source_name}"
        if date_str:
            header += f" | Date: {date_str}"
        if page_start is not None:
            if page_end is not None and page_end != page_start:
                header += f" | Pages: {page_start}-{page_end}"
            else:
                header += f" | Page: {page_start}"
        if section and section != "General":
            header += f" | Section: {section}"
        header += "]\n"

        context_text = header + body_text

        processed_chunks.append({
            "document_id": doc_id,
            "chunk_index": len(processed_chunks),
            "text": context_text,
            "title": title,
            "section": section,
            "published_at": published_at,
            "page_start": page_start,
            "page_end": page_end,
            "char_start": start,
            "char_end": end,
        })

    return processed_chunks
