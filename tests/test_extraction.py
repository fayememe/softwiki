from datetime import datetime
from softwiki.extraction.claim_extractor import ClaimExtractor

def test_heuristic_claim_extractor():
    extractor = ClaimExtractor()
    # Mock config load
    extractor.topics = {
        "decoupling": {"aliases": ["decoupled interface", "decouple"]},
        "common-protocol": {"aliases": ["common Project Alpha protocol"]},
        "expansion": {"aliases": []}
    }
    doc_id = 42
    published_at = datetime(2024, 10, 23)
    
    text = "Company is cautious about a common Project Alpha protocol. Main Team prefers local adaptation."
    
    claims = extractor._fallback_extract_claims(doc_id, text, published_at)
    assert len(claims) > 0
    
    p_claims = [c for c in claims if c.actor == "Company"]
    assert len(p_claims) > 0
    
    common_protocol_claims = [c for c in p_claims if c.topic == "common-protocol"]
    if common_protocol_claims:
        assert common_protocol_claims[0].stance == "cautious"
