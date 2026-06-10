# General Research Intelligence System: Multi-Layer Knowledge Architecture

## 1. Purpose

This document defines a general-purpose knowledge architecture for a research intelligence system.

The system should combine:

* Source-grounded RAG
* GraphRAG / entity-relationship graph
* Claim and stance tracking
* Timeline analysis
* llm-wiki / generated knowledge pages (inspired by Andrej Karpathy's `llm-wiki.md` design pattern for compiling stateless RAG queries into a stateful, evolving, and interlinked local Markdown knowledge base)
* Reports and briefs

The key design question is how RAG, GraphRAG, and llm-wiki should relate to each other.

The answer is:

```text
They are not a simple serial pipeline.

They are three derived knowledge views over the same canonical source store.
```

The canonical source of truth is always the raw source material plus source metadata.

---

## 2. Core Principle

The system should follow this principle:

```text
Raw Sources / Source Store = canonical evidence

RAG = evidence retrieval view

Graph / Claim DB = relationship and structured reasoning view

Timeline = temporal change view

llm-wiki = human-readable synthesis and navigation view
```

The wiki is not the ground truth.

The graph is not the ground truth.

RAG search results are not ground truth by themselves either.

Only the original source documents, with metadata and citations, are the canonical evidence base.

---

## 3. Incorrect Mental Model

Do not implement this system as a simple serial chain:

```text
Raw Sources
  ↓
RAG
  ↓
GraphRAG
  ↓
llm-wiki
```

This model is wrong because:

1. If the graph is produced only from RAG answers, it will inherit RAG retrieval errors.
2. If the wiki is produced only from graph summaries, it may lose source details.
3. If answers rely only on wiki pages, they will become stale and incomplete.
4. If graph relations are not source-verified, the system may hallucinate relationships.
5. If wiki pages try to summarize all raw data, they will collapse under scale.

---

## 4. Correct Mental Model

Use this model instead:

```text
                    ┌──────────────────┐
                    │   Raw Sources     │
                    │ Docs / Web / PDFs │
                    │ APIs / Notes      │
                    └─────────┬────────┘
                              ↓
                    ┌──────────────────┐
                    │   Source Store    │
                    │ canonical evidence│
                    └─────────┬────────┘
                              ↓
       ┌──────────────────────┼──────────────────────┐
       ↓                      ↓                      ↓
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  RAG Index   │       │ Extraction   │       │ Metadata DB  │
│ evidence     │       │ entities     │       │ sources      │
│ retrieval    │       │ claims       │       │ dates        │
└──────┬───────┘       │ events       │       │ trust levels │
       │               └──────┬───────┘       └──────────────┘
       │                      ↓
       │               ┌──────────────┐
       │               │ Graph Store  │
       │               │ relations    │
       │               │ claims       │
       │               │ timelines    │
       │               └──────┬───────┘
       │                      │
       └──────────────┬───────┘
                      ↓
              ┌──────────────┐
              │ Intelligence │
              │ Router / QA  │
              └──────┬───────┘
                     ↓
              ┌──────────────┐
              │ Wiki/Reports │
              │ synthesis    │
              └──────────────┘
```

In this design:

```text
RAG, Graph, Timeline, and Wiki are derived from Source Store.

They are not replacements for Source Store.

They are complementary views.
```

---

## 5. Layer Responsibilities

### 5.1 Source Store

The Source Store is the canonical evidence base.

It stores:

```text
documents
raw text
cleaned text
source metadata
publication date
collection date
source type
source location
language
author
trust level
hash
URL or file path
citation information
```

Every derived object should point back to one or more source documents.

Examples:

```text
A claim must point to a source document.
A graph relationship should point to a source document or extracted claim.
A wiki statement should point to source-backed claims or documents.
A report conclusion should be traceable to sources.
```

---

### 5.2 RAG Layer

The RAG layer is the evidence retrieval layer.

It is responsible for:

```text
document-aware chunking
BM25 full-text search
vector search
hybrid retrieval
reranking
citation generation
source lookup
latest evidence retrieval
```

RAG should be used when the system needs:

```text
exact source evidence
original wording
latest documents
citation-backed answers
verification of graph or wiki claims
```

RAG should not be treated as a final reasoning layer by itself.

It retrieves evidence. It does not define the system's long-term understanding.

---

### 5.3 Graph / GraphRAG Layer

The Graph layer is the structured relationship layer.

It stores:

```text
entities
documents
sources
claims
events
topics
concepts
people
organizations
projects
products
locations
relationships
dependencies
causal links
references
```

It is responsible for:

```text
entity linking
relationship traversal
multi-hop reasoning
claim-source linkage
topic mapping
dependency mapping
concept relationship analysis
```

The graph should be built from source documents, extracted claims, and extracted relationships.

The graph should not be built only from RAG-generated answers.

GraphRAG should be used when the system needs:

```text
relationship reasoning
multi-hop analysis
dependency analysis
entity comparison
topic network analysis
institutional or organizational relationship analysis
causal or influence-chain analysis
```

Graph relations should be source-grounded.

The system should never answer from the graph alone unless the graph relationship has source evidence.

---

### 5.4 Claim DB

The Claim DB is a structured layer for source-grounded assertions.

A claim is not just a summary.

A claim is a specific source-backed assertion made by an actor, source, or document.

Example:

```json
{
  "claim_id": "claim_00123",
  "text": "Product A supports feature X only when configuration Y is enabled.",
  "actor": "Document or source author",
  "topic": "feature X",
  "stance": "supportive",
  "source_id": "doc_abc",
  "source_type": "manual",
  "published_at": "2026-01-15",
  "confidence": 0.82
}
```

Claim DB is useful because real knowledge is often nuanced, conflicting, or time-dependent.

Examples:

```text
A product may support a feature only under certain conditions.
A policy may be proposed but not implemented.
A company may announce a roadmap but not deliver it yet.
A project may have conflicting documentation.
A technical decision may change over time.
```

These should not be flattened into simple yes/no statements.

---

### 5.5 Timeline Layer

The Timeline layer stores temporal change.

It tracks:

```text
events
announcements
policy changes
version changes
project milestones
publications
decisions
incidents
release notes
status changes
claim changes
```

The timeline is used for:

```text
trend analysis
before/after comparison
position evolution
project history
event chronology
version-aware answers
staleness detection
```

Trend questions should use Timeline + Graph + RAG, not wiki alone.

---

### 5.6 llm-wiki Layer

The llm-wiki layer is the human-readable synthesis layer.

It stores:

```text
topic pages
entity pages
concept pages
event pages
decision pages
claim summary pages
research briefs
open questions
source maps
```

The wiki should not attempt to contain all raw data.

It should contain:

```text
current assessment
stable conclusions
key entities
major disputes
important timeline summaries
links to source-backed claims
links to graph queries
links to RAG queries
open questions
```

The wiki is useful as:

```text
research map
navigation layer
synthesis cache
report seed
human-readable project memory
```

The wiki is not useful as:

```text
complete source archive
replacement for RAG
replacement for graph
replacement for timeline
ground truth database
```

---

## 6. Why Wiki Alone Fails at Large Scale

If the system has thousands or millions of documents, the wiki cannot summarize everything.

A bad design is:

```text
All sources → one huge topic wiki → answer all questions from wiki
```

This will fail because:

```text
pages become too long
old and new information mix together
source conflicts are hidden
details are lost
positions are oversimplified
LLM context limits are exceeded
updates become expensive
```

The correct design is:

```text
Raw data remains in Source Store and RAG.

Relationships remain in Graph and Claim DB.

Temporal change remains in Timeline.

Wiki only stores selected synthesis and navigation.
```

For example, a large topic page should not contain every source related to that topic.

It should contain:

```text
current assessment
confirmed facts
unconfirmed claims
major entity positions
key timeline events
open questions
links to graph and RAG queries
```

---

## 7. Wiki Page Size Rules

The wiki should be conservative and bounded.

Recommended rules:

```text
One wiki page should answer one stable research question.

One wiki page should usually be 800 to 1500 words.

If a page becomes too large, split it.

Do not dump all evidence into wiki pages.

Do not put all raw summaries into wiki pages.

Use wiki pages as synthesis and navigation, not as data storage.
```

Recommended topic structure:

```text
topics/example-topic/
├── overview.md
├── current-assessment.md
├── key-entities.md
├── confirmed-facts.md
├── disputes-and-uncertainties.md
├── timeline-summary.md
├── open-questions.md
└── source-map.md
```

---

## 8. Knowledge Generation Flow

The system should use several independent and incremental jobs.

### 8.1 Ingest Job

```text
Raw source → Source Store
```

Output:

```text
documents
metadata
cleaned_text
hashes
source records
```

---

### 8.2 Index Job

```text
Source Store → RAG Index
```

Output:

```text
chunks
embeddings
BM25 index
citation map
```

---

### 8.3 Extract Job

```text
Source Store / Chunks → Entities / Claims / Events / Relations
```

Output:

```text
entities
claims
events
relations
labels
```

---

### 8.4 Graph Build Job

```text
Entities / Claims / Events / Relations → Graph Store
```

Output:

```text
graph nodes
graph edges
claim-source links
entity-topic links
event-topic links
dependency links
```

---

### 8.5 Compile Job

```text
RAG + Graph + Timeline + Existing Wiki → Wiki / Reports
```

Output:

```text
topic pages
entity pages
event pages
decision pages
weekly reports
daily briefs
research summaries
```

---

## 9. Update Flow for New Documents

When a new document arrives:

```text
1. Add document to Source Store.
2. Clean and normalize text.
3. Update RAG index.
4. Extract entities, claims, events, and relations.
5. Update Claim DB.
6. Update Graph Store.
7. Update Timeline if events are detected.
8. Detect affected topics, entities, projects, concepts, and decisions.
9. Mark related wiki pages as dirty.
10. Regenerate only affected wiki sections if needed.
```

The system should not rewrite the entire wiki for every new document.

It should use incremental updates.

Example:

A new document about a product feature may affect:

```text
entities/product-a.md
topics/feature-x/current-assessment.md
claims/product-a-feature-x.md
timeline/feature-x.md
```

It should not trigger a full rewrite of all wiki pages.

---

## 10. Query-Time Logic

At query time, the system should not blindly query every knowledge layer.

Instead, it should use a Query Router.

The Query Router classifies the question type and chooses the retrieval strategy.

---

### 10.1 Query Types

Initial query types:

```text
Fact Question
Source Lookup Question
Relationship Question
Stance or Position Question
Trend Question
Comparison Question
Report Generation Question
Exploratory Research Question
```

---

### 10.2 Fact Question

Example:

```text
What does the source say about feature X?
```

Recommended flow:

```text
RAG → source evidence → answer with citations
```

Graph and wiki are optional.

Use RAG because the question asks for source-grounded factual evidence.

---

### 10.3 Source Lookup Question

Example:

```text
Show the original statement about this policy.
```

Recommended flow:

```text
Source Store → RAG/source lookup → original document excerpt → citation
```

Use source lookup and citations.

Do not answer from wiki.

---

### 10.4 Relationship Question

Example:

```text
How are Entity A and Entity B connected?
```

Recommended flow:

```text
1. Entity linking:
   Entity A, Entity B, relevant topics

2. Graph query:
   shared topics, events, claims, documents, dependencies, or relationships

3. RAG verification:
   retrieve source evidence for key graph relationships

4. Answer:
   structured explanation with citations
```

Use Graph first, then RAG verification.

Wiki may provide background context if available.

---

### 10.5 Stance or Position Question

Example:

```text
Does Entity A support Policy X?
```

Recommended flow:

```text
1. Claim DB:
   find claims where actor/entity = Entity A and topic = Policy X

2. Graph:
   find related policies, events, concepts, and entities

3. Timeline:
   check whether position changed over time

4. RAG:
   verify the claims against original source documents

5. Wiki:
   read existing synthesis page if available

6. Answer:
   nuanced position summary with confidence and citations
```

Expected answer behavior:

```text
Do not answer with a simple yes/no if evidence is nuanced.

Separate:
- confirmed position
- conditional support
- opposition
- uncertainty
- source interpretation
- speculation
```

---

### 10.6 Trend Question

Example:

```text
Is this topic accelerating, declining, or mostly rhetoric?
```

Recommended flow:

```text
1. Wiki:
   read current topic assessment if available

2. Timeline:
   collect major events over time

3. Graph / Claim DB:
   collect entity positions, actions, and topic relationships

4. RAG:
   retrieve latest and highest-quality source evidence

5. Contradiction check:
   compare source evidence against existing wiki synthesis

6. Answer:
   distinguish confirmed facts, interpretation, speculation, and open questions
```

The answer should separate:

```text
confirmed evidence
institutional or structural progress
announcements
actual implementation
source disagreement
speculation
```

---

### 10.7 Comparison Question

Example:

```text
Compare Entity A and Entity B on Topic X.
```

Recommended flow:

```text
1. Claim DB:
   retrieve claims for Entity A and Entity B on Topic X

2. Graph:
   retrieve relationships and related events

3. Timeline:
   compare changes over time

4. RAG:
   verify key claims and retrieve source citations

5. Wiki:
   use existing synthesis if available

6. Answer:
   structured comparison table and explanation
```

---

### 10.8 Report Generation Question

Example:

```text
Generate a topic brief for the last 30 days.
```

Recommended flow:

```text
1. RAG:
   retrieve recent documents

2. Claim DB:
   extract recent claims

3. Graph:
   map entities, concepts, events, claims, and relationships

4. Timeline:
   order developments by date

5. Wiki:
   read existing topic page as background

6. Report generator:
   create structured report

7. Save:
   export Markdown report and optionally update wiki summary
```

---

## 11. Answer Composition Rules

Every final answer should include as much of the following as appropriate:

```text
direct answer
evidence summary
source citations
source type distinction
entity positions
timeline if relevant
confidence level
uncertainties
contradictions
open questions
```

Always distinguish:

```text
primary source
secondary source
interpretation
speculation
unverified claim
model inference
```

---

## 12. Priority of Evidence

When layers disagree, use this priority order:

```text
1. Original source documents
2. High-quality primary sources
3. Source-grounded claims
4. Graph relationships with source links
5. Wiki synthesis
6. Model inference
```

Rules:

```text
If wiki conflicts with source evidence, prefer source evidence.

If graph relation lacks source evidence, treat it as unverified.

If a claim is not source-backed, do not present it as fact.

If sources conflict, explicitly state the conflict.

If evidence is old, mark the answer as potentially stale.

If the question depends on current events, prefer recent source evidence.
```

---

## 13. Relationship Between the Three Knowledge Views

### RAG

```text
Role:
  evidence retrieval

Strength:
  original text, latest info, citations

Weakness:
  weak at multi-hop relation reasoning
```

### GraphRAG / Graph

```text
Role:
  relationship and multi-hop reasoning

Strength:
  entities, concepts, claims, dependencies, timelines, relationships

Weakness:
  extracted relations can be incomplete or wrong without source verification
```

### llm-wiki

```text
Role:
  synthesis and navigation

Strength:
  reusable summaries, research memory, human-readable pages

Weakness:
  incomplete, potentially stale, not suitable for storing all raw data
```

Combined answer model:

```text
Answer = wiki synthesis + graph reasoning + RAG evidence
```

But evidence priority is:

```text
RAG/source evidence > graph extraction > wiki summary
```

---

## 14. Implementation Requirements for Answer Engine

The `answer_engine` should implement the following stages:

```text
1. classify_question
2. retrieve_wiki_context_if_needed
3. retrieve_graph_context_if_needed
4. retrieve_timeline_context_if_needed
5. retrieve_rag_evidence
6. verify_against_sources
7. detect_conflicts
8. compose_answer
9. produce_citations
10. estimate_confidence
11. mark_stale_wiki_pages_if_needed
```

Pseudocode:

```python
def answer_question(question: str) -> Answer:
    query_type = router.classify(question)

    context = AnswerContext()

    if query_type in ["trend", "report", "exploratory", "comparison"]:
        context.wiki = wiki.retrieve_relevant_pages(question)

    if query_type in ["relationship", "stance", "trend", "report", "comparison"]:
        context.graph = graph.retrieve_relevant_subgraph(question)
        context.claims = claims.retrieve_relevant_claims(question)

    if query_type in ["trend", "stance", "report", "comparison"]:
        context.timeline = timeline.retrieve_relevant_events(question)

    context.evidence = rag.retrieve_evidence(
        question=question,
        graph_context=context.graph,
        claim_context=context.claims,
        wiki_context=context.wiki,
    )

    verified_context = source_grounding.verify(context)

    conflicts = contradiction_check.detect(verified_context)

    answer = composer.compose(
        question=question,
        query_type=query_type,
        context=verified_context,
        conflicts=conflicts,
    )

    answer.confidence = confidence.estimate(verified_context, conflicts)
    answer.citations = citations.generate(verified_context)

    return answer
```

---

## 15. Implementation Requirements for Wiki Updates

The wiki update engine should not rebuild everything by default.

It should implement dirty-page tracking.

Pseudocode:

```python
def process_new_document(document_id: str):
    document = source_store.get(document_id)

    rag.index_document(document)

    extracted = extraction.extract_all(document)

    claims.upsert(extracted.claims)
    entities.upsert(extracted.entities)
    events.upsert(extracted.events)

    graph.merge(
        entities=extracted.entities,
        relations=extracted.relations,
        claims=extracted.claims,
        events=extracted.events,
    )

    affected_pages = impact_analyzer.find_affected_wiki_pages(
        entities=extracted.entities,
        claims=extracted.claims,
        events=extracted.events,
        topics=extracted.topics,
    )

    wiki.mark_dirty(affected_pages)
```

Then:

```python
def update_dirty_wiki_pages():
    pages = wiki.get_dirty_pages()

    for page in pages:
        source_evidence = rag.retrieve_for_page(page)
        graph_context = graph.retrieve_for_page(page)
        timeline_context = timeline.retrieve_for_page(page)

        new_page = wiki.generate_page(
            page=page,
            source_evidence=source_evidence,
            graph_context=graph_context,
            timeline_context=timeline_context,
        )

        wiki.save(new_page)
```

---

## 16. Project Safety and Quality Rules for Agents

Agents working on this project must obey these rules:

```text
1. Do not treat wiki pages as ground truth.
2. Do not answer from graph alone without source verification.
3. Do not write RAG-generated answers directly into graph as facts.
4. Do not summarize away source conflicts.
5. Do not flatten nuanced positions into yes/no unless sources justify it.
6. Preserve publication dates.
7. Preserve source type and source origin.
8. Track claims as first-class objects.
9. Track changes over time.
10. Prefer primary sources for authoritative claims.
11. Mark uncertain, speculative, or weakly sourced claims clearly.
12. Mark stale wiki pages when new source evidence contradicts them.
13. Keep raw source documents accessible for citation.
14. Every final answer should be source-grounded when it contains factual claims.
```

---

## 17. MVP Scope

The first version should not try to build the entire system.

MVP v0.1 should include:

```text
manual URL import
manual PDF import
manual Markdown import
source metadata storage
document cleaning
document-aware chunking
hybrid retrieval
citation generation
claim extraction
basic entity extraction
basic ask CLI
one topic wiki page generator
```

MVP v0.1 should not include:

```text
large-scale crawler
full web dashboard
multi-user permissions
advanced graph visualization
full Microsoft-style community GraphRAG
automatic multilingual translation
complex report scheduling
```

---

## 18. MVP Query Targets

The first version should be able to answer questions like:

```text
What are the confirmed facts about this topic?

What does the source say about this issue?

Does Entity A support or oppose Policy X?

What changed after a specific event or date?

Which entities are most connected to this topic?

Is this claim confirmed, disputed, or speculative?
```

Answers should include:

```text
direct answer
source-backed evidence
citations
confidence level
distinction between source evidence, interpretation, and speculation
```

---

## 19. Final Architecture Summary

The system should be implemented as a multi-layer source-grounded intelligence system:

```text
Source Store:
  canonical evidence

RAG:
  evidence retrieval and citation

Graph / Claim DB:
  relationship, structure, and multi-hop reasoning

Timeline:
  temporal change and trend analysis

llm-wiki:
  synthesis, navigation, and report memory

Answer Engine:
  dynamic combination of all layers depending on question type
```

Final rule:

```text
Wiki gives existing understanding.
Graph gives relationship reasoning.
RAG gives source evidence.

The final answer must be grounded in source evidence.
```
