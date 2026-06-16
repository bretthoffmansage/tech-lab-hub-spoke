#!/usr/bin/env python3
"""Layer 7: Build LLM-ready extraction packets.

Joins chunks with their heuristic signals into self-contained packets that a
future LLM extraction run can process in batches. No LLM is called here.

Writes processed/extracted_insights/llm_packets.jsonl and the prompt template.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, now_iso, read_jsonl, write_jsonl,
    write_text_report,
)

SCHEMA_VERSION = "1.0"

PROMPT_TEMPLATE = """# LLM Marketing Intelligence Extraction — Prompt Template (schema v1.0)

You are extracting structured marketing intelligence from one chunk of a raw
company call transcript. The transcript has NO speaker labels and NO reliable
timestamps. Treat it as plain unstructured call text.

## Input

You will receive one JSON packet with these fields:
- packet_id, chunk_id, source_file, cleaned_file, transcript_title,
  inferred_date, chunk_index
- text — the transcript chunk (this is your ONLY source of truth)
- basic_signals — rough keyword-based hints (questions, possible teaching
  points, objections, pain points, mistakes, hooks). These are HINTS only;
  verify each against the text and ignore anything not actually supported.

## Your task

Return ONE JSON object following the schema in docs/extraction_schema.md,
with these rules:

1. Use ONLY the provided chunk text. Do not use outside knowledge to add
   facts, names, numbers, or claims.
2. Do not invent facts. Every extracted item must be grounded in the text.
3. Do not infer or name speakers. The text has no reliable speaker identity.
4. Do not depend on or invent timestamps.
5. Return VALID JSON ONLY — no markdown, no commentary, no code fences.
6. If a field has nothing present in the text, return an empty list [] for
   list fields or null for scalar fields. Never pad fields with guesses.
7. right_fit_client_questions must be derived only from pains, desires,
   objections, and situations actually present in this chunk's text.
8. Preserve traceability: copy chunk_id, source_file, cleaned_file,
   transcript_title, inferred_date, and chunk_index from the packet
   unchanged. Set record_id to "<chunk_id>__extract_v1".
9. source_text_excerpt must be a VERBATIM quote from the chunk (~300 chars)
   that best anchors your extraction.
10. quotable_lines and metaphors_or_phrases must be verbatim from the text.
11. Score usefulness_score 0-5 using the scale in docs/extraction_schema.md
    (0 junk/housekeeping … 5 premium reusable insight) and set
    confidence_score between 0 and 1.

## Output schema (all keys required)

{
  "record_id": "...", "source_file": "...", "cleaned_file": "...",
  "transcript_title": "...", "inferred_date": "... or null",
  "chunk_id": "...", "chunk_index": 0, "source_text_excerpt": "...",
  "core_topic": "... or null", "subtopics": [],
  "client_pain_points": [], "client_desires": [], "client_objections": [],
  "beliefs_challenged": [], "mistakes_identified": [], "better_questions": [],
  "frameworks_or_models": [], "stories_or_examples": [],
  "metaphors_or_phrases": [], "quotable_lines": [],
  "right_fit_client_questions": [], "content_hooks": [],
  "youtube_angles": [], "short_form_angles": [], "email_angles": [],
  "sales_page_angles": [], "offer_positioning_notes": [],
  "audience_segments": [], "tags": [],
  "usefulness_score": 0, "confidence_score": 0.0
}
"""


def main():
    config = load_config()
    db_dir = PROJECT_ROOT / config["database_output_dir"]
    insights_dir = PROJECT_ROOT / config.get(
        "extracted_insights_dir", "processed/extracted_insights")

    chunks_path = db_dir / "transcript_chunks.jsonl"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}. Run scripts/chunk_transcripts.py first.")
        return 1
    chunks = read_jsonl(chunks_path)

    signals_path = db_dir / "basic_signals.jsonl"
    signals_by_chunk = {}
    if signals_path.exists():
        for rec in read_jsonl(signals_path):
            signals_by_chunk[rec["chunk_id"]] = {
                "signals": rec["signals"],
                "potential_usefulness_score": rec["potential_usefulness_score"],
            }
        print(f"Loaded signals for {len(signals_by_chunk)} chunks.")
    else:
        print("No basic_signals.jsonl found — packets will have basic_signals: null.")

    packets = []
    for c in chunks:
        packets.append({
            "packet_id": f"{c['chunk_id']}__packet_v{SCHEMA_VERSION}",
            "chunk_id": c["chunk_id"],
            "source_file": c["source_file"],
            "cleaned_file": c["cleaned_file"],
            "transcript_title": c["transcript_title"],
            "inferred_date": c["inferred_date"],
            "chunk_index": c["chunk_index"],
            "text": c["text"],
            "basic_signals": signals_by_chunk.get(c["chunk_id"]),
            "extraction_schema_version": SCHEMA_VERSION,
            "packet_built_at": now_iso(),
        })

    out_path = insights_dir / "llm_packets.jsonl"
    write_jsonl(out_path, packets)
    write_text_report(insights_dir / "llm_extraction_prompt_template.md",
                      PROMPT_TEMPLATE)

    print(f"Built {len(packets)} packets -> {out_path}")
    print(f"Prompt template -> {insights_dir / 'llm_extraction_prompt_template.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
