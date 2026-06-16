# Agent Navigation Guide

How an agent (or a person) should navigate this knowledge base. Plain
language, no special tooling required — everything is JSON/JSONL/markdown
plus a few Python scripts.

## Preferred entry point: the natural-language app

For humans, the intended interface is `streamlit run app.py` — type normal
questions ("what topics do we have?", "give me everything on right-fit
clients", "now give me hooks", "export questions"). For agents, the same
routing logic is importable:

```python
from natural_language_router import route_request
route_request("give me hooks from webinar conversion")
# -> {"intent": "get_hooks", "topic": {"topic_key": "webinar_event_conversion", ...}, ...}
```

The router is transparent keyword matching with a `reason` field on every
result, honest weak-topic flags, and a no-match path that returns fallback
topic options instead of guessing. The sections below describe the
underlying files and scripts the app sits on.

## The system in one paragraph

Raw Tech Lab call transcripts (no speakers, no timestamps) were cleaned,
chunked into 846 traceable pieces, scanned for marketing signals, and
processed into structured marketing-intelligence records. A topic layer sits
on top: discover topics, build a "topic pack" of everything useful about one
topic, or export a clean asset list. Current extraction records are MOCK
placeholders — see `agent_manifest.json` → `mock_mode_warning`.

## How to answer "What topics can I make questions from?"

1. Read `database/topic_index.json` (regenerate with
   `python3 scripts/discover_topics.py` if missing or stale).
2. Present the topics sorted by `matching_chunks`, with `display_name`,
   chunk/source counts, and `top_asset_types`.
3. Be honest that counts come from keyword matching, not semantic search.

## How to build a topic pack

1. Check `database/topic_packs/<topic_key>_topic_pack.json` — it may already
   exist.
2. If not: `python3 scripts/build_topic_pack.py "<topic phrase>"`.
   Any phrase works; configured topics (see
   `config/topic_pack_config.json`) match better via aliases.
3. The pack JSON has `sections` (questions, pains, desires, objections,
   beliefs/mistakes, hooks, four angle types, offer notes), `source_excerpts`,
   `related_topics`, and `stats`. The markdown twin in
   `processed/reports/topic_packs/` is the human-friendly version.

## How to export assets

`python3 scripts/export_topic_assets.py "<topic>" --asset-type questions`
(also: hooks, pain_points, objections, youtube_angles, short_form_angles,
email_angles, offer_notes, quotes, all). Output lands in
`exports/topic_assets/` as a numbered markdown list plus JSON.

## How to cite sources

Every item carries `source_file` and `chunk_id` (plus `transcript_title`,
`inferred_date`, `chunk_index`). Cite as:

> "…quoted text…" — `Tech-Lab-July-2025---Part-1.txt`, chunk
> `tech-lab-july-2025-part-1__chunk_0010`

To show the full surrounding text, look the chunk_id up in
`database/transcript_chunks.jsonl` or
`processed/transcript_chunks/<transcript>/chunk_NNNN.md`.

## What NOT to do

- Never modify raw transcript `.txt` files or hand-edit JSONL outputs.
- Never attribute a quote to a named speaker or a timestamp — the source has
  neither.
- Never present mock-extraction questions/hooks as final marketing copy.
- Never present a generated/reworded question as a verbatim transcript quote.
- Never invent source metadata; if `inferred_date` is "unknown", say unknown.
- See `safety_rules.md` for the full list.
