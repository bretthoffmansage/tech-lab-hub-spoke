# Extraction Schema (v1.0)

This is the structured record an LLM (or a human) should produce for each
transcript chunk during the future **LLM Marketing Intelligence Extraction**
phase. The packets in `processed/extracted_insights/llm_packets.jsonl` are the
inputs; records following this schema are the outputs.

All fields that are lists return `[]` when nothing is present. All scalar
fields return `null` when unknown. Nothing may be invented: every extracted
item must be grounded in the chunk text.

## Identity & traceability fields (copied from the packet — never altered)

| Field | Type | Description |
|---|---|---|
| `record_id` | string | Unique ID for this extraction record (e.g. `{chunk_id}__extract_v1`) |
| `source_file` | string | Original raw transcript filename |
| `cleaned_file` | string | Path of the cleaned transcript |
| `transcript_title` | string | Title inferred from the filename |
| `inferred_date` | string\|null | `YYYY-MM-DD`, `YYYY-MM`, or `null` if unknown |
| `chunk_id` | string | The chunk this record was extracted from |
| `chunk_index` | int | Position of the chunk within its transcript |
| `source_text_excerpt` | string | Short verbatim excerpt (~300 chars) anchoring the record |

## Content intelligence fields

| Field | Type | Description |
|---|---|---|
| `core_topic` | string\|null | Single main topic of the chunk |
| `subtopics` | list[string] | Secondary topics |
| `client_pain_points` | list[string] | Pains, struggles, frustrations expressed or described |
| `client_desires` | list[string] | Outcomes and wants expressed or described |
| `client_objections` | list[string] | Objections, hesitations, pushback |
| `beliefs_challenged` | list[string] | Common beliefs the teaching pushes against |
| `mistakes_identified` | list[string] | Mistakes/misconceptions named in the text |
| `better_questions` | list[string] | Reframed or "better questions" posed in the text |
| `frameworks_or_models` | list[string] | Named or describable frameworks, models, processes |
| `stories_or_examples` | list[string] | Stories, case examples, demonstrations (1-line each) |
| `metaphors_or_phrases` | list[string] | Metaphors and recurring signature phrases, verbatim |
| `quotable_lines` | list[string] | Verbatim lines strong enough to quote directly |

## Marketing asset fields

| Field | Type | Description |
|---|---|---|
| `right_fit_client_questions` | list[string] | Qualifying questions a right-fit client would say yes to, grounded ONLY in chunk content |
| `content_hooks` | list[string] | Hook-ready lines or angles |
| `youtube_angles` | list[string] | Long-form video angles |
| `short_form_angles` | list[string] | Reels/Shorts/TikTok angles |
| `email_angles` | list[string] | Email subject/opening angles |
| `sales_page_angles` | list[string] | Sales page section angles |
| `offer_positioning_notes` | list[string] | Notes on how offers are framed, priced, positioned |
| `audience_segments` | list[string] | Who this content speaks to |
| `tags` | list[string] | Freeform lowercase tags for filtering |

## Scoring fields

| Field | Type | Description |
|---|---|---|
| `usefulness_score` | int 0–5 | See scale below |
| `confidence_score` | float 0–1 | Extractor's confidence in this record |

### usefulness_score scale

| Score | Meaning |
|---|---|
| 0 | Junk or housekeeping (mic checks, waiting for attendees, breakout logistics) |
| 1 | Low-value context (transitions, small talk, admin) |
| 2 | Usable background (context that supports other content) |
| 3 | Useful teaching (real instruction, real answers to client questions) |
| 4 | Strong content idea (clear hook, story, framework, or objection-handling worth repurposing) |
| 5 | Premium / highly reusable insight (signature framework, killer story, sales language that can anchor a campaign) |

## Versioning

The current schema version is `1.0`. Each packet carries
`extraction_schema_version` so future schema changes can coexist with old
extraction runs.
