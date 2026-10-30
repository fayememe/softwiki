import os
import hashlib
from collections import Counter
import yaml
import json
from sqlalchemy import or_
from sqlalchemy.orm import Session
from datetime import datetime
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.source_store.models import Claim, CanonicalClaim, WikiArtifactState
from softwiki.knowledge.canonical import canonical_claims_for_topic
from softwiki.config import get_export_dir, get_session_id

class WikiPageGenerator:
    def __init__(self):
        self.last_model = None
        self.last_fallback = False
        self.last_intervention = ""

    def get_output_dir(self, override: str | None = None) -> str:
        if override:
            os.makedirs(override, exist_ok=True)
            return override
        if os.getenv("SOFTWIKI_MODE") in ["wiki-study", "wiki-work", "wiki-user", "study", "work", "user"]:
            session_id = get_session_id()
            path = os.path.abspath(os.path.join("output", session_id))
            os.makedirs(path, exist_ok=True)
            return path
        return get_export_dir("wiki/topics")

    def _apply_intervention(self, system_prompt: str, intervention: str) -> str:
        self.last_intervention = intervention or ""
        language_rule = (
            "OUTPUT LANGUAGE: Write the wiki page in English unless the user "
            "intervention explicitly requests another language. A Chinese-language "
            "intervention does not by itself request Chinese; it must say so explicitly."
        )
        prompt = language_rule + "\n\n" + system_prompt
        if not intervention:
            return prompt
        return (
            prompt
            + "\n\n## USER INTERVENTIONS (highest priority)\n"
            + "These are user instructions, not source evidence; they override the "
              "default structure where they conflict.\n\n"
            + intervention
        )

    def generate_topic_page(self, db: Session, topic_id: str, force_rebuild: bool = False,
                            intervention: str | None = None, output_dir: str | None = None) -> str:
        self.last_fallback = False
        self.last_model = None
        if intervention is None:
            # Canonical generation (UI Generate/Regenerate, CLI, MCP, auto-index)
            # always applies saved interventions. Preview/apply pass an explicit
            # composed string and therefore do not call this branch.
            from softwiki.wiki.interventions import compose_interventions
            intervention = compose_interventions(topic_id, include_saved=True)
        intervention_hash = hashlib.sha256((intervention or "").encode("utf-8")).hexdigest()
        # Check scope
        from softwiki.intelligence.scope_guard import check_scope
        is_in_scope, reason = check_scope(topic_id, item_type="wiki_topic")
        if not is_in_scope:
            raise ValueError(f"Reject: The topic '{topic_id}' is out of scope. Reason: {reason}")

        # 1. Fetch data from DB, including alias/pattern topics merged into this page.
        from softwiki.wiki.interventions import topic_aliases, topic_name
        aliases = topic_aliases(topic_id)
        conds = [Claim.topic == topic_id]
        for alias in aliases:
            if "*" in alias or "?" in alias:
                conds.append(Claim.topic.like(alias.replace("*", "%").replace("?", "_")))
            else:
                conds.append(Claim.topic == alias)
        claims = db.query(Claim).filter(or_(*conds)).all()
        self.last_claims_total = len(claims)
        max_claims = int(os.getenv("WIKI_MAX_CLAIMS", "250"))
        if len(claims) > max_claims:
            claims = sorted(
                claims,
                key=lambda c: ((c.confidence or 0), c.published_at or datetime.min),
                reverse=True,
            )[:max_claims]
        self.last_claims_used = len(claims)
        doc_ids = list(set(c.document_id for c in claims if c.document_id))
        docs = [DocumentRepository.get_document(db, d_id) for d_id in doc_ids if d_id]
        docs = [d for d in docs if d]
        
        # Sort docs by date
        sorted_docs = sorted(docs, key=lambda x: x.published_at or datetime.min)
        
        topic_title = topic_name(topic_id)
        
        output_filepath = os.path.join(self.get_output_dir(output_dir), f"{topic_id}.md")
        json_filepath = output_filepath.replace(".md", ".json")
        
        # 2. Check if we can use the LLM client
        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("wiki_compilation")
        self.last_model = model_name

        if not client:
            self.last_fallback = True
            print("No valid LLM client found for wiki compilation. Falling back to template-based generation.")
            return self._fallback_generate_topic_page(db, topic_id, claims, sorted_docs, topic_title, output_filepath, json_filepath)

        # 3. Read compiled state from JSON if it exists
        compiled_claim_ids = []
        compiled_doc_ids = []
        existing_markdown = ""
        is_incremental = False

        if os.path.exists(json_filepath) and os.path.exists(output_filepath) and not force_rebuild:
            try:
                with open(json_filepath, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    compiled_claim_ids = state.get("claim_ids", [])
                    compiled_doc_ids = state.get("doc_ids", [])
                    stored_intervention_hash = state.get("intervention_hash", "__missing__")
                with open(output_filepath, "r", encoding="utf-8") as f:
                    existing_markdown = f.read()
                # A changed prompt/intervention must be a full rebuild; incremental
                # merging would mix two different structures/policies.
                is_incremental = stored_intervention_hash == intervention_hash
            except Exception as e:
                print(f"Failed to read existing compiled state: {e}. Performing full rebuild.")
                is_incremental = False

        # Filter new claims and new documents
        new_claims = [c for c in claims if c.id not in compiled_claim_ids]
        new_docs = [d for d in docs if d.id not in compiled_doc_ids]
        
        # If nothing new, and files exist, return immediately
        if is_incremental and not new_claims and not new_docs:
            print(f"Wiki page for '{topic_id}' is already up-to-date.")
            return output_filepath

        # Assemble factual payload for the prompt
        claims_data = [
            {
                "id": c.id,
                "actor": c.actor,
                "stance": c.stance,
                "confidence": c.confidence,
                "claim_description": c.text,
                "source_name": next((d.source_name for d in docs if d.id == c.document_id), "Source"),
                "date": c.published_at.strftime("%Y-%m-%d") if c.published_at else "Unknown Date"
            }
            for c in claims
        ]
        
        sources_data = [
            {
                "id": d.id,
                "source_name": d.source_name,
                "title": d.title,
                "url": d.url,
                "published_at": d.published_at.strftime("%Y-%m-%d") if d.published_at else "Unknown Date"
            }
            for d in sorted_docs
        ]

        # Fetch timeline events, including merged alias topics.
        from softwiki.source_store.models import Event
        event_conds = [Event.topic == topic_id]
        for alias in aliases:
            if "*" in alias or "?" in alias:
                event_conds.append(Event.topic.like(alias.replace("*", "%").replace("?", "_")))
            else:
                event_conds.append(Event.topic == alias)
        events = db.query(Event).filter(or_(*event_conds), Event.status == "active").order_by(Event.event_date.asc()).all()
        events_data = [
            {
                "date": e.event_date.strftime("%Y-%m-%d"),
                "title": e.title,
                "description": e.description
            }
            for e in events
        ]

        extra_params = {}
        if max_tokens is not None:
            extra_params["max_tokens"] = max_tokens

        # LLM Logic
        if not is_incremental:
            print(f"Compiling first-time Wiki page for topic: '{topic_id}' using {model_name}...")
            system_prompt = """You are a Research Wiki Compiler.
Your goal is to synthesize structured evidence (Claims, Events, Relationships) into a unified, professional, human-readable Markdown Wiki Page.

You MUST follow the layout specified below:
# [Topic Title]

## Summary
[A high-level synthesis of the topic, key findings, and context.]

## Current Status
[A brief paragraph summarizing current tracking stats, document count, and overall sentiment/activity.]

## Key Actors
[A list of key actors and organizations involved.]

## Timeline
[A bulleted timeline of the key chronological events in YYYY-MM-DD format with short summaries.]

## Claims and Evidence
[A markdown table comparing claims from different actors. Table Columns: | Actor | Stance | Confidence | Claim Description | Source | Date |]

## Areas of Agreement
- [Summarize the consensus or points of agreement among the actors.]

## Areas of Disagreement
- [Summarize the disputes, cautions, and conflicting viewpoints.]

## Official Actions vs Political Rhetoric
- [Analyze differences between concrete policy declarations/actions vs media reports or rhetoric.]

## Open Questions
- [List critical unresolved issues or future questions.]

## Sources
- [A list of source documents with titles, publishers, URLs (if available), and dates.]

Rules:
1. Every paragraph and row MUST cite sources.
2. Keep the table formatted perfectly as a Markdown table.
3. Be objective, precise, and academic.
"""
            system_prompt = self._apply_intervention(system_prompt, intervention)
            user_content = f"""Topic: {topic_title}
            
Claims:
{json.dumps(claims_data, indent=2, ensure_ascii=False)}

Events/Timeline:
{json.dumps(events_data, indent=2, ensure_ascii=False)}

Sources:
{json.dumps(sources_data, indent=2, ensure_ascii=False)}

Please compile the initial Markdown Wiki Page:"""

            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=temperature,
                    **extra_params
                )
                markdown_content = response.choices[0].message.content
            except Exception as e:
                print(f"Wiki compilation LLM failed: {e}. Falling back to template generation.")
                self.last_fallback = True
                return self._fallback_generate_topic_page(
                    db, topic_id, claims, sorted_docs, topic_title, output_filepath, json_filepath
                )
        else:
            print(f"Incrementally updating Wiki page for topic: '{topic_id}' using {model_name}...")
            new_claims_data = [
                {
                    "id": c.id,
                    "actor": c.actor,
                    "stance": c.stance,
                    "confidence": c.confidence,
                    "claim_description": c.text,
                    "source_name": next((d.source_name for d in docs if d.id == c.document_id), "Source"),
                    "date": c.published_at.strftime("%Y-%m-%d") if c.published_at else "Unknown Date"
                }
                for c in new_claims
            ]
            
            system_prompt = """You are a Research Wiki Updater.
Your task is to incrementally update an existing Markdown Wiki Page with newly discovered evidence (new Claims, new Events, new Relationships).

You MUST merge the new data into the existing sections:
1. **Summary**: Incorporate new overall context if relevant.
2. **Current Status**: Update counts/stats.
3. **Key Actors**: Add any new actors.
4. **Timeline**: Add new events in correct chronological order.
5. **Claims and Evidence Table**: Append the new claims as rows in the table. Keep existing rows intact.
6. **Areas of Agreement / Disagreement**: Update if the new evidence introduces new alignment or conflict.
7. **Open Questions**: Update or resolve questions if the new evidence answers them.
8. **Sources**: Append new sources to the sources list.

Rules:
1. Preserve the existing markdown structure and layout.
2. Do NOT erase or lose existing facts, rows, or citations. Merge incrementally.
3. Output the FULL updated Markdown content.
"""
            system_prompt = self._apply_intervention(system_prompt, intervention)
            user_content = f"""Existing Wiki Page Content:
---
{existing_markdown}
---

New Claims to Integrate:
{json.dumps(new_claims_data, indent=2, ensure_ascii=False)}

New Sources to Integrate:
{json.dumps([{"source_name": d.source_name, "title": d.title, "url": d.url} for d in new_docs], indent=2, ensure_ascii=False)}

Please generate the updated full Markdown Wiki Page:"""

            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=temperature,
                    **extra_params
                )
                markdown_content = response.choices[0].message.content
            except Exception as e:
                print(f"Wiki compilation LLM failed: {e}. Falling back to template generation.")
                self.last_fallback = True
                return self._fallback_generate_topic_page(
                    db, topic_id, claims, sorted_docs, topic_title, output_filepath, json_filepath
                )

        # 4. Save results to disk
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Wiki page updated: {output_filepath}")

        # Update JSON state tracking file with full schema matching fallback for UI compatibility
        actors_list = list(set(c.actor for c in claims))
        actors_str = ", ".join(actors_list) if actors_list else "None registered"
        summary = f"This wiki page compiles intelligence on the topic: **{topic_title}**."
        if actors_list:
            summary += f" Key actors actively monitored include: {actors_str}."
        current_status = f"Currently tracking {len(claims)} active claims across {len(sorted_docs)} documents."

        agreement = "Agreement is seen in the general willingness to discuss reforms."
        disagreement = "Differences exist on implementation speeds, specific payment standards, or institutional integration."
        supportive_actors = list(set(c.actor for c in claims if c.stance == "supportive"))
        cautious_actors = list(set(c.actor for c in claims if c.stance == "cautious"))
        opposed_actors = list(set(c.actor for c in claims if c.stance == "opposed"))
        if supportive_actors:
            agreement = f"Strong alignment/support for this topic is demonstrated by: {', '.join(supportive_actors)}."
        if cautious_actors or opposed_actors:
            disagreement = ""
            if cautious_actors:
                disagreement += f"Caution or skepticism is shown by: {', '.join(cautious_actors)}."
            if opposed_actors:
                disagreement += f" Direct opposition is expressed by: {', '.join(opposed_actors)}."

        structured_data = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "summary": summary,
            "current_status": current_status,
            "key_actors": actors_list,
            "claim_ids": [c.id for c in claims],
            "doc_ids": [d.id for d in sorted_docs if d],
            "timeline": [
                {
                    "date": d.published_at.strftime("%Y-%m-%d") if d.published_at else "Unknown Date",
                    "event": f"{d.source_name} published \"{d.title}\"",
                    "source_name": d.source_name,
                    "document_title": d.title,
                    "url": d.url
                }
                for d in sorted_docs
            ],
            "claims": [
                {
                    "actor": c.actor,
                    "stance": c.stance,
                    "confidence": c.confidence,
                    "claim_description": c.text,
                    "source_name": (DocumentRepository.get_document(db, c.document_id).source_name if c.document_id and DocumentRepository.get_document(db, c.document_id) else "Source"),
                    "source_url": (DocumentRepository.get_document(db, c.document_id).url if c.document_id and DocumentRepository.get_document(db, c.document_id) else None),
                    "date": c.published_at.strftime("%Y-%m-%d") if c.published_at else "Unknown Date"
                }
                for c in claims
            ],
            "areas_of_agreement": [agreement],
            "areas_of_disagreement": [disagreement] if disagreement else [],
            "open_questions": [
                "What are the concrete next steps for integration?",
                "How will participant alignments affect the implementation timeline?"
            ],
            "sources": [
                {
                    "source_name": d.source_name,
                    "title": d.title,
                    "url": d.url,
                    "published_at": d.published_at.strftime("%Y-%m-%d") if d.published_at else None
                }
                for d in sorted_docs
            ],
            "intervention_hash": intervention_hash,
            "intervention_chars": len(intervention or ""),
            "claims_total": getattr(self, "last_claims_total", len(claims)),
            "claims_used": getattr(self, "last_claims_used", len(claims)),
            "updated_at": datetime.now().isoformat()
        }
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, indent=2, ensure_ascii=False)
        print(f"Wiki state JSON updated: {json_filepath}")
        if not output_dir:
            try:
                self._update_artifact_state(db, topic_id, claims)
            except Exception as exc:
                print(f"Wiki artifact state update failed: {exc}")

        return output_filepath

    def _update_artifact_state(self, db: Session, topic_id: str, claims: list) -> None:
        """Record claim hash/status/model so claim changes can mark this page stale."""
        canonical = canonical_claims_for_topic(db, topic_id)
        if canonical:
            ids = sorted(c.id for c in canonical)
            counts = Counter(c.status for c in canonical)
        else:
            ids = sorted(c.id for c in claims)
            counts = Counter("active" for _ in claims)
        claim_set_hash = hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()
        prompt_version = hashlib.sha256((self.last_intervention or "").encode("utf-8")).hexdigest()[:16]
        state = db.query(WikiArtifactState).filter(WikiArtifactState.topic == topic_id).first()
        if state is None:
            state = WikiArtifactState(topic=topic_id)
            db.add(state)
        state.prompt_version = prompt_version
        state.model = self.last_model
        state.claim_set_hash = claim_set_hash
        state.status_counts_json = json.dumps(dict(counts), ensure_ascii=False)
        state.built_at = datetime.utcnow()
        state.stale_at = None
        db.commit()

    def _fallback_generate_topic_page(self, db: Session, topic_id: str, claims: list, sorted_docs: list, topic_title: str, output_filepath: str, json_filepath: str) -> str:
        """Template-based fallback page generator (no external LLM key needed)."""
        claims_table_rows = []
        for c in claims:
            date_str = c.published_at.strftime("%Y-%m-%d") if c.published_at else "Unknown Date"
            doc = DocumentRepository.get_document(db, c.document_id)
            doc_ref = f"[{doc.source_name}]({doc.url})" if doc and doc.url else (doc.source_name if doc else "Source")
            claims_table_rows.append(
                f"| {c.actor} | {c.stance.title()} | {c.confidence:.2f} | {c.text} | {doc_ref} | {date_str} |"
            )
            
        claims_table = "\n".join(claims_table_rows) if claims_table_rows else "| None | - | - | - | - | - |"

        timeline_rows = []
        for d in sorted_docs:
            date_str = d.published_at.strftime("%Y-%m-%d") if d.published_at else "Unknown Date"
            timeline_rows.append(f"- **{date_str}**: {d.source_name} published \"{d.title}\"")
        timeline = "\n".join(timeline_rows) if timeline_rows else "- No events recorded."

        sources_list = []
        for d in sorted_docs:
            ref = f"- {d.source_name} - \"{d.title}\""
            if d.url:
                ref += f" [Link]({d.url})"
            if d.published_at:
                ref += f" ({d.published_at.strftime('%Y-%m-%d')})"
            sources_list.append(ref)
        sources_section = "\n".join(sources_list) if sources_list else "- No source documents listed."

        actors_list = list(set(c.actor for c in claims))
        actors_str = ", ".join(actors_list) if actors_list else "None registered"
        
        summary = f"This wiki page compiles intelligence on the topic: **{topic_title}**."
        if actors_list:
            summary += f" Key actors actively monitored include: {actors_str}."

        current_status = f"Currently tracking {len(claims)} active claims across {len(sorted_docs)} documents."

        agreement = "Agreement is seen in the general willingness to discuss reforms."
        disagreement = "Differences exist on implementation speeds, specific payment standards, or institutional integration."
        
        supportive_actors = list(set(c.actor for c in claims if c.stance == "supportive"))
        cautious_actors = list(set(c.actor for c in claims if c.stance == "cautious"))
        opposed_actors = list(set(c.actor for c in claims if c.stance == "opposed"))
        
        if supportive_actors:
            agreement = f"Strong alignment/support for this topic is demonstrated by: {', '.join(supportive_actors)}."
        if cautious_actors or opposed_actors:
            disagreement = ""
            if cautious_actors:
                disagreement += f"Caution or skepticism is shown by: {', '.join(cautious_actors)}."
            if opposed_actors:
                disagreement += f" Direct opposition is expressed by: {', '.join(opposed_actors)}."

        markdown_content = f"""# {topic_title}

## Summary
{summary}

## Current Status
{current_status}

## Key Actors
{actors_str}

## Timeline
{timeline}

## Claims and Evidence
| Actor | Stance | Confidence | Claim Description | Source | Date |
|---|---|---:|---|---|---|
{claims_table}

## Areas of Agreement
- {agreement}

## Areas of Disagreement
- {disagreement or "No explicit disagreement claims recorded."}

## Official Actions vs Political Rhetoric
- Official positions are verified through summit declarations and policy announcements.
- Speculative reporting is classified under lower confidence ratings.

## Open Questions
- What are the concrete next steps for integration?
- How will participant alignments affect the implementation timeline?

## Sources
{sources_section}
"""

        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        print(f"Generated fallback wiki page: {output_filepath}")

        # Generate structured JSON page content
        structured_data = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "summary": summary,
            "current_status": current_status,
            "key_actors": actors_list,
            "claim_ids": [c.id for c in claims],
            "doc_ids": [d.id for d in sorted_docs if d],
            "timeline": [
                {
                    "date": d.published_at.strftime("%Y-%m-%d") if d.published_at else "Unknown Date",
                    "event": f"{d.source_name} published \"{d.title}\"",
                    "source_name": d.source_name,
                    "document_title": d.title,
                    "url": d.url
                }
                for d in sorted_docs
            ],
            "claims": [
                {
                    "actor": c.actor,
                    "stance": c.stance,
                    "confidence": c.confidence,
                    "claim_description": c.text,
                    "source_name": (DocumentRepository.get_document(db, c.document_id).source_name if c.document_id and DocumentRepository.get_document(db, c.document_id) else "Source"),
                    "source_url": (DocumentRepository.get_document(db, c.document_id).url if c.document_id and DocumentRepository.get_document(db, c.document_id) else None),
                    "date": c.published_at.strftime("%Y-%m-%d") if c.published_at else "Unknown Date"
                }
                for c in claims
            ],
            "areas_of_agreement": [agreement],
            "areas_of_disagreement": [disagreement] if disagreement else [],
            "open_questions": [
                "What are the concrete next steps for integration?",
                "How will participant alignments affect the implementation timeline?"
            ],
            "sources": [
                {
                    "source_name": d.source_name,
                    "title": d.title,
                    "url": d.url,
                    "published_at": d.published_at.strftime("%Y-%m-%d") if d.published_at else None
                }
                for d in sorted_docs
            ]
        }

        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, indent=2, ensure_ascii=False)
        print(f"Generated fallback structured wiki JSON: {json_filepath}")

        return output_filepath
