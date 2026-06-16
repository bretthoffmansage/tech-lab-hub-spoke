#!/usr/bin/env python3
"""Layer 6: Heuristic (non-LLM) signal extraction.

First-pass keyword/pattern analysis over database/transcript_chunks.jsonl.
These signals are a ROUGH first pass — they help prioritize chunks and seed
the later LLM extraction; they are not final classifications.

Writes database/basic_signals.jsonl and basic signal reports.
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, now_iso, read_jsonl, write_json, write_jsonl,
    write_text_report,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")
MAX_PER_CATEGORY = 12
MAX_SENTENCE_CHARS = 400


def split_sentences(text):
    sentences = []
    for para in text.split("\n\n"):
        for s in SENTENCE_SPLIT_RE.split(para.strip()):
            s = s.strip()
            if s and len(s) <= MAX_SENTENCE_CHARS:
                sentences.append(s)
    return sentences


def contains_phrase(sentence_lower, phrases):
    return [p for p in phrases if p in sentence_lower]


def score_usefulness(signals, rules, chunk_words):
    """Heuristic 0-5 usefulness score. Rough first pass only."""
    low_hits = signals["low_value_phrase_hits"]
    value_hits = (
        len(signals["teaching_points"]) * 2
        + len(signals["objections"]) * 2
        + len(signals["pain_points"]) * 2
        + len(signals["mistakes"]) * 2
        + len(signals["hooks"]) * 2
        + len(signals["questions"])
        + len(signals["strategic_term_counts"])
    )
    if chunk_words < 50:
        return 0
    if value_hits == 0:
        return 0 if low_hits >= 3 else 1
    density = value_hits / max(chunk_words / 250, 1)
    if low_hits > value_hits:
        return 1
    if density >= 8:
        return 5
    if density >= 5:
        return 4
    if density >= 3:
        return 3
    if density >= 1.5:
        return 2
    return 1


def analyze_chunk(record, extraction_rules, usefulness_rules):
    text = record["text"]
    sentences = split_sentences(text)
    lower_sentences = [(s, s.lower()) for s in sentences]

    questions = [s for s, _ in lower_sentences if s.endswith("?")][:MAX_PER_CATEGORY]

    def match_category(phrases):
        hits = []
        for s, sl in lower_sentences:
            if contains_phrase(sl, phrases):
                hits.append(s)
            if len(hits) >= MAX_PER_CATEGORY:
                break
        return hits

    teaching = match_category(extraction_rules["teaching_points"])
    objections = match_category(extraction_rules["objections"])
    pains = match_category(extraction_rules["pain_points"])
    mistakes = match_category(extraction_rules["mistakes"])
    hooks = match_category(extraction_rules["hooks"])

    text_lower = text.lower()
    term_counts = {}
    for term in extraction_rules["strategic_terms"]:
        count = len(re.findall(r"\b" + re.escape(term) + r"\b", text_lower))
        if count:
            term_counts[term] = count

    low_hits = sum(
        text_lower.count(p) for p in usefulness_rules.get("low_value_phrases", [])
    )

    signals = {
        "questions": questions,
        "teaching_points": teaching,
        "objections": objections,
        "pain_points": pains,
        "mistakes": mistakes,
        "hooks": hooks,
        "strategic_term_counts": term_counts,
        "low_value_phrase_hits": low_hits,
    }
    score = score_usefulness(signals, usefulness_rules, record["word_count"])

    return {
        "chunk_id": record["chunk_id"],
        "source_file": record["source_file"],
        "transcript_title": record["transcript_title"],
        "inferred_date": record["inferred_date"],
        "chunk_index": record["chunk_index"],
        "signals": signals,
        "potential_usefulness_score": score,
        "signal_pass": "heuristic_v1",
        "note": "Rough keyword-based first pass. Not a final classification.",
    }


def main():
    config = load_config()
    db_dir = PROJECT_ROOT / config["database_output_dir"]
    chunks_path = db_dir / "transcript_chunks.jsonl"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}. Run scripts/chunk_transcripts.py first.")
        return 1

    extraction_rules = config["extraction_keyword_rules"]
    usefulness_rules = config["usefulness_keyword_rules"]
    chunks = read_jsonl(chunks_path)
    print(f"Analyzing {len(chunks)} chunks ...")

    results = [analyze_chunk(c, extraction_rules, usefulness_rules) for c in chunks]
    write_jsonl(db_dir / "basic_signals.jsonl", results)

    score_dist = Counter(r["potential_usefulness_score"] for r in results)
    all_terms = Counter()
    for r in results:
        all_terms.update(r["signals"]["strategic_term_counts"])
    totals = {
        "questions": sum(len(r["signals"]["questions"]) for r in results),
        "teaching_points": sum(len(r["signals"]["teaching_points"]) for r in results),
        "objections": sum(len(r["signals"]["objections"]) for r in results),
        "pain_points": sum(len(r["signals"]["pain_points"]) for r in results),
        "mistakes": sum(len(r["signals"]["mistakes"]) for r in results),
        "hooks": sum(len(r["signals"]["hooks"]) for r in results),
    }
    top_chunks = sorted(
        results, key=lambda r: -r["potential_usefulness_score"]
    )[:20]

    report = {
        "generated_at": now_iso(),
        "chunks_analyzed": len(results),
        "signal_totals": totals,
        "usefulness_score_distribution": {str(k): score_dist.get(k, 0) for k in range(6)},
        "top_strategic_terms": all_terms.most_common(30),
        "top_chunks_by_usefulness": [
            {"chunk_id": r["chunk_id"], "score": r["potential_usefulness_score"],
             "title": r["transcript_title"]} for r in top_chunks
        ],
        "disclaimer": "Heuristic keyword pass only. Treat as a rough first pass.",
    }
    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    write_json(reports_dir / "basic_signal_report.json", report)

    lines = [
        "# Basic Signal Report (Heuristic First Pass)", "",
        f"Generated: {report['generated_at']}", "",
        "> These signals come from keyword rules only. They are a rough first",
        "> pass to prioritize chunks — not final classifications.", "",
        f"- Chunks analyzed: **{len(results)}**", "",
        "## Signal totals", "",
    ] + [f"- {k.replace('_', ' ').title()}: {v:,}" for k, v in totals.items()] + [
        "", "## Usefulness score distribution (0=junk … 5=premium)", "",
        "| Score | Chunks |", "|---|---:|",
    ] + [f"| {k} | {v} |" for k, v in report["usefulness_score_distribution"].items()] + [
        "", "## Top strategic terms", "",
        "| Term | Mentions |", "|---|---:|",
    ] + [f"| {t} | {c:,} |" for t, c in report["top_strategic_terms"]] + [
        "", "## Highest-potential chunks", "",
        "| Chunk | Score | Transcript |", "|---|---:|---|",
    ] + [f"| `{c['chunk_id']}` | {c['score']} | {c['title']} |"
         for c in report["top_chunks_by_usefulness"]]
    write_text_report(reports_dir / "basic_signal_report.md", "\n".join(lines) + "\n")

    print(f"Signals written -> {db_dir / 'basic_signals.jsonl'}")
    print(f"Score distribution: {dict(sorted(score_dist.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
