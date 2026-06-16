# Tech Lab Transcript Assistant — Conversational Interface

A full-screen chat app: ask natural-language questions about 5 years of Tech
Lab call transcripts, get answers grounded in retrieved source material, with
source excerpts under every answer. This replaced the earlier topic-pack
dashboard UI — no button grids, no rigid report sections.

## How to launch

```bash
export OPENAI_API_KEY="sk-..."            # optional but recommended
export TECH_LAB_DATA_PROVIDER=convex      # or local / auto (default)
streamlit run app.py
```

- **Data source** (sidebar): Convex when configured and populated, local
  files otherwise.
- **OpenAI** (sidebar): `configured (<model>)` or `not configured`. Without
  a key, the app runs in **retrieval-only mode** — it still searches and
  shows source excerpts, it just doesn't synthesize answers.
- Model: `OPENAI_MODEL` env var / Streamlit secret; default `gpt-4.1-mini`
  (defined in `scripts/openai_answerer.py`).

## What to ask

- *What topics can I ask about?* — plain ranked topic list
- *What do the transcripts say about webinar conversion?* — synthesized,
  grounded answer + sources
- *Give me right-fit-client questions from the OBIE material.* — polished
  questions grounded in retrieved chunks
- *Search for Zoom registration issues.* — retrieval + answer
- *Turn that into hooks.* / *Make it client-facing.* — follow-ups reuse the
  previous retrieval context
- *Show me more sources.* — additional excerpts for the same question

## How it works (honestly)

1. **Retrieval** (`scripts/retrieval_engine.py`): keyword search over
   Convex `transcriptChunks` (primary truth) and `marketingAssets`
   (secondary hints — current extraction is mock placeholders). Runs the
   query as-is plus a stopword-stripped variant; dedupes by chunk;
   no vector/semantic search.
2. **Answering** (`scripts/openai_answerer.py`): OpenAI gets ONLY the
   retrieved material and strict rules — no invented facts, no speaker
   names, no timestamps, say so when material is weak, end with "Sources
   used". Generated questions/hooks are grounded adaptations, never passed
   off as verbatim quotes.
3. **No-match handling**: if retrieval returns nothing, the app says so,
   lists the archive's real topics, and suggests better queries — OpenAI is
   not called with empty context.

## Source traceability

Every answer carries an expandable **Sources** panel: source_file,
transcript title, inferred date, and chunk_id for each retrieved chunk/hint.
No speakers, no timestamps — the source transcripts have neither.

## Suggested demo flow

1. *What topics can I ask about?*
2. *What do the transcripts say about webinar conversion?* — open the
   Sources panel ("every answer has receipts").
3. *Turn that into right-fit-client questions.* — follow-up context.
4. *Show me more sources.*
5. *What do we have about dog grooming?* — honest no-match.
