from typing import List, Dict, Any

class CitationManager:
    def __init__(self):
        self.doc_id_to_num = {}
        self.citations = []

    def get_citation_num(self, doc_id: int, metadata: Dict[str, Any]) -> int:
        page_start = metadata.get("page_start")
        page_end = metadata.get("page_end")
        key = (doc_id, page_start, page_end)
        if key in self.doc_id_to_num:
            return self.doc_id_to_num[key]
            
        num = len(self.citations) + 1
        self.doc_id_to_num[key] = num
        
        title = metadata.get("title", "Unknown Title")
        url = metadata.get("url")
        source_name = metadata.get("source_name", "Unknown Source")
        published_at = metadata.get("published_at")
        
        date_str = ""
        if published_at:
            if hasattr(published_at, "strftime"):
                date_str = published_at.strftime("%Y-%m-%d")
            else:
                date_str = str(published_at)[:10]
                
        ref = f"{source_name}. \"{title}\""
        if date_str:
            ref += f" ({date_str})"
        if page_start is not None:
            if page_end is not None and page_end != page_start:
                ref += f", pp.{page_start}-{page_end}"
            else:
                ref += f", p.{page_start}"
        if url:
            ref += f". Available at: {url}"
            
        self.citations.append({
            "num": num,
            "doc_id": doc_id,
            "text": ref,
            "url": url,
            "title": title,
            "source_name": source_name,
            "published_at": date_str,
            "page_start": page_start,
            "page_end": page_end,
        })
        return num

    def render_citations(self) -> str:
        if not self.citations:
            return ""
        lines = ["\n### Sources & Citations\n"]
        for c in self.citations:
            lines.append(f"[{c['num']}] {c['text']}")
        return "\n".join(lines)
