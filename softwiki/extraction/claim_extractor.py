import os
import json
import yaml
from typing import List, Dict, Any
from datetime import datetime
from softwiki.source_store.models import Claim
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.config import get_config_path

class ClaimExtractor:
    def __init__(self):
        # We will load dynamically when calling extract_claims to adjust to dynamic workspace
        pass

    def load_configs(self):
        self.topics = {}
        topics_path = get_config_path("topics.yaml")
        if os.path.exists(topics_path):
            try:
                with open(topics_path, "r", encoding="utf-8") as f:
                    self.topics = yaml.safe_load(f).get("topics", {}) or {}
            except Exception as e:
                print(f"Error loading topics config: {e}")

    def extract_claims(self, doc_id: int, text: str, published_at: datetime) -> List[Claim]:
        self.load_configs()
        
        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        
        if not client:
            print("No valid LLM client found. Using rule-based fallback claim extraction.")
            return self._fallback_extract_claims(doc_id, text, published_at)

        if self.topics:
            topics_str = ", ".join(self.topics.keys())
            topic_instruction = f"The topic area (must map closely to one of: {topics_str}, or a specific sub-topic if not listed)."
            predefined_section = f"Predefined topics: {topics_str}"
        else:
            topic_instruction = "The topic area (determine this dynamically based on the subject of the claim, keeping it concise, lowercase, and hyphen-separated, e.g. 'de-dollarization', 'low-altitude-economy')."
            predefined_section = "Predefined topics: None (infer dynamically from the text)"

        system_prompt = f"""You are a Fact and Position Extraction Assistant.
Your task is to extract all source-grounded claims made by actors in the text.
A claim is a source-grounded assertion made by a specific actor (e.g. country, organization, or person representing them).

{predefined_section}

For each claim, you must extract:
1. "text": The literal assertion made by the actor.
2. "actor": The entity making the assertion.
3. "topic": {topic_instruction}
4. "stance": The actor's stance on this topic. Choose EXACTLY one from: "supportive", "cautious", "opposed", "unclear".
5. "confidence": A float from 0.0 to 1.0 estimating the strength/clarity of the evidence.

Return your response strictly as a JSON object containing a list of claims under the key "claims".
Example Output:
{{
  "claims": [
    {{
      "text": "India favors settlement of trade in local currencies.",
      "actor": "India",
      "topic": "de-dollarization",
      "stance": "supportive",
      "confidence": 0.90
    }}
  ]
}}
"""

        try:
            extra_params = {}
            if max_tokens is not None:
                extra_params["max_tokens"] = max_tokens
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract claims from the following document text:\n\n{text}"}
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                **extra_params
            )
            
            result_json = json.loads(response.choices[0].message.content)
            extracted = result_json.get("claims", [])
            
            claims = []
            for i, c in enumerate(extracted):
                claim_id = f"claim_{published_at.strftime('%Y')}_{doc_id}_{i+1}"
                claims.append(Claim(
                    id=claim_id,
                    document_id=doc_id,
                    text=c.get("text"),
                    actor=c.get("actor", "Unknown"),
                    topic=c.get("topic", "general"),
                    stance=c.get("stance", "unclear"),
                    confidence=float(c.get("confidence", 0.5)),
                    published_at=published_at
                ))
            return claims
            
        except Exception as e:
            print(f"API extraction failed: {e}. Falling back to rule-based extraction.")
            return self._fallback_extract_claims(doc_id, text, published_at)

    def _fallback_extract_claims(self, doc_id: int, text: str, published_at: datetime) -> List[Claim]:
        claims = []
        text_lower = text.lower()
        
        # Generalize fallback heuristics: we can map any of the configured topics dynamically!
        # If no topics are loaded, default to some basic ones.
        topics_mapping = {}
        for topic_name, topic_meta in self.topics.items():
            aliases = topic_meta.get("aliases", [])
            topics_mapping[topic_name] = [topic_name] + [a.lower() for a in aliases]
            
        if not topics_mapping:
            topics_mapping = {
                "general": ["general", "news", "report"]
            }

        # Check common generic actors
        actors = {
            "System": ["system", "platform"],
            "Organization": ["organization", "agency", "company", "institution"],
            "User": ["user", "actor", "agent"]
        }
        
        # Also dynamically extract capitalized entities as potential actors
        cap_words = re.findall(r"\b([A-Z][a-z]+)\b", text)
        for w in set(cap_words):
            if w not in ["The", "A", "An", "In", "On", "At", "By", "For", "With", "If", "Of", "To", "And", "Or", "But"]:
                if w not in actors:
                    actors[w] = [w.lower()]

        sentences = re.split(r'[.!?]\s+', text)
        
        claim_index = 1
        for actor, actor_keywords in actors.items():
            if any(kw in text_lower for kw in actor_keywords):
                for topic, topic_keywords in topics_mapping.items():
                    matching_kws = [kw for kw in topic_keywords if kw in text_lower]
                    if matching_kws:
                        context_sentences = [s.strip() for s in sentences if any(kw in s.lower() for kw in actor_keywords) and any(kw in s.lower() for kw in topic_keywords)]
                        
                        if context_sentences:
                            claim_text = context_sentences[0]
                        else:
                            claim_text = f"{actor} mentioned in relation to {topic}."
                        
                        stance = "supportive"
                        if any(w in claim_text.lower() for w in ["cautious", "hesitant", "concern", "wary", "not rush"]):
                            stance = "cautious"
                        elif any(w in claim_text.lower() for w in ["oppose", "reject", "against"]):
                            stance = "opposed"
                            
                        claim_id = f"claim_{published_at.strftime('%Y')}_{doc_id}_{claim_index}"
                        claims.append(Claim(
                             id=claim_id,
                             document_id=doc_id,
                             text=claim_text[:300] + "..." if len(claim_text) > 300 else claim_text,
                             actor=actor,
                             topic=topic,
                             stance=stance,
                             confidence=0.75,
                             published_at=published_at
                        ))
                        claim_index += 1
                        
        return claims
import re
