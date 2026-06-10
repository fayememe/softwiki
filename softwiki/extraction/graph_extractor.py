import os
import json
import yaml
import re
from typing import List, Dict, Any
from datetime import datetime
from softwiki.source_store.models import Entity, Relationship
from softwiki.config import get_config_path

class GraphExtractor:
    def __init__(self):
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

    def extract_graph(self, doc_id: int, text: str, published_at: datetime) -> Dict[str, Any]:
        self.load_configs()
        
        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        
        if not client:
            print("No valid LLM client found. Using local fallback graph extraction.")
            return self._fallback_extract_graph(doc_id, text, published_at)

        system_prompt = """You are a Knowledge Graph Extraction Assistant.
Your task is to extract entities and their relationships from the text.

You MUST extract:
1. Entities: Important entities mentioned in the text (e.g. countries, organizations, people, major concept or project names).
   For each entity: "name", "type" (choose one of: "country", "organization", "person", "concept", "location", "project"), "description".
2. Relationships: The direct relationships between these extracted entities.
   For each relationship: "source_entity" (must match an entity name), "target_entity" (must match an entity name), "relation_type" (e.g. "member_of", "cooperates_with", "disputes_with", "controls", "depends_on", "funds", "announced"), "description", "confidence" (float 0.0 to 1.0).

Return your response strictly as a JSON object containing:
- "entities": a list of extracted entities
- "relationships": a list of extracted relationships

Example Output:
{
  "entities": [
    {"name": "AlphaCorp", "type": "organization", "description": "A global technology enterprise"},
    {"name": "BetaNation", "type": "country", "description": "A sovereign nation"}
  ],
  "relationships": [
    {"source_entity": "BetaNation", "target_entity": "AlphaCorp", "relation_type": "headquartered_in", "description": "AlphaCorp is headquartered in BetaNation.", "confidence": 0.95}
  ]
}
"""

        try:
            extra_params = {}
            if max_tokens is not None:
                extra_params["max_tokens"] = max_tokens
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract graph elements from the following text:\n\n{text}"}
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                **extra_params
            )

            result_json = json.loads(response.choices[0].message.content)
            
            entities = []
            for ent in result_json.get("entities", []):
                entities.append(Entity(
                    name=ent.get("name", "").strip(),
                    type=ent.get("type", "concept"),
                    description=ent.get("description", "")
                ))

            relationships = []
            for rel in result_json.get("relationships", []):
                relationships.append(Relationship(
                    source_name=rel.get("source_entity", "").strip(),
                    target_name=rel.get("target_entity", "").strip(),
                    relation_type=rel.get("relation_type", "associated_with"),
                    description=rel.get("description", ""),
                    document_id=doc_id,
                    confidence=float(rel.get("confidence", 0.75)),
                    published_at=published_at
                ))

            return {"entities": entities, "relationships": relationships}

        except Exception as e:
            print(f"API graph extraction failed: {e}. Falling back to local heuristics.")
            return self._fallback_extract_graph(doc_id, text, published_at)

    def _fallback_extract_graph(self, doc_id: int, text: str, published_at: datetime) -> Dict[str, Any]:
        entities = []
        relationships = []
        text_lower = text.lower()

        # Dynamically extract capitalized words as entities
        cap_words = re.findall(r"\b([A-Z][a-z]+)\b", text)
        ignored = ["The", "A", "An", "In", "On", "At", "By", "For", "With", "If", "Of", "To", "And", "Or", "But", "This", "That", "It", "They", "We", "He", "She", "You"]
        candidates = [w for w in set(cap_words) if w not in ignored]
        
        # Take up to 7 entities to avoid combinatorial explosion
        candidates = sorted(candidates)[:7]

        for name in candidates:
            entities.append(Entity(
                name=name,
                type="concept",
                description=f"Entity '{name}' extracted dynamically via fallback rules."
            ))

        # Simple relation rules: if they appear close to each other, relate them
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                src = candidates[i]
                tgt = candidates[j]
                
                relation_type = "associated_with"
                desc = f"{src} and {tgt} co-occur in the document context."
                
                if "dispute" in text_lower or "conflict" in text_lower or "oppose" in text_lower:
                    relation_type = "disputes_with"
                elif "member" in text_lower or "found" in text_lower:
                    relation_type = "member_of"

                relationships.append(Relationship(
                    source_name=src,
                    target_name=tgt,
                    relation_type=relation_type,
                    description=desc,
                    document_id=doc_id,
                    confidence=0.6,
                    published_at=published_at
                ))

        return {"entities": entities, "relationships": relationships}
