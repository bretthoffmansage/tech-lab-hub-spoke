# Cleaning Rules

Cleaning is **conservative by design**. The goal is to make transcripts usable
for search and downstream extraction — not to summarize, paraphrase, or reduce
them. When in doubt, the cleaner keeps the text.

## What the cleaner REMOVES

| Pattern | Why | How |
|---|---|---|
| `WEBVTT` headers and VTT metadata lines | Caption format noise | Dropped if present |
| SRT sequence numbers (lines that are only a number) | Caption format noise | Dropped only when the file looks like SRT/VTT |
| Timestamp lines (`00:01:23 --> 00:01:25` style) | Unreliable, explicitly out of scope | Dropped |
| Inline caption tags (`<inaudible>`, `<crosstalk>`, `<laughter>`, `[inaudible]`, `[music]`, etc.) | Transcription artifacts that break sentences and pollute search | Replaced with a single space; occurrences are counted in the cleaning report |
| Repeated blank lines | Formatting noise | Collapsed to one blank line |
| Exact duplicate adjacent lines | Transcription glitch | Second copy dropped |
| Byte-order marks, carriage returns, stray control characters | Encoding noise | Normalized |
| Empty files and exact duplicate files (same content hash) | No value / double-counting | Skipped, listed in the cleaning report |

## What the cleaner PRESERVES (always)

- All meaningful teaching content
- Stories and examples
- Client questions (anything ending in `?` is never dropped)
- Objections and pushback language
- Frameworks, models, processes
- Offer language and sales language
- Metaphors and recurring company phrases
- Anything that could later become a hook, post, email, sales page
  section, or right-fit-client question

## Line-wrapping repair

The raw files contain long machine-wrapped lines. The cleaner joins consecutive
non-blank lines into paragraphs (blank lines remain paragraph separators).
It does **not** re-split sentences, reorder text, or merge across blank lines.

## What the cleaner does NOT do

- It does not summarize or shorten content
- It does not fix grammar or transcription word errors
  (a misheard word might still be searchable in context)
- It does not remove filler words (`um`, `like`, `you know`) — these can carry
  voice and are cheap to filter later; removing them now is irreversible
- It does not remove call housekeeping (greetings, "can you see my screen")
  in this version — housekeeping is instead *scored down* in the usefulness
  scoring layer, which is reversible. The keyword lists for this live in
  `config/pipeline_config.json` under `usefulness_keyword_rules.low_value_phrases`.
- It does not infer or invent speakers, timestamps, or structure

## Verification

`processed/reports/cleaning_report.md` shows per-file original vs. cleaned word
counts and the reduction percentage. Because cleaning only strips artifacts,
reductions should be small (typically under 5%). A large reduction is flagged
as a warning for human review.
