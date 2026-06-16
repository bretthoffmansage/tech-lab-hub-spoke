#!/usr/bin/env python3
"""Topic discovery — answers "What topics can I make questions from?"

Counts keyword-alias matches for every configured topic across the extracted
marketing insights (when present), basic signals, and transcript chunks.
This is keyword matching, not semantic understanding — the reports say so.

Writes:
  processed/reports/topic_discovery_report.{md,json}
  database/topic_index.json
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, write_json, write_text_report,
)
from topic_lib import (  # noqa: E402
    INSIGHTS_PATH, SIGNALS_PATH, CHUNKS_PATH, TOPIC_INDEX_PATH,
    load_topic_config, load_insights, load_chunks, topic_regex,
    record_matches, mock_mode_banner,
)

REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"

# count individual asset items matching the topic, by field
ASSET_FIELDS = [
    "right_fit_client_questions", "content_hooks", "client_pain_points",
    "client_objections", "quotable_lines", "youtube_angles",
    "short_form_angles", "email_angles", "offer_positioning_notes",
    "better_questions", "frameworks_or_models", "stories_or_examples",
]


def main():
    config = load_topic_config()
    insights, extraction_mode = load_insights(config)
    chunks = load_chunks()
    if not chunks and not insights:
        print("No data found. Run python3 scripts/run_pipeline.py first.")
        return 1

    data_sources = []
    if INSIGHTS_PATH.exists():
        data_sources.append(str(INSIGHTS_PATH.relative_to(PROJECT_ROOT)))
    if SIGNALS_PATH.exists():
        data_sources.append(str(SIGNALS_PATH.relative_to(PROJECT_ROOT)))
    if CHUNKS_PATH.exists():
        data_sources.append(str(CHUNKS_PATH.relative_to(PROJECT_ROOT)))

    topics = config["topic_aliases"]
    regexes = {key: topic_regex(t["aliases"]) for key, t in topics.items()}

    # per-chunk topic hits (also powers co-occurrence)
    chunk_topic_hits = {key: [] for key in topics}
    for c in chunks:
        for key, regex in regexes.items():
            hits = len(regex.findall(c["text"]))
            if hits:
                chunk_topic_hits[key].append((hits, c))

    print(f"Scanning {len(insights)} insight records and {len(chunks)} chunks "
          f"for {len(topics)} configured topics ...")

    index = {}
    for key, topic in topics.items():
        regex = regexes[key]
        matched_chunks = chunk_topic_hits[key]
        chunk_ids = {c["chunk_id"] for _, c in matched_chunks}
        source_files = {c["source_file"] for _, c in matched_chunks}

        matched_records = [r for r in insights if record_matches(r, regex)]
        asset_counts = Counter()
        for r in matched_records:
            for field in ASSET_FIELDS:
                for item in r.get(field) or []:
                    if isinstance(item, str) and regex.search(item):
                        asset_counts[field] += 1

        # co-occurring topics: which other topics appear in this topic's chunks
        co = Counter()
        for _, c in matched_chunks:
            for other_key, other_regex in regexes.items():
                if other_key != key and other_regex.search(c["text"]):
                    co[other_key] += 1

        top_chunks = sorted(matched_chunks, key=lambda x: -x[0])[:3]
        if matched_records and matched_chunks:
            basis = "mock extraction + raw chunks" if extraction_mode == "mock" \
                else "extraction records + raw chunks"
        elif matched_records:
            basis = "extraction records only"
        else:
            basis = "raw chunks only (keyword match)"

        index[key] = {
            "display_name": topic["display_name"],
            "aliases": topic["aliases"],
            "matching_chunks": len(chunk_ids),
            "matching_source_files": len(source_files),
            "matching_insight_records": len(matched_records),
            "matching_assets_total": sum(asset_counts.values()),
            "top_asset_types": asset_counts.most_common(5),
            "data_basis": basis,
            "co_occurring_topics": [
                {"topic_key": k, "display_name": topics[k]["display_name"],
                 "shared_chunks": v} for k, v in co.most_common(5)
            ],
            "sample_sources": [
                {"transcript_title": c["transcript_title"],
                 "source_file": c["source_file"],
                 "chunk_id": c["chunk_id"],
                 "alias_hits": hits}
                for hits, c in top_chunks
            ],
            "example_command":
                f'python3 scripts/build_topic_pack.py "{topic["aliases"][0]}"',
        }

    ranked = sorted(index.items(),
                    key=lambda kv: -kv[1]["matching_chunks"])
    banner = mock_mode_banner(extraction_mode)

    payload = {
        "generated_at": now_iso(),
        "method": "keyword alias matching on word boundaries — NOT semantic "
                  "understanding; counts reflect phrasing, not meaning",
        "data_sources_inspected": data_sources,
        "extraction_mode": extraction_mode,
        "mock_mode_warning": banner,
        "insight_records_scanned": len(insights),
        "chunks_scanned": len(chunks),
        "topics": dict(ranked),
    }
    write_json(REPORTS_DIR / "topic_discovery_report.json", payload)
    write_json(TOPIC_INDEX_PATH, payload)

    lines = [
        "# Topic Discovery Report",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "**Question this answers: \"What topics can I make questions from?\"**",
        "",
        f"Scanned {len(chunks)} transcript chunks and {len(insights)} "
        f"extraction records across {len(payload['topics'])} configured topics.",
        "",
        "> Method note: these counts come from keyword/alias matching, not "
        "semantic understanding. A chunk counts when it literally uses one "
        "of the topic's phrases.",
        "",
    ]
    if banner:
        lines += [f"> ⚠️ {banner}", ""]
    lines += ["## Top topics", ""]
    for rank, (key, t) in enumerate(ranked, 1):
        top_assets = ", ".join(
            f"{f.replace('_', ' ')} ({n})" for f, n in t["top_asset_types"][:3]
        ) or "raw chunk matches only"
        related = ", ".join(
            c["display_name"] for c in t["co_occurring_topics"][:3]) or "—"
        lines += [
            f"### {rank}. {t['display_name']}",
            "",
            f"- **Why useful:** appears in {t['matching_chunks']} chunks across "
            f"{t['matching_source_files']} transcripts; strongest material: {top_assets}",
            f"- Matching extraction records: {t['matching_insight_records']} "
            f"({t['matching_assets_total']} on-topic asset items)",
            f"- Data basis: {t['data_basis']}",
            f"- Often appears alongside: {related}",
            f"- Build the pack: `{t['example_command']}`",
            "",
        ]
    lines += [
        "## Next step",
        "",
        "Pick a topic and run its command above. The topic pack collects "
        "questions, hooks, pain points, objections, angles, and source-backed "
        "excerpts in one report.",
    ]
    write_text_report(REPORTS_DIR / "topic_discovery_report.md",
                      "\n".join(lines) + "\n")

    print(f"\nTop topics by chunk coverage:")
    for key, t in ranked[:5]:
        print(f"  {t['display_name']}: {t['matching_chunks']} chunks, "
              f"{t['matching_assets_total']} on-topic assets")
    print(f"\nTopic index -> {TOPIC_INDEX_PATH}")
    print(f"Report -> {REPORTS_DIR / 'topic_discovery_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
