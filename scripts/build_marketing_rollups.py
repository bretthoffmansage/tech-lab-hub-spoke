#!/usr/bin/env python3
"""Build rollup reports from database/extracted_marketing_insights.jsonl.

Groups similar items with simple text normalization, prefers higher
usefulness/confidence, keeps full source traceability, and clearly marks
mock-mode outputs.

Writes per-asset markdown reports plus a combined rollup report
(md + json) to processed/reports/.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, read_jsonl, write_json, write_text_report,
)

INSIGHTS_PATH = PROJECT_ROOT / "database" / "extracted_marketing_insights.jsonl"
REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"

ROLLUPS = [
    ("right_fit_client_questions", "top_right_fit_client_questions.md",
     "Top Right-Fit Client Questions"),
    ("content_hooks", "top_content_hooks.md", "Top Content Hooks"),
    ("client_pain_points", "top_pain_points.md", "Top Client Pain Points"),
    ("client_objections", "top_objections.md", "Top Client Objections"),
    ("youtube_angles", "top_youtube_angles.md", "Top YouTube Angles"),
    ("short_form_angles", "top_short_form_angles.md", "Top Short-Form Angles"),
    ("email_angles", "top_email_angles.md", "Top Email Angles"),
    ("offer_positioning_notes", "top_offer_positioning_notes.md",
     "Top Offer Positioning Notes"),
]
TOP_N = 40
MIN_ITEM_WORDS = 3
GENERIC_ITEMS = {"yes", "no", "okay", "ok", "right", "thank you", "thanks"}


def normalize(text):
    """Normalization key for grouping near-duplicate items."""
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_worth_showing(text):
    norm = normalize(text)
    return len(norm.split()) >= MIN_ITEM_WORDS and norm not in GENERIC_ITEMS


def collect(records, field):
    """Group field items by normalized text. Returns sorted group list."""
    groups = defaultdict(lambda: {"texts": [], "sources": [], "best_score": -1,
                                  "best_conf": -1.0})
    for r in records:
        for item in r.get(field) or []:
            if not isinstance(item, str) or not is_worth_showing(item):
                continue
            g = groups[normalize(item)]
            g["texts"].append(item)
            g["sources"].append({
                "record_id": r["record_id"],
                "chunk_id": r["chunk_id"],
                "source_file": r["source_file"],
                "transcript_title": r["transcript_title"],
                "inferred_date": r.get("inferred_date"),
            })
            g["best_score"] = max(g["best_score"], r.get("usefulness_score") or 0)
            g["best_conf"] = max(g["best_conf"], r.get("confidence_score") or 0)
    result = []
    for key, g in groups.items():
        result.append({
            "text": g["texts"][0],
            "occurrences": len(g["texts"]),
            "best_usefulness_score": g["best_score"],
            "best_confidence_score": round(g["best_conf"], 3),
            "sources": g["sources"][:5],
            "normalized_key": key,
        })
    result.sort(key=lambda x: (-x["best_usefulness_score"], -x["occurrences"],
                               -x["best_confidence_score"]))
    return result


def render_rollup(title, field, items, mock_mode):
    lines = [f"# {title}", "", f"Generated: {now_iso()}", ""]
    if mock_mode:
        lines += ["> **MOCK MODE**: these items are verbatim sentences routed "
                  "by keyword heuristics, not polished marketing assets. "
                  "Re-run extraction with a real provider for usable copy.", ""]
    if not items:
        lines += [f"_No non-empty `{field}` items found in the current "
                  "extraction output._", ""]
    else:
        lines += [f"{len(items)} grouped item(s); showing top {min(TOP_N, len(items))}.",
                  ""]
        for i, item in enumerate(items[:TOP_N], 1):
            lines.append(f"## {i}. {item['text']}")
            lines.append("")
            lines.append(f"- Occurrences: {item['occurrences']} | "
                         f"usefulness: {item['best_usefulness_score']} | "
                         f"confidence: {item['best_confidence_score']}")
            for s in item["sources"]:
                lines.append(f"- Source: `{s['source_file']}` — "
                             f"{s['transcript_title']} "
                             f"({s['inferred_date']}) — `{s['chunk_id']}`")
            lines.append("")
    return "\n".join(lines) + "\n"


def main():
    if not INSIGHTS_PATH.exists():
        print(f"No insights file at {INSIGHTS_PATH}. "
              "Run scripts/extract_marketing_insights.py first.")
        return 1
    records = read_jsonl(INSIGHTS_PATH)
    if not records:
        print("Insights file is empty — nothing to roll up.")
        return 1

    mock_count = sum(1 for r in records if r.get("extraction_provider") == "mock")
    mock_mode = mock_count == len(records)

    summary = {
        "generated_at": now_iso(),
        "records": len(records),
        "mock_records": mock_count,
        "all_mock_mode": mock_mode,
        "rollups": {},
    }
    for field, filename, title in ROLLUPS:
        items = collect(records, field)
        write_text_report(REPORTS_DIR / filename,
                          render_rollup(title, field, items, mock_mode))
        summary["rollups"][field] = {
            "report": filename,
            "grouped_items": len(items),
            "total_occurrences": sum(i["occurrences"] for i in items),
            "top_items": [
                {"text": i["text"], "occurrences": i["occurrences"],
                 "best_usefulness_score": i["best_usefulness_score"]}
                for i in items[:5]
            ],
        }
        print(f"rollup: {field}: {len(items)} grouped items -> {filename}")

    write_json(REPORTS_DIR / "marketing_insights_rollup_report.json", summary)
    lines = [
        "# Marketing Insights Rollup Report", "",
        f"Generated: {summary['generated_at']}", "",
        f"- Records analyzed: **{len(records)}**",
        f"- Mock-mode records: {mock_count}"
        + (" (ALL outputs are mock placeholders)" if mock_mode else ""),
        "", "| Asset | Grouped items | Occurrences | Report |", "|---|---:|---:|---|",
    ]
    for field, info in summary["rollups"].items():
        lines.append(f"| {field} | {info['grouped_items']} | "
                     f"{info['total_occurrences']} | `{info['report']}` |")
    write_text_report(REPORTS_DIR / "marketing_insights_rollup_report.md",
                      "\n".join(lines) + "\n")
    print(f"Rollup summary -> {REPORTS_DIR / 'marketing_insights_rollup_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
