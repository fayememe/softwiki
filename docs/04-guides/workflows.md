# Research Workflows

softwiki provides several preset workflows covering scenarios from quick Q&A to deep wiki compilation.

## research — Deep Research Flow

Multi-query → Compare viewpoints → Synthesis brief

1. Analyze the question, decompose into multiple sub-queries.
2. Use websearch/webfetch to gather sources across dimensions, cross-reference viewpoints from different sources.
3. **[wiki-admin / wiki-manage mode]** Check scope for each high-quality source (see `config/scope.md`). If in scope, call `softwiki_ingest` to ingest.
4. **[wiki-admin / wiki-manage mode]** After ingestion, ask the user whether to rebuild affected wiki pages (`softwiki_wiki_build`).
5. **[wiki-work mode]** If valuable sources are found, use the `submit` workflow to pre-submit for admin review.
6. Output a structured research summary with citations.

## wiki-compile — Wiki Compilation Flow

Collect evidence → Identify consensus/disagreement → Generate document

1. Call `softwiki_status` to confirm the workspace has relevant documents.
2. Use websearch to find missing context or latest developments.
3. If new relevant sources are found, `softwiki_ingest` first.
4. Call `softwiki_wiki_build` to generate a markdown wiki page.
5. Report the compiled page's output path.

## simple-q&a — Quick Q&A Flow

Single hybrid query (knowledge base + web)

1. Answer directly using existing knowledge or via websearch for the latest information.
2. **[wiki-admin / wiki-manage mode]** If high-quality in-scope sources are found, ask the user whether to ingest.

## contribute — Knowledge Contribution Flow

1. Call `softwiki_ingest` to ingest the provided URL, file, or notes.
2. Confirm ingestion results and return the document ID.
3. Identify potentially affected topics in `config/topics.yaml`.
4. Execute `softwiki_wiki_build` for each affected topic.

## submit — Submit for Review Flow (wiki-work only)

For `wiki-work` role: submit research results or sources to admin for review, **without directly modifying** the knowledge base.

1. Summarize research findings or write structured notes in the session output directory.
2. Notes include: source URLs, relevance to workspace topics, key findings, suggested wiki pages to update.
3. Inform the user the submission has been staged, awaiting review by a `wiki-manage` or `wiki-admin` user.
4. **Do not call** `softwiki_ingest`. **Do not directly modify** the knowledge base.

---

## Ingest → Index → Q&A → Wiki Complete Example

```bash
# 1. Ingest: import document from URL
./sw ingest --url "https://example.com/de-dollarization-overview"

# 2. Index: build vector and keyword indexes
./sw index

# 3. Q&A: ask questions based on knowledge base
./sw ask "What are the key findings?"

# 4. Compile wiki: generate structured wiki page
./sw wiki build --topic de-dollarization
```

## Shell Workflows

In **Admin** / **Manage** modes, Shell automatically works in the following loop:

```
research → ingest → wiki build → (loop)
```

That is: research with websearch → ingest high-quality sources → compile/update wiki pages → return to research.
This loop does not require manual mode switching; the system advances automatically based on conversation context.

---

> **Note**: See the [CLI documentation](../03-operations/cli.md) for the full command reference. This page only covers workflow-level interaction logic.
