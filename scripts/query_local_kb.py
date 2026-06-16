#!/usr/bin/env python3
"""Layer 9: Local keyword search over the knowledge base.

Usage:
    python3 scripts/query_local_kb.py "founder bottleneck"
    python3 scripts/query_local_kb.py "right fit client" --limit 10

Searches SQLite FTS5 when available, falls back to SQLite LIKE, and finally
to scanning database/transcript_chunks.jsonl directly. Retrieval only — no
external APIs, no answer generation.
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT, load_config, read_jsonl  # noqa: E402

EXCERPT_CHARS = 280


def make_excerpt(text, query_terms):
    """Short excerpt centered on the first matching term."""
    lower = text.lower()
    pos = -1
    for term in query_terms:
        pos = lower.find(term.lower())
        if pos != -1:
            break
    if pos == -1:
        pos = 0
    start = max(0, pos - EXCERPT_CHARS // 3)
    end = min(len(text), start + EXCERPT_CHARS)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"


def search_sqlite(db_path, query, limit):
    conn = sqlite3.connect(db_path)
    try:
        has_fts = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='chunks_fts'"
        ).fetchone()
        if has_fts:
            # quote each term to keep FTS5 syntax characters literal
            terms = [t for t in re.split(r"\s+", query.strip()) if t]
            fts_query = " ".join(f'"{t}"' for t in terms)
            rows = conn.execute(
                "SELECT c.chunk_id, c.source_file, c.transcript_title, "
                "c.inferred_date, c.chunk_index, c.text "
                "FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
                "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            return rows, "sqlite-fts5"
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT chunk_id, source_file, transcript_title, inferred_date, "
            "chunk_index, text FROM chunks WHERE text LIKE ? LIMIT ?",
            (like, limit),
        ).fetchall()
        return rows, "sqlite-like"
    finally:
        conn.close()


def search_jsonl(jsonl_path, query, limit):
    terms = [t.lower() for t in re.split(r"\s+", query.strip()) if t]
    scored = []
    for rec in read_jsonl(jsonl_path):
        text_lower = rec["text"].lower()
        hits = sum(text_lower.count(t) for t in terms)
        if hits and all(t in text_lower for t in terms):
            scored.append((hits, rec))
    scored.sort(key=lambda x: -x[0])
    rows = [
        (r["chunk_id"], r["source_file"], r["transcript_title"],
         r["inferred_date"], r["chunk_index"], r["text"])
        for _, r in scored[:limit]
    ]
    return rows, "jsonl-scan"


def main():
    parser = argparse.ArgumentParser(description="Search the local transcript KB.")
    parser.add_argument("query", help="Search phrase, e.g. \"right fit client\"")
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    args = parser.parse_args()

    config = load_config()
    db_dir = PROJECT_ROOT / config["database_output_dir"]
    db_path = db_dir / "tech_lab_knowledge_base.sqlite"
    jsonl_path = db_dir / "transcript_chunks.jsonl"

    if db_path.exists():
        rows, backend = search_sqlite(db_path, args.query, args.limit)
        if not rows and backend == "sqlite-fts5":
            # FTS5 found nothing for all terms; nothing more to try in SQLite
            pass
    elif jsonl_path.exists():
        rows, backend = search_jsonl(jsonl_path, args.query, args.limit)
    else:
        print("No database found. Run python3 scripts/run_pipeline.py first.")
        return 1

    terms = [t for t in re.split(r"\s+", args.query.strip()) if t]
    print(f'Query: "{args.query}"  (backend: {backend})')
    if not rows:
        print("No matching chunks found.")
        return 0
    print(f"Top {len(rows)} matching chunk(s):\n")
    for i, (chunk_id, source_file, title, date, idx, text) in enumerate(rows, 1):
        print(f"{i}. {title}  [chunk {idx}]")
        print(f"   source_file: {source_file}")
        print(f"   inferred_date: {date}   chunk_id: {chunk_id}")
        print(f"   excerpt: {make_excerpt(text, terms)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
