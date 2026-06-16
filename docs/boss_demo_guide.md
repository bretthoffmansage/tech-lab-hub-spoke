# Boss Demo Guide

A simple script for demoing the Tech Lab Transcript Knowledge Base
proof-of-concept.

## What this prototype proves

- **5 years of call transcripts are now structured and searchable.** 66 raw
  files → 846 traceable chunks → structured marketing-intelligence records →
  topic packs on command.
- **The workflow works end-to-end**: ask "what topics do we have?", pick one,
  get a full pack of questions, hooks, pain points, objections, angles, and
  source-backed excerpts in seconds — all traceable to the exact transcript
  and chunk.
- **Nothing was lost or altered**: raw transcripts are untouched; every item
  cites its source.
- **It's cheap to rerun**: the entire pipeline is local, standard-library
  Python, and re-runnable in seconds.

## What it does NOT prove yet

- **Content quality.** The current extraction layer is a mock/placeholder
  pass: items are verbatim sentences routed by keyword rules, not rewritten
  marketing copy. Questions read like transcript lines, not polished
  qualifying questions.
- **Semantic understanding.** Topic matching is keyword-based. "Founder
  bottleneck" finds chunks that use those words, not every chunk *about* the
  concept.
- No chatbot, no web UI — by design, this stage is workflow proof.

## How to say what it does in plain English

> "We took five years of Tech Lab recordings, broke them into about 850
> traceable pieces, and built a system that can pull everything we've ever
> said about a topic — questions, pain points, objections, hooks, content
> angles — with a receipt pointing back to the exact transcript. Right now
> it's running on a placeholder extraction so we could prove the plumbing;
> the next step swaps in a real LLM pass so the questions and hooks come out
> polished instead of raw."

## How to explain the mock limitation if asked

> "Everything you see is real transcript content — nothing is invented. But
> the 'questions' and 'hooks' are currently raw sentences the system found,
> not rewritten marketing assets. The real LLM pass rewrites each chunk into
> clean questions, hooks, and summaries — same workflow, much better output.
> We held that back so we could validate the system before spending on it."

## How real LLM extraction improves the output

| Today (mock) | After real extraction |
|---|---|
| Verbatim transcript sentences | Polished, reusable marketing assets |
| Question = any question found in text | Right-fit-client questions a prospect recognizes themselves in |
| Topic summary = match statistics | Plain-English summary of what the archive teaches |
| Empty fields (beliefs, metaphors, segments) | Filled where the content supports them |

## Best commands to run

```bash
python3 scripts/discover_topics.py                                  # list topics
python3 scripts/build_topic_pack.py "founder bottleneck"            # full pack
python3 scripts/export_topic_assets.py "right fit client" --asset-type questions
python3 scripts/run_boss_demo_pack.py                               # everything at once
```

## Best first topics to test

1. **right fit client** — richest topic in the archive (OBIE sessions are
   full of it)
2. **founder bottleneck** — relatable, shows delegation/automation content
3. **offer positioning** — strong offer-creation material
4. **objections** — shows pushback handling across years
5. **content strategy** — broad coverage, good for angle demos

## Suggested demo flow

1. Open `processed/reports/topic_discovery_report.md` — "here's everything
   the archive can talk about, ranked."
2. Pick a topic ("founder bottleneck" or "right fit client").
3. Run `python3 scripts/build_topic_pack.py "right fit client"` live — it
   takes ~2 seconds.
4. Open the pack and show the **right-fit-client questions** section.
5. Scroll to **hooks and quotable lines**.
6. Show **source-backed excerpts** — "every line has a receipt."
7. Run one export:
   `python3 scripts/export_topic_assets.py "right fit client" --asset-type questions`
   — "and here's the clean hand-off list."
8. Close: "this same workflow runs for any topic in the archive — and when we
   turn on the real LLM pass, the same buttons produce polished copy."
