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

# ── Answer modes ──

ANSWER_MODES = {
    "normal": {
        "label": "Normal",
        "temperature": 0.7,
        "top_k": 5,
        "system_prompt": """You are a friendly, knowledgeable research assistant. Answer the user's question naturally using the provided context.

Guidelines:
- Use a conversational tone — like explaining to a curious friend
- Match the user's language (Korean, English, Chinese, Japanese, etc.)
- Cite sources naturally with inline references like [1], [2]
- If you don't have relevant information, just say so honestly
- Don't fabricate information or force a structure
- Be concise but thorough — no fluff, no filler""",
    },
    "deep": {
        "label": "Deep Think",
        "temperature": 0.5,
        "top_k": 10,
        "system_prompt": """You are a thorough research analyst. Provide a comprehensive, well-reasoned answer.

Guidelines:
- Think step by step before answering
- Cite every factual claim with inline references [1], [2], [3]
- Present multiple perspectives when the sources disagree
- Include relevant quotes from sources
- Note gaps or uncertainties in the available information
- Structure your answer with clear logical flow
- Match the user's language""",
    },
    "concise": {
        "label": "Concise",
        "temperature": 0.3,
        "top_k": 3,
        "system_prompt": """You are a direct answer assistant. Give the shortest possible correct answer.

Guidelines:
- Answer in 1-3 sentences when possible
- Include only essential citations
- No elaboration unless the question asks for it
- If the answer is yes/no, start with yes or no
- Match the user's language""",
    },
    "creative": {
        "label": "Creative",
        "temperature": 0.9,
        "top_k": 8,
        "system_prompt": """You are a creative analyst with a talent for connecting ideas.

Guidelines:
- Draw unexpected connections across different sources
- Offer hypotheses and speculative analysis (clearly labeled as such)
- Use analogies and metaphors to explain complex topics
- Cite sources where possible, but feel free to synthesize beyond them
- Make the answer engaging and thought-provoking
- Match the user's language""",
    },
}

# ── Query type classification ──

_CASUAL_PATTERNS = [
    "hi", "hello", "hey", "howdy", "greetings", "good morning", "good afternoon",
    "good evening", "what's up", "sup", "yo",
    "how are you", "how are things", "how's it going", "how do you do",
    "nice to meet", "pleasure",
    "thanks", "thank you", "thx", "ty", "appreciate it", "goodbye", "bye",
    "see you", "later", "cya", "have a good",
    "你好", "您好", "早上好", "下午好", "晚上好", "你好吗", "最近怎么样",
    "谢谢", "感谢", "再见", "拜拜", "明天见",
    "天气", "今天天气", "你叫什么", "你会什么",
]

_ADMIN_PATTERNS = [
    "what's in", "what is in", "show me", "list", "how many", "count", "summary",
    "knowledge base", "knowledgebase", "my data", "all documents", "all claims",
    "知识库", "有什么", "多少", "统计", "列表", "数据",
    "工作区", "workspace", "workspaces",
    "documents", "claims", "entities", "relationships", "events",
    "status", "database", "storage",
]

# Phrases that mean "search the web for this"



def _detect_language(text: str) -> str:
    """Quick language detection based on character ranges."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    korean = sum(1 for c in text if '\uac00' <= c <= '\ud7a3' or '\u3130' <= c <= '\u318f')
    if cjk > len(text) * 0.3:
        return "zh"
    if korean > len(text) * 0.3:
        return "ko"
    return "en"


def _classify_question(question: str) -> str:
    """Returns 'casual', 'admin', or 'knowledge'."""
    q = question.lower().strip()
    for p in _CASUAL_PATTERNS:
        if q == p or q.startswith(p + " ") or q.startswith(p + ",") or q.startswith(p + "!"):
            return "casual"
    for p in _ADMIN_PATTERNS:
        if p in q:
            return "admin"
    return "knowledge"


_CASUAL_RESPONSES = {
    "en": {
        ("hi", "hello", "hey", "howdy"): [
            "Hi there! How can I help you today?",
            "Hello! What can I do for you?",
            "Hey! Feel free to ask me anything about your knowledge base.",
        ],
        ("how are you", "how are things", "how's it going"): [
            "I'm doing well, thanks! Ready to help you explore your knowledge base.",
            "All good here! How can I assist you today?",
            "Doing great! What would you like to know?",
        ],
        ("thanks", "thank you", "thx", "ty"): [
            "You're welcome! Happy to help.",
            "No problem! Let me know if you need anything else.",
            "Anytime!",
        ],
        ("good morning",): ["Good morning! Hope you're having a great start to your day."],
        ("good afternoon",): ["Good afternoon! What can I help you with?"],
        ("good evening",): ["Good evening! How can I assist you?"],
        ("bye", "goodbye", "see you", "later"): [
            "Goodbye! Feel free to come back anytime.",
            "See you later! Take care.",
        ],
    },
}


def _try_web_search(query: str, top_k: int = 5) -> Optional[List[str]]:
    from softwiki.search.web import search_web
    return search_web(query, top_k)

def _casual_response(question: str) -> str:
    """Generate a natural response for casual chat."""
    lang = _detect_language(question)
    q = question.lower().strip()

    if lang == "zh":
        # Simple Chinese greetings
        if any(q.startswith(g) for g in ["你好", "您好", "早上好", "下午好", "晚上好"]):
            return "你好！有什么我可以帮你的吗？"
        if "谢谢" in q or "感谢" in q:
            return "不客气！有什么需要随时问我。"
        if "再见" in q or "拜拜" in q:
            return "再见！随时欢迎回来。"
        if "天气" in q:
            return "我暂时还不能查天气哦，不过我可以帮你查知识库里的内容！"
        if "你叫什么" in q:
            return "我是 SoftWiki，你的个人知识库助手！"
        if "你会什么" in q:
            return "我可以帮你查询知识库、管理文档、生成 Wiki 页面等等！"
        return "你好！有什么我可以帮你的吗？"

    if lang == "ko":
        if any(q.startswith(g) for g in ["안녕", "안녕하세요"]):
            return "안녕하세요! 무엇을 도와드릴까요?"
        if "고마" in q or "감사" in q:
            return "천만에요! 또 필요하시면 말씀해 주세요."
        if "날씨" in q:
            return "죄송합니다, 날씨 정보는 아직 지원하지 않아요. 대신 지식 베이스 내용을 검색해 드릴게요!"
        return "안녕하세요! 무엇을 도와드릴까요?"

    # English
    en_responses = _CASUAL_RESPONSES["en"]
    for patterns, replies in en_responses.items():
        if any(q.startswith(p) or q == p for p in patterns):
            import random
            return random.choice(replies)

    return "Hi there! How can I help you today?"


def _admin_answer(db: Session, question: str) -> str:
    """Answer admin/inventory questions about the knowledge base."""
    from softwiki.source_store.models import Document, Claim, Chunk, Entity, Relationship, Event
    from softwiki.config import get_workspace_dir, list_workspaces

    lang = _detect_language(question)

    doc_count = db.query(Document).count()
    chunk_count = db.query(Chunk).count()
    claim_count = db.query(Claim).count()
    entity_count = db.query(Entity).count()
    rel_count = db.query(Relationship).count()
    event_count = db.query(Event).count()
    ws = get_workspace_dir()
    ws_name = os.path.basename(ws)

    if "workspace" in question.lower() or "工作区" in question:
        workspaces = list_workspaces()
        ws_list = "\n".join(f"  - {w}" for w in workspaces)
        if lang == "zh":
            return (
                f"当前工作区: **{ws_name}**\n\n"
                f"可用工作区:\n{ws_list}\n\n"
                f"在工作区 `{ws_name}` 内:\n"
                f"- 文档: {doc_count}\n- 文本片段: {chunk_count}\n- 声明(Claims): {claim_count}\n"
                f"- 实体: {entity_count}\n- 关系: {rel_count}\n- 事件: {event_count}"
            )
        return (
            f"Current workspace: **{ws_name}**\n\n"
            f"Available workspaces:\n{ws_list}\n\n"
            f"In `{ws_name}`:\n"
            f"- Documents: {doc_count}\n- Chunks: {chunk_count}\n- Claims: {claim_count}\n"
            f"- Entities: {entity_count}\n- Relationships: {rel_count}\n- Events: {event_count}"
        )

    # General "what's in my knowledge base" type queries
    if lang == "zh":
        lines = [f"当前工作区 **{ws_name}** 包含以下数据:\n"]
        if doc_count > 0:
            lines.append(f"📄 **文档**: {doc_count} 篇")
        if chunk_count > 0:
            lines.append(f"🧩 **文本片段**: {chunk_count} 条")
        if claim_count > 0:
            lines.append(f"📋 **声明(Claims)**: {claim_count} 条")
        if entity_count > 0:
            lines.append(f"🏷️ **实体**: {entity_count} 个")
        if rel_count > 0:
            lines.append(f"🔗 **关系**: {rel_count} 条")
        if event_count > 0:
            lines.append(f"📅 **事件**: {event_count} 个")
        if doc_count == 0 and claim_count == 0 and entity_count == 0:
            lines.append("\n还没有数据，先导入一些文档吧！")
        return "\n".join(lines)

    lines = [f"Workspace **{ws_name}** contains:\n"]
    if doc_count > 0:
        lines.append(f"📄 **Documents**: {doc_count}")
    if chunk_count > 0:
        lines.append(f"🧩 **Chunks**: {chunk_count}")
    if claim_count > 0:
        lines.append(f"📋 **Claims**: {claim_count}")
    if entity_count > 0:
        lines.append(f"🏷️ **Entities**: {entity_count}")
    if rel_count > 0:
        lines.append(f"🔗 **Relationships**: {rel_count}")
    if event_count > 0:
        lines.append(f"📅 **Events**: {event_count}")
    if doc_count == 0 and claim_count == 0 and entity_count == 0:
        lines.append("\nNothing yet — try ingesting some documents first!")
    return "\n".join(lines)

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

    def ask(self, db: Session, question: str, history: Optional[List[Dict[str, str]]] = None, mode: str = "normal") -> str:
        self.load_configs()

        qtype = _classify_question(question)

        if qtype == "casual":
            answer = _casual_response(question)
            self._save_user_mode_output(question, answer, [])
            return answer
        if qtype == "admin":
            answer = _admin_answer(db, question)
            self._save_user_mode_output(question, answer, [])
            return answer

        mode_config = ANSWER_MODES.get(mode, ANSWER_MODES["normal"])

        # If there's conversation history, use the original topic from history
        # as the RAG search query — current message is almost always a follow-up.
        search_query = question
        if history:
            for h in reversed(history):
                if h["role"] == "user":
                    search_query = h["content"]
                    break

        # 1. RAG Retrieve
        search_results = []
        context_str = ""
        citation_manager = CitationManager()
        if is_module_enabled("rag"):
            search_results = self.searcher.search(db, search_query, top_k=mode_config["top_k"])
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

        # Web search — always supplement when enabled
        should_search = os.getenv("SOFTWIKI_ENABLE_WEB_SEARCH", "").lower() in ("1", "true", "yes")
        web_results = None
        if should_search:
            web_results = _try_web_search(search_query)
            if web_results:
                web_context = "### Live Web Search Results (retrieved just now):\n" + "\n\n".join(web_results)
                consolidated_context = (consolidated_context + "\n\n" + web_context) if consolidated_context.strip() else web_context

        if not consolidated_context.strip():
            answer = "I don't have information about that yet. Try adding some documents first and I'll be able to help!"
            self._save_user_mode_output(question, answer, [])
            return answer

        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("high_quality_analysis")
        
        if not client:
            print("No valid LLM client found. Generating answer using local fallback mode.")
            answer = self._generate_fallback_answer_modular(question, search_results, claims_context, graph_context, timeline_context, wiki_context, citation_manager)
        else:
            system_prompt = mode_config["system_prompt"]

            user_content = f"""Question: {question}

Context:
{consolidated_context}"""

            try:
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    for h in history[-20:]:  # last 20 exchanges max
                        messages.append({"role": h["role"], "content": h["content"]})
                messages.append({"role": "user", "content": user_content})

                extra_params = {}
                if max_tokens is not None:
                    extra_params["max_tokens"] = max_tokens
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=mode_config["temperature"],
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
        
        if is_module_enabled("rag") and search_results:
            output.append("Here's what I found from the sources:\n")
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
                if len(snippet) > 300:
                    snippet = snippet[:300] + "..."
                output.append(f"- [{cit_num}] {doc.source_name}: {snippet}")
        
        if claims:
            output.append("\nRelevant claims from database:")
            for c in claims[:5]:
                output.append(f"  • {c}")
                
        if graph:
            output.append("\nFound in knowledge graph:")
            for r in graph[:5]:
                output.append(f"  • {r}")
                
        if timeline:
            output.append("\nRelated timeline events:")
            for ev in timeline[:5]:
                output.append(f"  • {ev}")

        if wiki:
            output.append("\nRelated wiki topics:")
            for wk in wiki[:2]:
                output.append(f"  • {wk[:300]}...\n")
        
        if not any([search_results, claims, graph, timeline, wiki]):
            output.append("I don't have information about that yet. Try adding some documents first.")
        elif not (is_module_enabled("rag") and search_results):
            output.append("\n\n(Note: LLM is not connected — showing local search results. Set up an API key for more natural answers.)")
            
        if is_module_enabled("rag") and search_results:
            output.append("\n\n---\n" + citation_manager.render_citations())
            
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
