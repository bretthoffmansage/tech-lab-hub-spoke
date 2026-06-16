# Marketing Extraction Output Schema — v1 (schema version "1.0")

One JSON object per processed chunk, written as one line of
`database/extracted_marketing_insights.jsonl`. This schema extends
`docs/extraction_schema.md` with provider and QA fields.

## Identity and traceability (copied from the packet — never altered)

| Field | Type | Description |
|---|---|---|
| `record_id` | string | `"<chunk_id>__extract_v1"` — unique per record |
| `source_file` | string | Original raw transcript filename |
| `cleaned_file` | string | Path of the cleaned transcript |
| `transcript_title` | string | Title inferred from the filename |
| `inferred_date` | string\|null | `YYYY-MM-DD`, `YYYY-MM`, `"unknown"`, or null |
| `chunk_id` | string | The chunk this record was extracted from |
| `chunk_index` | int | Position of the chunk within its transcript |
| `extraction_schema_version` | string | `"1.0"` |
| `source_text_excerpt` | string | Short verbatim excerpt (~300 chars) anchoring the extraction |

## Content intelligence (all `list[string]` unless noted)

| Field | Description |
|---|---|
| `core_topic` (string\|null) | Single main topic of the chunk |
| `subtopics` | Secondary topics |
| `client_pain_points` | Pains, struggles, frustrations expressed or described |
| `client_desires` | Outcomes and wants expressed or described |
| `client_objections` | Objections, hesitations, pushback |
| `beliefs_challenged` | Common beliefs the teaching pushes against |
| `mistakes_identified` | Mistakes/misconceptions named in the text |
| `better_questions` | Reframed or "better question" formulations posed in the text |
| `frameworks_or_models` | Named or describable frameworks, models, processes |
| `stories_or_examples` | Stories, case examples, demonstrations (1-line each) |
| `metaphors_or_phrases` | Metaphors and recurring signature phrases, verbatim |
| `quotable_lines` | Verbatim/near-verbatim lines strong enough to quote |

## Marketing assets (all `list[string]`)

| Field | Description |
|---|---|
| `right_fit_client_questions` | Questions a strong-fit prospect would recognize themselves in |
| `content_hooks` | Concise lines usable as social/video/email openers |
| `youtube_angles` | Long-form video angles |
| `short_form_angles` | Reels/Shorts/TikTok angles |
| `email_angles` | Email subject/opening angles |
| `sales_page_angles` | Sales page section angles |
| `offer_positioning_notes` | How offers are framed, priced, differentiated |
| `audience_segments` | Who the content addresses — inferred only from content |
| `tags` | Lowercase freeform tags for search and filtering |

## Scoring and QA

| Field | Type | Description |
|---|---|---|
| `usefulness_score` | int 0–5 | Marketing/content reusability (scale in `docs/extraction_schema.md`) |
| `confidence_score` | float 0–1 | Confidence in extraction quality and grounding |
| `grounding_notes` | string\|null | How the extraction is grounded in the chunk |
| `extraction_warnings` | list[string] | Caveats; `[]` if none |
| `extraction_provider` | string | `"mock"`, `"anthropic"`, or `"openai"` |
| `extraction_model` | string | Model identifier (`"mock"` in mock mode) |
| `extracted_at` | string | UTC ISO timestamp of the extraction run (run metadata, not transcript time) |

## Rules

- List fields MUST be JSON arrays (possibly empty). Scalar unknowns MUST be `null`.
- `usefulness_score` must be an integer 0–5; `confidence_score` a float 0–1.
- `source_text_excerpt` must come from the chunk text.
- No markdown in JSON string fields unless it appears in the source text.
- No timestamp fields and no speaker fields of any kind (the source has neither).
- Every record must carry `chunk_id` and `source_file` so any downstream use
  can cite the exact transcript and chunk it came from.

`scripts/validate_marketing_insights.py` enforces these rules.
