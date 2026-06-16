# Tech Lab Transcript Knowledge Base — System Overview

This project converts a folder of raw Tech Lab call transcripts into a durable,
searchable, content-intelligence knowledge base. Everything runs locally with
the Python standard library. No paid APIs are required for any step in this
package.

## The pipeline

```
Raw transcripts (plain .txt files, no speakers, no timestamps)
        │
        ▼
1. Inventory (scripts/transcript_inventory.py)
   What files exist, how big, what format, likely dates, duplicates
        │
        ▼
2. Conservative cleaning & normalization (scripts/normalize_transcripts.py)
   Remove caption/transcription noise, repair line wrapping,
   preserve all meaningful wording → processed/cleaned_transcripts/
        │
        ▼
3. Chunking (scripts/chunk_transcripts.py)
   Split into ~1000-word retrieval-friendly chunks with 150-word overlap
   → processed/transcript_chunks/ and database/transcript_chunks.jsonl
        │
        ▼
4. Basic signal extraction (scripts/extract_basic_signals.py)
   Heuristic, keyword-based first pass: questions, teaching points,
   objections, pain points, mistakes, hooks, strategic terms
   → database/basic_signals.jsonl
        │
        ▼
5. LLM-ready extraction packets (scripts/build_llm_extraction_packets.py)
   Self-contained JSONL packets (chunk text + signals + schema version)
   ready to send to an LLM later → processed/extracted_insights/llm_packets.jsonl
        │
        ▼
6. Local database (scripts/build_sqlite_database.py)
   SQLite with full-text search (FTS5 when available)
   → database/tech_lab_knowledge_base.sqlite
        │
        ▼
7. Local query (scripts/query_local_kb.py)
   Command-line keyword/phrase search returning source-traced chunks
        │
        ▼
FUTURE: Vector search (ChromaDB / LanceDB) → see docs/future_database_plan.md
        │
        ▼
FUTURE: User-facing query interface (chatbot / internal search app)
```

## Design principles

- **Raw files are never touched.** All outputs go to new folders
  (`processed/`, `database/`).
- **No speaker labels, no timestamps.** The transcripts don't have reliable
  versions of either, so nothing in the pipeline depends on them.
- **Cleaning is conservative.** It makes text readable and searchable; it never
  summarizes or rewrites. Original wording is preserved because that wording is
  the marketing asset.
- **Everything is rerunnable.** Each script can be run independently or via
  `scripts/run_pipeline.py`. Outputs are deterministically regenerated.
- **JSONL is the durable interchange format.** SQLite is a convenience layer
  built from the JSONL files and can always be rebuilt.
- **Source traceability everywhere.** Every chunk, signal record, and packet
  carries `source_file` and `chunk_id` so any future LLM answer can cite the
  exact transcript it came from.

## What this package deliberately does NOT do

- No web app, no chatbot UI
- No LLM calls (it *prepares* for them — see `processed/extracted_insights/`)
- No vector embeddings yet
- No speaker diarization
- No paid or external APIs

## Key files to know

| File | What it is |
|---|---|
| `config/pipeline_config.json` | All tunable settings |
| `processed/reports/transcript_inventory.md` | Human-readable inventory of source files |
| `processed/cleaned_transcripts/*.md` | Cleaned transcripts with frontmatter |
| `database/transcript_chunks.jsonl` | All chunks, one JSON record per line |
| `database/basic_signals.jsonl` | Heuristic signals per chunk |
| `processed/extracted_insights/llm_packets.jsonl` | LLM-ready extraction packets |
| `database/tech_lab_knowledge_base.sqlite` | Local searchable database |
