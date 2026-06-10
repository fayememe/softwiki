import os
import logging
import yaml
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from sqlalchemy import or_
from softwiki.rag.hybrid_search import HybridSearcher
from softwiki.rag.citations import CitationManager
from softwiki.config import get_config_path, is_module_enabled, get_export_dir, get_session_id
from softwiki.source_store.models import Claim, Entity, Relationship, Event

logger = logging.getLogger(__name__)

_lightrag_warned = False

def _try_lightrag_query(question: str, mode: str = "local") -> Optional[List[str]]:
    """Try querying LightRAG for graph context. Returns None if unavailable."""
    global _lightrag_warned
    try:
        from softwiki.graph_rag.adapter import has_lightrag_credentials
        if not has_lightrag_credentials():
            return None
    except ImportError:
        return None
    try:
        from softwiki.graph_rag.adapter import LightRAGAdapter
        adapter = LightRAGAdapter.get_instance()
        context = adapter.sync_query_context(question, mode=mode, top_k=20)
        if context and context.strip():
            lines = context.strip().split("\n")
            return [f"(LightRAG) {line}" for line in lines if line.strip()]
    except Exception as e:
        logger.debug(f"LightRAG query failed (non-critical): {e}")
    return None

class AnswerEngine:
    def __init__(self):
        self.searcher = HybridSearcher()

    def load_configs(self):
        pass

    def ask(self, db: Session, question: str) -> str:
        self.load_configs()
        
        # 1. RAG Retrieve
        search_results = []
        context_str = ""
        citation_manager = CitationManager()
        if is_module_enabled("rag"):
            search_results = self.searcher.search(db, question, top_k=5)
            if search_results:
                context_parts = []
                for res in search_results:
                    chunk = res["chunk"]
                    doc = res["document"]
                    doc_meta = {
                        "title": doc.title,
                        "url": doc.url,
                        "source_name": doc.source_name,
                        "published_at": doc.published_at
                    }
                    cit_num = citation_manager.get_citation_num(doc.id, doc_meta)
                    entry = f"--- Source [{cit_num}] ({doc.source_name} - {doc.source_type or 'Unknown'}) ---\n{chunk.text}"
                    context_parts.append(entry)
                context_str = "\n\n".join(context_parts)

        # 2. Claim DB Retrieve
        claims_context = []
        if is_module_enabled("claimdb"):
            words = [w for w in question.lower().split() if len(w) > 3]
            query = db.query(Claim)
            if words:
                filters = [Claim.text.like(f"%{w}%") for w in words]
                query = query.filter(or_(*filters))
            claims = query.limit(10).all()
            for c in claims:
                date_str = c.published_at.strftime('%Y-%m-%d') if c.published_at else 'unknown'
                claims_context.append(f"- Actor: {c.actor} | Stance: {c.stance} | Claim: {c.text} (Date: {date_str}, Conf: {c.confidence:.2f})")

        # 3. Graph Retrieve — try LightRAG first, fallback to SQL LIKE
        graph_context = []
        if is_module_enabled("graph"):
            lr_context = _try_lightrag_query(question, mode="local")
            if lr_context:
                graph_context = lr_context
            else:
                # Fallback: SQL LIKE on existing Entity/Relationship tables
                words = [w for w in question.lower().split() if len(w) > 3]
                query = db.query(Relationship)
                if words:
                    filters = [Relationship.description.like(f"%{w}%") | Relationship.source_name.like(f"%{w}%") | Relationship.target_name.like(f"%{w}%") for w in words]
                    query = query.filter(or_(*filters))
                rels = query.limit(10).all()
                for r in rels:
                    graph_context.append(f"- Relationship: {r.source_name} --({r.relation_type})--> {r.target_name} ({r.description or ''})")

        # 4. Timeline Retrieve
        timeline_context = []
        if is_module_enabled("timeline"):
            words = [w for w in question.lower().split() if len(w) > 3]
            query = db.query(Event)
            if words:
                filters = [Event.title.like(f"%{w}%") | Event.description.like(f"%{w}%") for w in words]
                query = query.filter(or_(*filters))
            events = query.order_by(Event.event_date.asc()).limit(10).all()
            for ev in events:
                date_str = ev.event_date.strftime("%Y-%m-%d")
                timeline_context.append(f"- Event [{date_str}]: {ev.title} - {ev.description or ''}")

        # 5. LLM Wiki Retrieve
        wiki_context = []
        if is_module_enabled("llmwiki"):
            wiki_dir = get_export_dir("wiki/topics")
            if os.path.exists(wiki_dir):
                for filename in os.listdir(wiki_dir):
                    if filename.endswith(".md"):
                        topic_name = filename[:-3]
                        if topic_name.lower().replace("-", " ") in question.lower():
                            try:
                                with open(os.path.join(wiki_dir, filename), "r", encoding="utf-8") as f:
                                    wiki_context.append(f"--- Compiled Wiki Page: {topic_name} ---\n{f.read()[:800]}...\n")
                            except Exception:
                                pass

        # Compile consolidated context blocks
        prompt_parts = []
        if context_str:
            prompt_parts.append(f"### Relevant Text Excerpts (RAG):\n{context_str}")
        if claims_context:
            prompt_parts.append("### Extracted Claims (ClaimDB):\n" + "\n".join(claims_context))
        if graph_context:
            prompt_parts.append("### Knowledge Graph Relationships (Graph):\n" + "\n".join(graph_context))
        if timeline_context:
            prompt_parts.append("### Chronological Events (Timeline):\n" + "\n".join(timeline_context))
        if wiki_context:
            prompt_parts.append("### Existing Topic Synthesis (llm-wiki):\n" + "\n\n".join(wiki_context))

        consolidated_context = "\n\n".join(prompt_parts)

        if not consolidated_context.strip():
            answer = "No relevant sources found in active modules to answer this question. Please ingest and index some documents."
            self._save_user_mode_output(question, answer, [])
            return answer

        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("high_quality_analysis")
        
        if not client:
            print("No valid LLM client found. Generating answer using local fallback mode.")
            answer = self._generate_fallback_answer_modular(question, search_results, claims_context, graph_context, timeline_context, wiki_context, citation_manager)
        else:
            system_prompt = """You are a senior analyst and research assistant.
Your goal is to provide a source-grounded, fact-based response to the user's question using the provided context from various knowledge layers.

You MUST follow these rules:
1. Every factual statement or claim MUST be backed by a source and include appropriate references (e.g. inline citation like [1], [2] for RAG sources, or specific claim/graph/timeline attributes).
2. Avoid unsupported conclusions. If the sources do not provide information, explicitly state that.
3. Distinguish between official positions, news reporting, and analysis/speculation.
4. Provide a "Confidence Level" assessment at the end (High, Medium, Low) and explain why (e.g. weak evidence, conflicting statements).

Structure your response as follows:
## Direct Answer
[Short, direct answer to the question]

## Detailed Evidence Summary
[Nuanced synthesis of the provided context, citing sources inline]

## Official Positions vs. Rhetoric & Speculation
[Brief analysis comparing official actions or statements with news reporting or speculation if applicable]

## Confidence Assessment
[Confidence: High/Medium/Low. Explain your rating based on the source quality, agreement/contradiction, and timeline.]
"""

            user_content = f"""User Question: {question}

Provided Context from Knowledge Layers:
{consolidated_context}

Please generate the structured response:"""

            try:
                extra_params = {}
                if max_tokens is not None:
                    extra_params["max_tokens"] = max_tokens
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=temperature,
                    **extra_params
                )
                
                answer = response.choices[0].message.content
                if is_module_enabled("rag") and search_results:
                    answer += "\n" + citation_manager.render_citations()
                
            except Exception as e:
                print(f"API answer generation failed: {e}. Using local modular fallback.")
                answer = self._generate_fallback_answer_modular(question, search_results, claims_context, graph_context, timeline_context, wiki_context, citation_manager)

        self._save_user_mode_output(question, answer, search_results)
        return answer

    def _generate_fallback_answer_modular(self, question: str, search_results: list, claims: list, graph: list, timeline: list, wiki: list, citation_manager: CitationManager) -> str:
        output = []
        output.append("## Direct Answer (Local Modular Retrieval Mode)")
        output.append(f"Synthesized matching local knowledge segments for query: \"{question}\"\n")
        
        output.append("## Detailed Evidence Summary")
        
        if is_module_enabled("rag") and search_results:
            output.append("### RAG Text Segments:")
            for res in search_results:
                chunk = res["chunk"]
                doc = res["document"]
                doc_meta = {
                    "title": doc.title,
                    "url": doc.url,
                    "source_name": doc.source_name,
                    "published_at": doc.published_at
                }
                cit_num = citation_manager.get_citation_num(doc.id, doc_meta)
                snippet = chunk.text.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                output.append(f"- From **{doc.source_name}** ({doc.source_type or 'news'}): \"{snippet}\" [{cit_num}]")
        
        if claims:
            output.append("\n### Claims DB Entries:")
            for c in claims[:5]:
                output.append(c)
                
        if graph:
            output.append("\n### Graph Relationships:")
            for r in graph[:5]:
                output.append(r)
                
        if timeline:
            output.append("\n### Timeline Events:")
            for ev in timeline[:5]:
                output.append(ev)

        if wiki:
            output.append("\n### Wiki Overview:")
            for wk in wiki[:2]:
                output.append(wk[:300] + "...\n")
            
        output.append("\n## Official Positions vs. Rhetoric & Speculation")
        output.append("*(Offline mode: Advanced thematic analysis is limited. Please configure a valid `OPENAI_API_KEY`.)*")
        
        output.append("\n## Confidence Assessment")
        output.append("**Confidence**: Medium (Rule-based lexical retrieval completed. Semantic synthesis is offline.)")
        
        if is_module_enabled("rag") and search_results:
            output.append(citation_manager.render_citations())
            
        return "\n".join(output)

    def _slugify(self, text: str) -> str:
        import re
        text = text.lower().strip()
        # Keep alphanumeric, spaces, hyphens, underscores and CJK characters
        # Replaces any other character with underscore
        text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3-]', '_', text)
        # Replace spaces/underscores/hyphens with a single underscore
        text = re.sub(r'[\s_-]+', '_', text)
        text = text.strip('_')
        slug = text[:50]
        return slug if slug else "query"

    def _get_output_dir(self) -> str:
        session_id = get_session_id()
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.abspath(os.path.join(project_root, "output", session_id))
        os.makedirs(path, exist_ok=True)
        return path

    def _save_user_mode_output(self, question: str, answer: str, search_results: list):
        current_mode = os.getenv("SOFTWIKI_MODE")
        if current_mode not in ["work", "user", "wiki-work", "wiki-user"]:
            return
        
        import json
        from datetime import datetime
        
        session_id = get_session_id()
        out_dir = self._get_output_dir()
        slug = self._slugify(question)
        
        md_filename = f"ask_{slug}.md"
        json_filename = f"ask_{slug}.json"
        
        md_filepath = os.path.join(out_dir, md_filename)
        json_filepath = os.path.join(out_dir, json_filename)
        
        now = datetime.now().isoformat()
        md_content = f"# Research Query: {question}\n\n- **Date**: {now}\n- **Mode**: {current_mode.title()} Mode\n- **Session ID**: {session_id}\n\n---\n\n{answer}\n"
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Generated Q&A document: {md_filepath}")
            
        sources = []
        for res in search_results:
            chunk = res["chunk"]
            doc = res["document"]
            sources.append({
                "document_id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "source_name": doc.source_name,
                "source_type": doc.source_type,
                "published_at": doc.published_at.strftime('%Y-%m-%d') if doc.published_at else None,
                "trust_level": doc.trust_level,
                "text_snippet": chunk.text,
                "score": float(res["score"])
            })
            
        json_data = {
            "question": question,
            "session_id": session_id,
            "timestamp": now,
            "answer": answer,
            "sources": sources
        }
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        print(f"Generated Q&A JSON: {json_filepath}")
