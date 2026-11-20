"""Pilot: generate one small page per subject, to compare against the 250-claim mega page.

Reads canonical claims for a subject directly from Postgres, calls the same
`wiki_compilation` LLM profile the real generator uses, and writes one markdown
file per subject into /tmp/wiki-pilot/.

Usage (inside the api container or on the host with DB access):
    python3 scripts/wiki_pilot_subjects.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from softwiki.intelligence.llm_client import get_llm_client_and_params  # noqa: E402

OUT = Path("/tmp/wiki-pilot")

# (subject, cap for demoing the slide) — caps chosen from actual claim counts.
SUBJECTS = [
    ("AeroPress", 12),
    ("Cortado", 10),
    ("Cold brew", 11),
    ("Moka pot", 15),
    ("Iced coffee", 23),
    ("Coffeehouse", 129),   # deliberate counter-example: too big for one page
]

SYSTEM = """You are compiling a wiki entry for ONE subject from a knowledge base.

Hard rules:
- Use ONLY the numbered claims below. No outside knowledge. No inference beyond them.
- Every sentence that states a fact must end with the claim number in brackets, e.g. [3].
- If the claims disagree, say so explicitly in a "Conflicts" section and cite both numbers.
  Never silently pick one.
- If a claim is only tangentially about the subject (e.g. it mentions the subject while
  discussing a different product), put it under "Mentions" instead of treating it as fact
  about the subject.
- Do not invent sections. If there is nothing to say for a section, omit it.

Structure:
# <Subject>
one-paragraph summary
## Facts            (organized, each line cited)
## Conflicts        (only if claims disagree)
## Mentions         (only if some claims are tangential)
## Sources          (claim number -> source name and date)
"""


def build_prompt(subject: str, rows: list[tuple]) -> str:
    lines = [f"Subject: {subject}", "", "Claims:", ""]
    for i, row in enumerate(rows, 1):
        text_, actor, title, page_start, page_end, _conf = row
        src = (title or actor or "unknown").strip()
        if page_start is not None:
            span = f"p.{page_start}" if page_end in (None, page_start) else f"p.{page_start}-{page_end}"
            src = f"{src}, {span}"
        lines.append(f"[{i}] ({src}) {text_.strip()}")
    return "\n".join(lines)


def main() -> int:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_engine(dsn)

    client, model, temperature, max_tokens = get_llm_client_and_params("wiki_compilation")
    if client is None:
        print(f"no usable LLM client (model={model}); check keys", file=sys.stderr)
        return 2
    print(f"model={model} temperature={temperature} max_tokens={max_tokens}")

    OUT.mkdir(parents=True, exist_ok=True)
    index: list[str] = []

    for subject, cap in SUBJECTS:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.text,
                           c.actor,
                           d.title,
                           c.primary_page_start,
                           c.primary_page_end,
                           c.confidence::text
                    FROM canonical_claims c
                    LEFT JOIN documents d ON d.id = c.primary_document_id
                    WHERE c.text ILIKE :pat AND c.status = 'active'
                    ORDER BY c.confidence DESC, c.primary_document_id
                    """
                ),
                {"pat": f"%{subject}%"},
            ).fetchall()

        total = len(rows)
        used = rows[:cap]
        prompt = build_prompt(subject, [tuple(r) for r in used])

        print(f"\n--- {subject}: {total} claims total, sending {len(used)} "
              f"(prompt {len(prompt)} chars)")

        resp = client.chat.completions.create(
            model=model,
            temperature=temperature or 0.0,
            max_tokens=max_tokens or 8000,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        finish = resp.choices[0].finish_reason
        usage = resp.usage

        slug = subject.lower().replace(" ", "-").replace("'", "")
        path = OUT / f"{slug}.md"
        header = (
            f"<!-- pilot: subject={subject} claims_total={total} claims_used={len(used)} "
            f"model={model} finish={finish} "
            f"tokens_in={getattr(usage, 'prompt_tokens', None)} "
            f"tokens_out={getattr(usage, 'completion_tokens', None)} -->\n"
        )
        path.write_text(header + content, encoding="utf-8")
        print(f"    -> {path}  finish={finish} "
              f"out_tokens={getattr(usage, 'completion_tokens', None)} "
              f"chars={len(content)}")
        index.append(f"| {subject} | {total} | {len(used)} | {finish} | {len(content)} | {path.name} |")

    (OUT / "INDEX.md").write_text(
        "# Wiki pilot — one page per subject\n\n"
        "| subject | claims in KB | claims sent | finish | output chars | file |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(index) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT}/INDEX.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
