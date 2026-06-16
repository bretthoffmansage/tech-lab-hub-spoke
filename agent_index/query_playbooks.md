# Query Playbooks

Concrete recipes for the requests this system supports. Each playbook: what
the user says → what to do → where the data lives.

> **Natural-language first:** all of these playbooks are handled
> automatically by the Streamlit app (`streamlit run app.py`) — the user just
> types the request. Programmatic callers can use
> `route_request(text, current_topic_key=...)` from
> `scripts/natural_language_router.py` to get the intent, resolved topic
> (with weak-coverage flags), asset type, and fallback options, then follow
> the matching playbook below. The CLI commands remain valid for scripted
> use.

## 1. User asks for topics

> "What topics can I make questions from?"

- Read `database/topic_index.json` (or run `python3 scripts/discover_topics.py`).
- Answer with the ranked topic list: display name, chunks/transcripts covered,
  strongest asset types.
- Offer: "Pick one and I'll build the full topic pack."

## 2. User picks a topic

> "Let's do founder bottleneck."

- Run `python3 scripts/build_topic_pack.py "founder bottleneck"` (or load the
  existing `database/topic_packs/founder_bottleneck_topic_pack.json`).
- Walk the pack top-down: summary → questions → pains → objections → hooks →
  angles → source excerpts → related topics.

## 3. User asks for questions from a topic

> "Give me questions from this topic."

- `python3 scripts/export_topic_assets.py "founder bottleneck" --asset-type questions`
- Or read `sections.right_fit_client_questions` from the pack JSON.
- Cite `source_file` + `chunk_id` per question.

## 4. User asks for hooks from a topic

> "Give me hooks."

- `python3 scripts/export_topic_assets.py "<topic>" --asset-type hooks`
- Or `sections.hooks_quotables` in the pack JSON.

## 5. User asks for objections from a topic

> "What objections show up around pricing?"

- `python3 scripts/export_topic_assets.py "high ticket" --asset-type objections`
- Or `sections.objections_pushback` in the pack JSON.

## 6. User asks for source excerpts

> "Show me where the transcripts actually talk about this."

- Use `source_excerpts` in the pack JSON (each has source_file,
  transcript_title, inferred_date, chunk_id, excerpt).
- For more context on one excerpt, look up its chunk_id in
  `database/transcript_chunks.jsonl`.
- For arbitrary phrases not tied to a topic:
  `python3 scripts/query_local_kb.py "<phrase>"`.

## 7. User asks for ALL useful information on a topic

> "Give me everything we have on right-fit clients."

- Build/load the topic pack (playbook 2) — that IS the everything view.
- Optionally also `python3 scripts/export_topic_assets.py "right fit client" --asset-type all`
  for a flat hand-off list.
- Do not collapse it into one "best answer"; the pack is intentionally broad.

## Always

- Lead with the mock-mode caveat while extraction records are placeholders.
- Keep every item traceable (source_file + chunk_id).
- Say "keyword match" when asked how things were found.
