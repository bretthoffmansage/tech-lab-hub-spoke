#!/usr/bin/env python3
"""Layer 8: Build the local SQLite knowledge base.

Standard library sqlite3 only. Rebuilds database/tech_lab_knowledge_base.sqlite
from the JSONL outputs (the JSONL files remain the source of truth).

Tables: transcripts, chunks, basic_signals, pipeline_runs — plus
marketing_insights and marketing_assets when
database/extracted_marketing_insights.jsonl exists.
Full-text search uses FTS5 when available; otherwise falls back to plain
tables (queries then use LIKE) and the report documents the limitation.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, now_iso, read_jsonl, write_text_report,
)

DB_NAME = "tech_lab_knowledge_base.sqlite"

# maps marketing_assets.asset_type -> source list field on insight records
ASSET_TYPE_FIELDS = {
    "right_fit_client_question": "right_fit_client_questions",
    "content_hook": "content_hooks",
    "youtube_angle": "youtube_angles",
    "short_form_angle": "short_form_angles",
    "email_angle": "email_angles",
    "sales_page_angle": "sales_page_angles",
    "pain_point": "client_pain_points",
    "objection": "client_objections",
    "framework": "frameworks_or_models",
    "story_or_example": "stories_or_examples",
    "quote": "quotable_lines",
    "offer_positioning_note": "offer_positioning_notes",
}


def fts5_available(conn):
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE temp.fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def main():
    config = load_config()
    db_dir = PROJECT_ROOT / config["database_output_dir"]
    chunks_path = db_dir / "transcript_chunks.jsonl"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}. Run scripts/chunk_transcripts.py first.")
        return 1

    chunks = read_jsonl(chunks_path)
    signals_path = db_dir / "basic_signals.jsonl"
    signals = read_jsonl(signals_path) if signals_path.exists() else []
    insights_path = db_dir / "extracted_marketing_insights.jsonl"
    insights = read_jsonl(insights_path) if insights_path.exists() else []

    db_path = db_dir / DB_NAME
    if db_path.exists():
        db_path.unlink()  # databases are disposable indexes; JSONL is the truth
    conn = sqlite3.connect(db_path)
    has_fts = fts5_available(conn)

    conn.executescript("""
        CREATE TABLE transcripts (
            source_file TEXT PRIMARY KEY,
            cleaned_file TEXT,
            transcript_title TEXT,
            inferred_date TEXT,
            chunk_count INTEGER,
            total_words INTEGER
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            source_file TEXT REFERENCES transcripts(source_file),
            cleaned_file TEXT,
            transcript_title TEXT,
            inferred_date TEXT,
            chunk_index INTEGER,
            word_count INTEGER,
            text TEXT,
            previous_chunk_id TEXT,
            next_chunk_id TEXT
        );
        CREATE INDEX idx_chunks_source ON chunks(source_file);
        CREATE INDEX idx_chunks_title ON chunks(transcript_title);
        CREATE INDEX idx_chunks_date ON chunks(inferred_date);
        CREATE TABLE basic_signals (
            chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
            potential_usefulness_score INTEGER,
            question_count INTEGER,
            teaching_point_count INTEGER,
            objection_count INTEGER,
            pain_point_count INTEGER,
            mistake_count INTEGER,
            hook_count INTEGER,
            signals_json TEXT
        );
        CREATE TABLE pipeline_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at TEXT,
            chunks_loaded INTEGER,
            signals_loaded INTEGER,
            fts5_enabled INTEGER,
            notes TEXT
        );
    """)

    # transcripts table aggregated from chunks
    by_source = {}
    for c in chunks:
        t = by_source.setdefault(c["source_file"], {
            "source_file": c["source_file"],
            "cleaned_file": c["cleaned_file"],
            "transcript_title": c["transcript_title"],
            "inferred_date": c["inferred_date"],
            "chunk_count": 0,
            "total_words": 0,
        })
        t["chunk_count"] += 1
        t["total_words"] += c["word_count"]
    conn.executemany(
        "INSERT INTO transcripts VALUES (:source_file,:cleaned_file,"
        ":transcript_title,:inferred_date,:chunk_count,:total_words)",
        by_source.values(),
    )
    conn.executemany(
        "INSERT INTO chunks VALUES (:chunk_id,:source_file,:cleaned_file,"
        ":transcript_title,:inferred_date,:chunk_index,:word_count,:text,"
        ":previous_chunk_id,:next_chunk_id)",
        chunks,
    )
    conn.executemany(
        "INSERT INTO basic_signals VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                s["chunk_id"],
                s["potential_usefulness_score"],
                len(s["signals"]["questions"]),
                len(s["signals"]["teaching_points"]),
                len(s["signals"]["objections"]),
                len(s["signals"]["pain_points"]),
                len(s["signals"]["mistakes"]),
                len(s["signals"]["hooks"]),
                json.dumps(s["signals"], ensure_ascii=False),
            )
            for s in signals
        ],
    )

    # marketing intelligence tables (only when an extraction run exists)
    asset_rows = []
    if insights:
        conn.executescript("""
            CREATE TABLE marketing_insights (
                record_id TEXT PRIMARY KEY,
                chunk_id TEXT REFERENCES chunks(chunk_id),
                source_file TEXT,
                cleaned_file TEXT,
                transcript_title TEXT,
                inferred_date TEXT,
                chunk_index INTEGER,
                core_topic TEXT,
                usefulness_score INTEGER,
                confidence_score REAL,
                extraction_provider TEXT,
                extraction_model TEXT,
                extraction_schema_version TEXT,
                extracted_at TEXT,
                record_json TEXT
            );
            CREATE INDEX idx_mi_chunk ON marketing_insights(chunk_id);
            CREATE INDEX idx_mi_source ON marketing_insights(source_file);
            CREATE INDEX idx_mi_score ON marketing_insights(usefulness_score);
            CREATE TABLE marketing_assets (
                asset_id TEXT PRIMARY KEY,
                record_id TEXT REFERENCES marketing_insights(record_id),
                chunk_id TEXT,
                source_file TEXT,
                transcript_title TEXT,
                inferred_date TEXT,
                asset_type TEXT,
                asset_text TEXT,
                usefulness_score INTEGER,
                confidence_score REAL,
                tags_json TEXT
            );
            CREATE INDEX idx_ma_type ON marketing_assets(asset_type);
            CREATE INDEX idx_ma_record ON marketing_assets(record_id);
        """)
        conn.executemany(
            "INSERT OR REPLACE INTO marketing_insights VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r["record_id"], r["chunk_id"], r["source_file"],
                    r["cleaned_file"], r["transcript_title"],
                    r.get("inferred_date"), r.get("chunk_index"),
                    r.get("core_topic"), r.get("usefulness_score"),
                    r.get("confidence_score"), r.get("extraction_provider"),
                    r.get("extraction_model"),
                    r.get("extraction_schema_version"), r.get("extracted_at"),
                    json.dumps(r, ensure_ascii=False),
                )
                for r in insights
            ],
        )
        for r in insights:
            tags_json = json.dumps(r.get("tags") or [], ensure_ascii=False)
            for asset_type, field in ASSET_TYPE_FIELDS.items():
                for i, text in enumerate(r.get(field) or []):
                    asset_rows.append((
                        f"{r['record_id']}__{asset_type}_{i:03d}",
                        r["record_id"], r["chunk_id"], r["source_file"],
                        r["transcript_title"], r.get("inferred_date"),
                        asset_type, text, r.get("usefulness_score"),
                        r.get("confidence_score"), tags_json,
                    ))
        conn.executemany(
            "INSERT OR REPLACE INTO marketing_assets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            asset_rows,
        )

    if has_fts:
        conn.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5("
            "chunk_id UNINDEXED, transcript_title, text, "
            "content='chunks', content_rowid='rowid')"
        )
        conn.execute(
            "INSERT INTO chunks_fts(rowid, chunk_id, transcript_title, text) "
            "SELECT rowid, chunk_id, transcript_title, text FROM chunks"
        )
        if insights:
            conn.execute(
                "CREATE VIRTUAL TABLE marketing_assets_fts USING fts5("
                "asset_id UNINDEXED, asset_type, asset_text, "
                "content='marketing_assets', content_rowid='rowid')"
            )
            conn.execute(
                "INSERT INTO marketing_assets_fts"
                "(rowid, asset_id, asset_type, asset_text) "
                "SELECT rowid, asset_id, asset_type, asset_text "
                "FROM marketing_assets"
            )

    notes = "FTS5 enabled" if has_fts else (
        "FTS5 NOT available in this Python's SQLite build; "
        "query_local_kb.py will fall back to LIKE search."
    )
    conn.execute(
        "INSERT INTO pipeline_runs (ran_at, chunks_loaded, signals_loaded, "
        "fts5_enabled, notes) VALUES (?,?,?,?,?)",
        (now_iso(), len(chunks), len(signals), int(has_fts), notes),
    )
    conn.commit()
    conn.close()

    report = "\n".join([
        "# SQLite Database Report", "",
        f"Generated: {now_iso()}", "",
        f"- Database: `database/{DB_NAME}`",
        f"- Transcripts: **{len(by_source)}**",
        f"- Chunks: **{len(chunks)}**",
        f"- Signal records: **{len(signals)}**",
        f"- Marketing insight records: **{len(insights)}**"
        + ("" if insights else " (run scripts/extract_marketing_insights.py to add)"),
        f"- Flattened marketing assets: **{len(asset_rows)}**",
        f"- Full-text search (FTS5): **{'available' if has_fts else 'NOT available'}**",
        "",
        "## Tables",
        "",
        "- `transcripts` — one row per source transcript (title, date, sizes)",
        "- `chunks` — every chunk with full text; searchable by source_file,",
        "  transcript_title, inferred_date, chunk_index, and text",
        "- `basic_signals` — heuristic signal counts + full signals JSON per chunk",
        "- `marketing_insights` — one row per extraction record (+ full record JSON)"
        if insights else
        "- `marketing_insights` — (not built; no extraction output yet)",
        "- `marketing_assets` — reusable assets flattened to one row each "
        "(asset_type: right_fit_client_question, content_hook, youtube_angle, "
        "short_form_angle, email_angle, sales_page_angle, pain_point, objection, "
        "framework, story_or_example, quote, offer_positioning_note); "
        "FTS via `marketing_assets_fts` when FTS5 is available"
        if insights else
        "- `marketing_assets` — (not built; no extraction output yet)",
        "- `pipeline_runs` — build history",
        "" if has_fts else
        "\n## Limitation\n\nFTS5 was not available, so `chunks_fts` was not "
        "created. Searches fall back to SQL `LIKE`, which is slower and has "
        "no relevance ranking. Installing a Python build with FTS5-enabled "
        "SQLite removes this limitation.",
        "",
        "## Rebuilding",
        "",
        "This database is a disposable index. Rerun "
        "`python3 scripts/build_sqlite_database.py` to rebuild it from the "
        "JSONL files at any time.",
    ])
    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    write_text_report(reports_dir / "sqlite_database_report.md", report + "\n")

    print(f"Database built -> {db_path}")
    print(f"  {len(by_source)} transcripts, {len(chunks)} chunks, "
          f"{len(signals)} signal records, {len(insights)} insight records, "
          f"{len(asset_rows)} marketing assets. FTS5: {has_fts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
