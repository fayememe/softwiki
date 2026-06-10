from typing import List, Dict, Any

class CitationManager:
    def __init__(self):
        self.doc_id_to_num = {}
        self.citations = []

    def get_citation_num(self, doc_id: int, metadata: Dict[str, Any]) -> int:
        if doc_id in self.doc_id_to_num:
            return self.doc_id_to_num[doc_id]
            
        num = len(self.citations) + 1
        self.doc_id_to_num[doc_id] = num
        
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
        if url:
            ref += f". Available at: {url}"
            
        self.citations.append({
            "num": num,
            "doc_id": doc_id,
            "text": ref,
            "url": url,
            "title": title,
            "source_name": source_name,
            "published_at": date_str
        })
        return num

    def render_citations(self) -> str:
        if not self.citations:
            return ""
        lines = ["\n### Sources & Citations\n"]
        for c in self.citations:
            lines.append(f"[{c['num']}] {c['text']}")
        return "\n".join(lines)
