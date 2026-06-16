# Future Database Plan

The pipeline is built in layers so the storage can grow with the project
without redoing earlier work. JSONL files are the durable source of truth at
every stage; every database below can be rebuilt from them at any time.

## Stage 1 (now): JSONL files — durable pipeline outputs

- `database/transcript_chunks.jsonl` — every chunk with full text and traceability
- `database/basic_signals.jsonl` — heuristic signals per chunk
- `processed/extracted_insights/llm_packets.jsonl` — LLM-ready inputs
- Future: `database/extracted_marketing_insights.jsonl` — structured LLM outputs

Why JSONL: human-inspectable, diff-able, append-friendly, no schema lock-in,
readable by every tool that will ever exist.

## Stage 2 (now): SQLite — local structured search

`database/tech_lab_knowledge_base.sqlite`, built by
`scripts/build_sqlite_database.py` using only the Python standard library.

- Tables: `transcripts`, `chunks`, `basic_signals`, `pipeline_runs`
- Full-text search via **FTS5** when the local SQLite build supports it
  (macOS system Python does); otherwise it falls back to `LIKE` search and the
  report documents the limitation.
- Good for: keyword/phrase search, filtering by transcript/date, joining
  signals to chunks.

## Stage 3 (next): Local vector search — ChromaDB or LanceDB

When semantic search is wanted ("find the part where he talks about founders
doing everything themselves" without exact keywords):

- **ChromaDB** (`pip install chromadb`) — simplest path; embed each chunk from
  `transcript_chunks.jsonl`, store `chunk_id` + `source_file` as metadata.
- **LanceDB** (`pip install lancedb`) — columnar, fast, good if the archive
  grows large.
- Embeddings can be local (e.g. `sentence-transformers`) to stay free, or an
  API embedding model for higher quality.
- Keep `chunk_id` as the join key back to SQLite/JSONL so vector hits remain
  source-traceable.

## Stage 4 (later, only if productized): Postgres + pgvector

If the company wants a multi-user production app (internal chatbot, client
portal):

- Postgres holds chunks, insights, and embeddings (`pgvector` extension)
- One database serves keyword search, structured filters, and vector search
- Migration is mechanical: load the same JSONL files into Postgres tables

## Rule of thumb

Never make a database the source of truth. The JSONL outputs are. Databases
are disposable indexes built from them.
