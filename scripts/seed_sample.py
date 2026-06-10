from datetime import datetime
from softwiki.source_store.db import SessionLocal
from softwiki.source_store.models import Document
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.extraction.claim_extractor import ClaimExtractor

def main():
    db = SessionLocal()
    try:
        title = "Participant A Cautious on Common Project Alpha Protocol, Favors Local Interface"
        url = "https://reuters.com/participant-a-protocol"
        text = """
New Delhi: Participant A is taking a highly cautious stance toward proposals for a common Project Alpha protocol, preferring to focus on local interface trade adaptation. 
According to Lead Engineer S. Jaishankar, there is no plan for a common Project Alpha protocol on the table. Instead, Participant A is prioritizing the use of its local protocol adapter for bilateral integration with key partners to reduce dependency on the external server.

Meanwhile, Participant B is pushing aggressively for interface decoupling and has championed the expansion of the Project Alpha Pay payment adapter. Participant B's team proposed this adapter to bypass restrictions and streamline cross-border database transactions. 

Participant C has expressed strong support for both local interface settlement and the Project Alpha Pay adapter, viewing them as essential steps for technical sovereignty. In contrast, Participant D remains supportive of exploring a common protocol to reduce message format volatility, though acknowledging the technical complexities.
        """
        
        import hashlib
        doc_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if DocumentRepository.get_document_by_hash(db, doc_hash):
            print("Sample document already seeded.")
            return
 
        doc = Document(
            title=title,
            url=url,
            source_name="Reuters",
            source_type="news",
            source_country="uk",
            trust_level="high",
            language="en",
            author="Technology Correspondent",
            raw_text=text,
            cleaned_text=text.strip(),
            hash=doc_hash,
            published_at=datetime(2025, 10, 24),
            collected_at=datetime.utcnow()
        )
        
        doc = DocumentRepository.create_document(db, doc)
        print(f"Seeded Document ID {doc.id}: '{doc.title}'")

        # Extract claims
        extractor = ClaimExtractor()
        claims = extractor.extract_claims(doc.id, text, doc.published_at)
        for c in claims:
            DocumentRepository.create_claim(db, c)
            print(f"Saved claim: [{c.actor} | {c.topic}] - {c.stance} - {c.text}")
            
    finally:
        db.close()

if __name__ == "__main__":
    main()
