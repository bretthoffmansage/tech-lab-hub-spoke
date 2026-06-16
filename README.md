# Tech Lab Transcript Knowledge Base

A local, rerunnable pipeline that turns this folder of raw Tech Lab call
transcripts into a searchable content-intelligence knowledge base: cleaned
transcripts, retrieval-ready chunks, heuristic marketing signals, LLM-ready
extraction packets, and a local SQLite full-text-search database.

**Everything runs locally with the Python standard library. No paid APIs.
Raw transcript files are never modified.**

## What it does

- Inventories every transcript (size, format, inferred date, duplicates)
- Conservatively cleans transcripts (removes caption artifacts like
  `<inaudible>`, repairs line wrapping — never summarizes or rewrites)
- Splits transcripts into ~1000-word overlapping chunks with full source
  traceability
- Runs a heuristic first-pass scan for questions, teaching points, objections,
  pain points, mistakes, hooks, and strategic terms
- Builds LLM-ready extraction packets for a future marketing-intelligence
  extraction phase
- Builds a local SQLite database with full-text search
- Provides a command-line search tool

## What it does NOT do (yet)

- No LLM extraction (packets are prepared, not processed)
- No vector/semantic search (see `docs/future_database_plan.md`)
- No web app, chatbot, or answer generation
- No speaker identification or timestamps — the source transcripts have
  neither, and nothing here depends on them

## Folder structure

```
.                               # raw transcript .txt files live here (untouched)
├── raw_transcripts/            # alternative source location (optional)
├── config/pipeline_config.json # all tunable settings
├── scripts/                    # the pipeline (see below)
├── docs/                       # system docs, cleaning rules, schema, db plan
├── processed/
│   ├── cleaned_transcripts/    # cleaned .md files with frontmatter
│   ├── transcript_chunks/      # one folder of chunk files per transcript
│   ├── extracted_insights/     # llm_packets.jsonl + prompt template
│   └── reports/                # human-readable reports for every stage
└── database/
    ├── transcript_chunks.jsonl     # durable chunk records (source of truth)
    ├── basic_signals.jsonl         # heuristic signals per chunk
    └── tech_lab_knowledge_base.sqlite  # disposable search index
```

## Run the full pipeline

```bash
python3 scripts/run_pipeline.py
```

Runs all six stages in order and writes
`processed/reports/pipeline_run_report.md`. Safe to rerun anytime — all
outputs are regenerated; raw files are read-only to the pipeline.

Individual stages can also be run directly, in this order:

```bash
python3 scripts/transcript_inventory.py
python3 scripts/normalize_transcripts.py
python3 scripts/chunk_transcripts.py
python3 scripts/extract_basic_signals.py
python3 scripts/build_llm_extraction_packets.py
python3 scripts/build_sqlite_database.py
```

## Search the knowledge base

```bash
python3 scripts/query_local_kb.py "founder bottleneck"
python3 scripts/query_local_kb.py "right fit client" --limit 10
python3 scripts/query_local_kb.py "high ticket offer"
```

Returns the top matching chunks with `source_file`, `transcript_title`,
`inferred_date`, `chunk_id`, and an excerpt. Retrieval only — it finds source
material; it does not generate answers.

## Inspecting the outputs

| Want to see… | Look at |
|---|---|
| What source files exist, dates, duplicates | `processed/reports/transcript_inventory.md` |
| How much cleaning changed each file | `processed/reports/cleaning_report.md` |
| A cleaned transcript | any file in `processed/cleaned_transcripts/` |
| Chunk sizes and counts | `processed/reports/chunking_report.md` |
| A specific chunk | `processed/transcript_chunks/<transcript>/chunk_0000.md` |
| Heuristic signal overview, top terms, best chunks | `processed/reports/basic_signal_report.md` |
| The raw chunk records | `database/transcript_chunks.jsonl` (one JSON per line) |

## Preparing for the LLM extraction phase

`processed/extracted_insights/llm_packets.jsonl` contains one self-contained
packet per chunk (text + heuristic signals + schema version).
`processed/extracted_insights/llm_extraction_prompt_template.md` is the prompt
to use, and `docs/extraction_schema.md` defines the output schema. The next
package ("LLM Marketing Intelligence Extraction v1") will process these
packets into `database/extracted_marketing_insights.jsonl`.

## Configuration

Edit `config/pipeline_config.json` to change chunk sizes, keyword rules,
source directory, or skip behavior. Defaults: 1000-word chunks, 150-word
overlap, 250-word minimum. The pipeline reads transcripts from
`raw_transcripts/` if files are there, otherwise from the project root
(`"transcript_source_dir": "auto"`).

## Marketing Intelligence Extraction (second-stage pipeline)

This stage processes the 846 LLM packets into structured marketing
intelligence records — right-fit-client questions, content hooks, pain
points, objections, frameworks, stories, quotable lines, content angles
(YouTube/short-form/email/sales page), offer positioning, audience
segments, and tags — written to `database/extracted_marketing_insights.jsonl`.

It is provider-agnostic: **mock** (default — no API, no keys, standard
library only), **anthropic**, or **openai**. Mock mode produces conservative
placeholder records (verbatim sentences routed by keyword signals) so the
whole pipeline — schema, resume, validation, rollups, search, SQLite — can be
exercised before spending anything on a real LLM.

### Run a small mock test

```bash
python3 scripts/run_marketing_extraction_pipeline.py --provider mock --max-packets 10
```

### Run the full mock extraction

```bash
python3 scripts/run_marketing_extraction_pipeline.py --provider mock
```

Resume is on by default: already-extracted chunk_ids are skipped, so reruns
only process what's missing. Use `--overwrite` to deliberately rebuild the
output file from scratch — it is never overwritten implicitly.

### Configure a real provider later

1. Install the package: `pip install anthropic` (or `pip install openai`)
2. Export the key: `export ANTHROPIC_API_KEY=...` (or `OPENAI_API_KEY=...`)
3. Run: `python3 scripts/run_marketing_extraction_pipeline.py --provider anthropic --max-packets 25`

Provider, model, temperature, token limits, batch size, and the
`min_usefulness_to_keep` filter live in `config/llm_extraction_config.json`.
If the package or key is missing, the run stops with a clear message before
touching any output. (Hardened rate-limiting/retry/cost controls are the next
package: Real Provider Extraction Adapter v1.)

### Outputs and how to check them

| What | Where |
|---|---|
| Extraction records (JSONL, source of truth) | `database/extracted_marketing_insights.jsonl` |
| Extraction run report | `processed/reports/marketing_extraction_report.md` |
| Failures (if any) | `processed/reports/marketing_extraction_failures.jsonl` |
| Validation | `python3 scripts/validate_marketing_insights.py` → `processed/reports/marketing_insights_validation_report.md` |
| Rollups (inspect these first) | `processed/reports/marketing_insights_rollup_report.md`, then `top_right_fit_client_questions.md`, `top_content_hooks.md`, `top_pain_points.md`, `top_objections.md`, `top_*_angles.md`, `top_offer_positioning_notes.md` |
| SQLite tables | `marketing_insights`, `marketing_assets` (+ `marketing_assets_fts`) in `database/tech_lab_knowledge_base.sqlite` |

### Search extracted insights

```bash
python3 scripts/query_marketing_insights.py "right fit client"
python3 scripts/query_marketing_insights.py "offer positioning" --limit 10
python3 scripts/query_marketing_insights.py "bottleneck" --asset-type content_hooks
```

### Source traceability

Every record and every flattened asset carries `source_file`, `cleaned_file`,
`transcript_title`, `inferred_date`, `chunk_id`, and `chunk_index`, plus a
verbatim `source_text_excerpt`. Any insight can be traced to the exact raw
transcript and chunk it came from; traceability fields are validated to match
the originating packet exactly.

## Hub & Spoke Answer Builder

A Streamlit app for manually answering prewritten tech SEO/AEO questions organized as hubs and spokes. **No LLM** — answers are typed by users and saved directly to **Convex** (the sole source of truth).

```bash
pip install -r requirements.txt
npx convex dev --once
python3 scripts/seed_hub_spoke_questions.py
streamlit run app.py
```

Set `CONVEX_URL` in `.env.local` (local) or Streamlit Cloud secrets (hosted). Full guide: [hub_spoke_answer_app.md](docs/hub_spoke_answer_app.md).

**Answer Questions mode** uses hub-level locking so multiple people can work at once without being assigned the same hub. Locks expire after 5 minutes of inactivity if a tab is closed without exiting.

## Tech Lab Transcript Assistant (the demo experience)

A conversational chat app over the archive — ask questions in plain English,
get answers grounded in retrieved transcript chunks, with source excerpts
under every answer:

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."          # optional; without it the app runs
export TECH_LAB_DATA_PROVIDER=convex    # retrieval-only (sources, no synthesis)
streamlit run app.py
```

Ask things like *"What do the transcripts say about webinar conversion?"*,
*"Give me right-fit-client questions from the OBIE material"*, then follow
up with *"turn that into hooks"* or *"show me more sources"*. Retrieval is
keyword search over Convex-hosted chunks (local fallback); answers come from
OpenAI grounded strictly in the retrieved material — it refuses to invent
answers for topics the archive doesn't cover. Guide:
[natural_language_demo_interface.md](docs/natural_language_demo_interface.md).

### Hosted data via Convex

The app prefers Convex-hosted data when `CONVEX_URL` is configured (it is,
via `.env.local`) and falls back to local files automatically. Upload/refresh
hosted data with `python3 scripts/upload_to_convex.py`, verify with
`python3 scripts/verify_convex_upload.py`, and force a source with
`TECH_LAB_DATA_PROVIDER=convex|local|auto`. The sidebar shows which source is
active. Full guide incl. Streamlit Cloud deployment:
[convex_hosted_demo.md](docs/convex_hosted_demo.md).

## Boss Demo Topic Pack Workflow

The demo layer on top of the extraction outputs: discover topics → build a
topic pack → export clean asset lists.

```bash
python3 scripts/discover_topics.py                       # "what topics can I make questions from?"
python3 scripts/build_topic_pack.py "founder bottleneck" # full topic pack (md + json)
python3 scripts/export_topic_assets.py "right fit client" --asset-type questions
python3 scripts/run_boss_demo_pack.py                    # discovery + 5 packs + exports in one go
```

- **Topic packs** land in `processed/reports/topic_packs/*.md` (human) and
  `database/topic_packs/*.json` (machine). Each pack collects questions, pain
  points, desires, objections, beliefs/mistakes, hooks, content angles, offer
  notes, and source-backed excerpts — broad material, not one best answer.
- **Exports** land in `exports/topic_assets/` as numbered hand-off lists
  (asset types: questions, hooks, pain_points, objections, youtube_angles,
  short_form_angles, email_angles, offer_notes, quotes, all).
- **Topics** are configured in `config/topic_pack_config.json` (easy to edit;
  any unconfigured phrase also works as an ad-hoc topic).
- **Agent index** lives in `agent_index/` — `agent_manifest.json`
  (machine-readable system map), `agent_navigation.md`, `query_playbooks.md`,
  and `safety_rules.md`.
- **Inspect first:** `processed/reports/topic_discovery_report.md`, then a
  pack like `processed/reports/topic_packs/right_fit_client_topic_pack.md`,
  and `docs/boss_demo_guide.md` for the demo script.
- **Current limitation:** extraction records are still mock placeholders, so
  pack items are verbatim transcript sentences, not polished marketing copy.
  Every report is labeled accordingly; a real-provider extraction run
  upgrades the same workflow in place.

## Known limitations

- **No speakers, no timestamps** — by design; the source data has neither.
- **Heuristic signals are rough.** Keyword matching catches phrasing, not
  meaning. Treat `basic_signals.jsonl` as a prioritization aid, not truth.
- **Dates come from filenames only.** Files like `Breakouts.txt` have
  `inferred_date: unknown`. `Apr-23`-style names are assumed to mean 20xx.
- **Keyword search only.** "Founder doing everything" won't match a chunk
  that says "I can't let go of anything" until vector search is added.
- **Some transcripts contain transcription errors** (e.g. misheard song
  lyrics during pre-call waiting music). Cleaning preserves them; usefulness
  scoring is what filters them out downstream.
- Exact-duplicate files and empty files are skipped (listed in the cleaning
  report).

## Recommended next steps

1. **LLM Marketing Intelligence Extraction v1** — process
   `llm_packets.jsonl` into `database/extracted_marketing_insights.jsonl`
   (right-fit-client questions, hooks, pain points, objections, frameworks,
   stories, content angles, offer positioning, reusable sales language).
2. Local vector search (ChromaDB or LanceDB) for semantic queries —
   see `docs/future_database_plan.md`.
3. A simple internal query interface once 1–2 are in place.
