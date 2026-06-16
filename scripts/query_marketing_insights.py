#!/usr/bin/env python3
"""Search the extracted marketing insights.

Usage:
    python3 scripts/query_marketing_insights.py "right fit client"
    python3 scripts/query_marketing_insights.py "offer positioning" --limit 10
    python3 scripts/query_marketing_insights.py "bottleneck" --asset-type content_hooks

Scans database/extracted_marketing_insights.jsonl across all content and
marketing-asset fields. Retrieval only — no external APIs, no generation.
Results rank by match count, then usefulness_score, then confidence_score.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT, read_jsonl  # noqa: E402

INSIGHTS_PATH = PROJECT_ROOT / "database" / "extracted_marketing_insights.jsonl"

SEARCH_FIELDS = [
    "core_topic", "subtopics", "client_pain_points", "client_desires",
    "client_objections", "beliefs_challenged", "mistakes_identified",
    "better_questions", "frameworks_or_models", "stories_or_examples",
    "metaphors_or_phrases", "quotable_lines", "right_fit_client_questions",
    "content_hooks", "youtube_angles", "short_form_angles", "email_angles",
    "sales_page_angles", "offer_positioning_notes", "audience_segments",
    "tags",
]
EXCERPT_CHARS = 220


def field_texts(record, field):
    value = record.get(field)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)]


def match_record(record, terms, fields):
    """Return (hit_count, matching_fields, sample_items)."""
    hits = 0
    matching_fields = []
    samples = []
    for field in fields:
        field_hits = 0
        for text in field_texts(record, field):
            tl = text.lower()
            term_hits = sum(tl.count(t) for t in terms)
            if term_hits and all(t in tl for t in terms):
                field_hits += term_hits
                if len(samples) < 3:
                    samples.append((field, text))
        if field_hits:
            hits += field_hits
            matching_fields.append(field)
    return hits, matching_fields, samples


def main():
    parser = argparse.ArgumentParser(description="Search extracted marketing insights.")
    parser.add_argument("query", help='Search phrase, e.g. "right fit client"')
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    parser.add_argument("--asset-type", dest="asset_type", choices=SEARCH_FIELDS,
                        help="Restrict the search to one field")
    args = parser.parse_args()

    if not INSIGHTS_PATH.exists():
        print(f"No insights file at {INSIGHTS_PATH}.")
        print("Run python3 scripts/run_marketing_extraction_pipeline.py first.")
        return 1

    terms = [t.lower() for t in re.split(r"\s+", args.query.strip()) if t]
    fields = [args.asset_type] if args.asset_type else SEARCH_FIELDS

    results = []
    records = read_jsonl(INSIGHTS_PATH)
    for record in records:
        hits, matching_fields, samples = match_record(record, terms, fields)
        if hits:
            results.append((hits, record, matching_fields, samples))
    results.sort(key=lambda r: (
        -r[0], -(r[1].get("usefulness_score") or 0),
        -(r[1].get("confidence_score") or 0)))

    mock_count = sum(1 for r in records if r.get("extraction_provider") == "mock")
    print(f'Query: "{args.query}"  ({len(records)} records scanned'
          + (f", fields: {args.asset_type}" if args.asset_type else "") + ")")
    if mock_count:
        print(f"NOTE: {mock_count}/{len(records)} records are MOCK-mode "
              "placeholder extractions.")
    if not results:
        print("No matching insight records found.")
        return 0

    print(f"Top {min(args.limit, len(results))} of {len(results)} matching record(s):\n")
    for i, (hits, record, matching_fields, samples) in enumerate(
            results[:args.limit], 1):
        print(f"{i}. {record['transcript_title']}  "
              f"[usefulness {record.get('usefulness_score')}, "
              f"confidence {record.get('confidence_score')}]")
        print(f"   record_id: {record['record_id']}")
        print(f"   chunk_id: {record['chunk_id']}   "
              f"source_file: {record['source_file']}")
        print(f"   inferred_date: {record.get('inferred_date')}")
        print(f"   matched fields: {', '.join(matching_fields)}")
        for field, text in samples:
            excerpt = re.sub(r"\s+", " ", text)[:EXCERPT_CHARS]
            suffix = "…" if len(text) > EXCERPT_CHARS else ""
            print(f"     - [{field}] {excerpt}{suffix}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
