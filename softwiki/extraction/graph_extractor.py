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
        
        from softwiki.intelligence.llm_client import create_chat_completion, get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        
        if not client:
            print("No valid LLM client found. Using local fallback graph extraction.")
            return self._fallback_extract_graph(doc_id, text, published_at)

        system_prompt = """You are a Knowledge Graph Extraction Assistant for ARM architecture documentation.

Extract a precise entity/relationship graph. Only what the text supports; never invent.

Entities — for each: "name", "type", "description", "aliases".
- "type" must be one of: "product", "ip_block", "architecture", "protocol", "instruction_set",
  "feature", "register", "component", "standard", "organization", "concept", "other".
- "name": the canonical name as used in the document, keeping model numbers
  (e.g. "Cortex-M55", "AMBA AXI5", "PL031", "Ethos-U55", "GIC-600").
- "aliases": other spellings that clearly denote the same thing
  (e.g. ["M55", "Cortex M55"] for "Cortex-M55"; [] if none).
- Skip generic words ("this", "the processor", "data"), stopwords and section titles.

Relationships — for each: "source_entity", "target_entity", "relation_type",
"description", "confidence", "evidence".
- Both endpoints MUST be entity names from your "entities" list.
- "relation_type" must be a short snake_case verb, preferred vocabulary:
  implements, part_of, variant_of, supports, requires, extends, compatible_with,
  includes, used_by, configured_by, has_feature, documented_in, licensed_by,
  precedes, replaces.
- "confidence": float 0.0–1.0 reflecting how explicit the text is.
- "evidence": the shortest quoted phrase (<=200 chars) that supports it.
- Do not repeat the same (source, target, relation_type) twice; merge duplicates
  and keep the strongest evidence.

Return strictly a JSON object:
{"entities": [...], "relationships": [...]}

Example:
{
  "entities": [
    {"name": "Cortex-M55", "type": "product", "description": "Armv8.1-M processor", "aliases": ["M55"]},
    {"name": "Helium", "type": "feature", "description": "M-profile vector extension", "aliases": ["MVE"]}
  ],
  "relationships": [
    {"source_entity": "Cortex-M55", "target_entity": "Helium", "relation_type": "supports",
     "description": "Cortex-M55 implements the Helium vector extension.", "confidence": 0.95,
     "evidence": "Cortex-M55 supports Helium technology"}
  ]
}
"""

        try:
            extra_params = {}
            if max_tokens is not None:
                extra_params["max_tokens"] = max_tokens
            response = create_chat_completion(
                client,
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

            from softwiki.graph.resolution import clean_aliases, normalize_entity_name

            entities = []
            entity_names: set[str] = set()
            for ent in result_json.get("entities", []):
                name = (ent.get("name") or "").strip()
                if not name:
                    continue
                entity_names.add(name.lower())
                aliases = clean_aliases(name, ent.get("aliases") or [])
                entities.append(Entity(
                    name=name,
                    type=ent.get("type", "concept"),
                    description=ent.get("description", ""),
                    normalized_name=normalize_entity_name(name),
                    aliases=json.dumps(aliases, ensure_ascii=False) if aliases else None,
                ))

            relationships = []
            seen_edges: set[tuple[str, str, str]] = set()
            for rel in result_json.get("relationships", []):
                source = (rel.get("source_entity") or "").strip()
                target = (rel.get("target_entity") or "").strip()
                rtype = (rel.get("relation_type") or "associated_with").strip().lower()
                if not source or not target:
                    continue
                # Endpoints must be entities we actually extracted.
                if entity_names and source.lower() not in entity_names:
                    continue
                if entity_names and target.lower() not in entity_names:
                    continue
                key = (source.lower(), target.lower(), rtype)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                try:
                    confidence = float(rel.get("confidence", 0.75))
                except (TypeError, ValueError):
                    confidence = 0.75
                relationships.append(Relationship(
                    source_name=source,
                    target_name=target,
                    relation_type=rtype[:100],
                    description=(rel.get("description") or rel.get("evidence") or "").strip(),
                    document_id=doc_id,
                    confidence=max(0.0, min(1.0, confidence)),
                    published_at=published_at,
                ))

            return {"entities": entities, "relationships": relationships}

        except Exception as e:
            if os.getenv("GRAPH_ALLOW_HEURISTIC_FALLBACK", "").lower() in ("1", "true", "yes"):
                print(f"API graph extraction failed: {e}. Falling back to local heuristics.")
                return self._fallback_extract_graph(doc_id, text, published_at)
            # A heuristic graph is noise: capitalized words with made-up
            # relations. Better to leave this window without graph data and let
            # the retry/normalization pass report it than to poison the graph.
            print(f"API graph extraction failed for doc {doc_id}: {e}. Skipping graph for this window.")
            return {"entities": [], "relationships": []}

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
