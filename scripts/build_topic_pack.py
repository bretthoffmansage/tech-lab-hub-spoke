#!/usr/bin/env python3
"""Build a full topic pack — broad useful material on one topic, grouped by
type, lightly deduplicated, source-traceable. Not one best answer.

Usage:
    python3 scripts/build_topic_pack.py "founder bottleneck"
    python3 scripts/build_topic_pack.py "right fit client"
    python3 scripts/build_topic_pack.py "offer positioning" --limit 50
    python3 scripts/build_topic_pack.py "content strategy" --export-md

Writes:
    processed/reports/topic_packs/<topic>_topic_pack.md
    database/topic_packs/<topic>_topic_pack.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, write_json,
)
from topic_lib import (  # noqa: E402
    TOPIC_INDEX_PATH, load_topic_config, resolve_topic, topic_regex,
    load_insights, load_chunks, record_matches, collect_items,
    matching_chunks, mock_mode_banner,
)

PACKS_MD_DIR = PROJECT_ROOT / "processed" / "reports" / "topic_packs"
PACKS_JSON_DIR = PROJECT_ROOT / "database" / "topic_packs"

SECTIONS = [
    ("right_fit_client_questions", "Best Right-Fit-Client Questions",
     ["right_fit_client_questions", "better_questions"]),
    ("pain_points", "Pain Points", ["client_pain_points"]),
    ("client_desires", "Client Desires", ["client_desires"]),
    ("objections_pushback", "Objections and Pushback", ["client_objections"]),
    ("beliefs_mistakes", "Beliefs Challenged / Mistakes",
     ["beliefs_challenged", "mistakes_identified", "better_questions"]),
    ("hooks_quotables", "Hooks and Quotable Lines",
     ["content_hooks", "quotable_lines", "metaphors_or_phrases"]),
    ("youtube_angles", "YouTube Angles", ["youtube_angles"]),
    ("short_form_angles", "Short-Form Angles", ["short_form_angles"]),
    ("email_angles", "Email Angles", ["email_angles"]),
    ("sales_page_angles", "Sales-Page Angles", ["sales_page_angles"]),
    ("offer_positioning", "Offer Positioning Notes", ["offer_positioning_notes"]),
]

QUESTION_RE = re.compile(r"(?<=[.?!])\s+")


def question_fallback(chunks_for_topic, regex, limit):
    """Question-like sentences pulled straight from matching chunk text."""
    out, seen = [], set()
    for entry in chunks_for_topic:
        # re-scan full chunk text via excerpt source is not enough; excerpts
        # are short — fallback uses what we have, the excerpt sentences
        for s in QUESTION_RE.split(entry["excerpt"]):
            s = s.strip().lstrip("…").strip()
            if s.endswith("?") and regex.search(s) and 4 <= len(s.split()) <= 60:
                key = s.lower()
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "text": s, "field": "chunk_text_question",
                        "alias_hits_in_item": len(regex.findall(s)),
                        "usefulness_score": None, "confidence_score": None,
                        "source_file": entry["source_file"],
                        "transcript_title": entry["transcript_title"],
                        "inferred_date": entry.get("inferred_date"),
                        "chunk_id": entry["chunk_id"],
                        "chunk_index": entry.get("chunk_index"),
                        "record_id": None,
                    })
        if len(out) >= limit:
            break
    return out[:limit]


def build_summary(topic, stats, extraction_mode):
    parts = [
        f"Across the archive, \"{topic['display_name']}\" language appears in "
        f"{stats['matching_chunks']} chunks from "
        f"{stats['matching_source_files']} transcripts."
    ]
    if stats["top_sections"]:
        parts.append(
            "The strongest material by volume: "
            + ", ".join(f"{name.lower()} ({n})"
                        for name, n in stats["top_sections"][:4]) + ".")
    if stats["co_occurring"]:
        parts.append("It most often appears alongside "
                     + ", ".join(stats["co_occurring"][:3]) + ".")
    if extraction_mode == "mock":
        parts.append(
            "NOTE: this is a placeholder summary based on mock/keyword "
            "extraction — it reflects where the topic shows up, not yet a "
            "polished read of what is taught about it.")
    return " ".join(parts)


def cite(item):
    bits = [f"`{item['source_file']}`"]
    if item.get("inferred_date") and item["inferred_date"] != "unknown":
        bits.append(item["inferred_date"])
    bits.append(f"chunk `{item['chunk_id']}`")
    return " · ".join(bits)


def main():
    parser = argparse.ArgumentParser(description="Build a topic pack.")
    parser.add_argument("topic", help='Topic, e.g. "founder bottleneck"')
    parser.add_argument("--limit", type=int,
                        help="Max items per section (default from config)")
    parser.add_argument("--export-md", action="store_true",
                        help="(Markdown is always written; flag kept for "
                             "convenience/compatibility)")
    args = parser.parse_args()

    config = load_topic_config()
    limit = args.limit or config.get("default_asset_limit_per_section", 25)
    max_excerpts = config.get("max_source_excerpts", 20)

    topic = resolve_topic(args.topic, config)
    regex = topic_regex(topic["aliases"])
    insights, extraction_mode = load_insights(config)
    chunks = load_chunks()
    if not insights and not chunks:
        print("No data found. Run python3 scripts/run_pipeline.py first.")
        return 1

    print(f"Topic: {topic['display_name']} "
          f"({'configured' if topic['configured'] else 'ad-hoc'}; "
          f"{len(topic['aliases'])} alias(es))")

    matched_records = [r for r in insights if record_matches(r, regex)]
    excerpts = matching_chunks(chunks, regex, max_excerpts)
    all_chunk_matches = matching_chunks(chunks, regex, len(chunks)) if chunks else []

    sections = {}
    for key, title, fields in SECTIONS:
        prefer = collect_items(matched_records, fields, regex, limit,
                               require_alias_in_item=True)
        if len(prefer) < limit:
            extra = collect_items(matched_records, fields, regex,
                                  limit - len(prefer))
            seen = {i["text"] for i in prefer}
            prefer += [e for e in extra if e["text"] not in seen]
        sections[key] = prefer[:limit]

    # questions fallback from raw chunk text if extraction gave too few
    if len(sections["right_fit_client_questions"]) < 5:
        fallback = question_fallback(all_chunk_matches, regex, limit)
        seen = {i["text"].lower() for i in sections["right_fit_client_questions"]}
        sections["right_fit_client_questions"] += [
            f for f in fallback if f["text"].lower() not in seen][:limit]

    # related topics from the topic index (or co-occurrence on the fly)
    related = []
    if TOPIC_INDEX_PATH.exists():
        index = json.loads(TOPIC_INDEX_PATH.read_text(encoding="utf-8"))
        entry = index.get("topics", {}).get(topic["topic_key"])
        if entry:
            related = [c["display_name"] for c in entry["co_occurring_topics"]]
    if not related and chunks:
        other = {k: topic_regex(t["aliases"])
                 for k, t in config["topic_aliases"].items()
                 if k != topic["topic_key"]}
        counts = {}
        for e in all_chunk_matches[:200]:
            for k, rgx in other.items():
                if rgx.search(e["excerpt"]):
                    counts[k] = counts.get(k, 0) + 1
        related = [config["topic_aliases"][k]["display_name"]
                   for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:5]]

    stats = {
        "matching_chunks": len(all_chunk_matches),
        "matching_source_files": len({e["source_file"] for e in all_chunk_matches}),
        "matching_insight_records": len(matched_records),
        "top_sections": sorted(
            ((title, len(sections[key])) for key, title, _ in SECTIONS
             if sections[key]), key=lambda x: -x[1]),
        "co_occurring": related,
    }
    summary = build_summary(topic, stats, extraction_mode)
    banner = mock_mode_banner(extraction_mode)
    demo_questions = [
        f'Give me questions from this topic. -> python3 scripts/export_topic_assets.py "{args.topic}" --asset-type questions',
        f'Give me hooks from this topic. -> python3 scripts/export_topic_assets.py "{args.topic}" --asset-type hooks',
        f'Give me objections from this topic. -> python3 scripts/export_topic_assets.py "{args.topic}" --asset-type objections',
        f'Give me YouTube angles from this topic. -> python3 scripts/export_topic_assets.py "{args.topic}" --asset-type youtube_angles',
        f'Give me everything useful from this topic. -> python3 scripts/export_topic_assets.py "{args.topic}" --asset-type all',
    ]

    pack = {
        "topic_key": topic["topic_key"],
        "display_name": topic["display_name"],
        "query": args.topic,
        "aliases_used": topic["aliases"],
        "configured_topic": topic["configured"],
        "generated_at": now_iso(),
        "extraction_mode": extraction_mode,
        "mock_mode_warning": banner,
        "method_note": "Keyword alias matching and light normalized-text "
                       "dedupe; broad collection, not a single best answer.",
        "limits": {"per_section": limit, "max_source_excerpts": max_excerpts},
        "stats": stats,
        "summary": summary,
        "sections": sections,
        "source_excerpts": excerpts,
        "related_topics": related,
        "suggested_demo_questions": demo_questions,
    }
    slug = topic["topic_key"]
    json_path = PACKS_JSON_DIR / f"{slug}_topic_pack.json"
    write_json(json_path, pack)

    # ---------- markdown report ----------
    lines = [f"# Topic Pack: {topic['display_name']}", "",
             f"Generated: {pack['generated_at']}  |  "
             f"Aliases matched: {', '.join(topic['aliases'])}", ""]
    if banner:
        lines += [f"> ⚠️ {banner}", ""]
    lines += ["## 1. Quick Summary", "", summary, ""]

    section_num = 2
    titles = {key: title for key, title, _ in SECTIONS}
    order = ["right_fit_client_questions", "pain_points", "client_desires",
             "objections_pushback", "beliefs_mistakes", "hooks_quotables"]
    for key in order:
        lines += [f"## {section_num}. {titles[key]}", ""]
        items = sections[key]
        if not items:
            lines += ["_No on-topic items found in current extraction output._", ""]
        for item in items:
            lines += [f"- {item['text']}", f"  - {cite(item)}"]
        lines.append("")
        section_num += 1

    lines += [f"## {section_num}. Content Angles", ""]
    for key in ("youtube_angles", "short_form_angles", "email_angles",
                "sales_page_angles"):
        lines += [f"### {titles[key]}", ""]
        items = sections[key]
        if not items:
            lines += ["_None found in current extraction output._", ""]
        for item in items:
            lines += [f"- {item['text']}", f"  - {cite(item)}"]
        lines.append("")
    section_num += 1

    lines += [f"## {section_num}. Offer Positioning Notes", ""]
    if not sections["offer_positioning"]:
        lines += ["_None found in current extraction output._", ""]
    for item in sections["offer_positioning"]:
        lines += [f"- {item['text']}", f"  - {cite(item)}"]
    lines.append("")
    section_num += 1

    lines += [f"## {section_num}. Source-Backed Excerpts", ""]
    for e in excerpts:
        lines += [
            f"> {e['excerpt']}",
            "",
            f"— `{e['source_file']}` · {e['transcript_title']} · "
            f"{e.get('inferred_date')} · chunk `{e['chunk_id']}` "
            f"({e['alias_hits']} topic mentions)",
            "",
        ]
    section_num += 1

    lines += [f"## {section_num}. Related Topics to Explore Next", ""]
    lines += [f"- {t}" for t in related] or ["_None detected._"]
    lines.append("")
    section_num += 1

    lines += [f"## {section_num}. Suggested Demo Questions", ""]
    lines += [f"- {q}" for q in demo_questions]
    lines.append("")

    md_path = PACKS_MD_DIR / f"{slug}_topic_pack.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # ---------- terminal summary ----------
    print(f"\n{summary}\n")
    for key, title, _ in SECTIONS:
        if sections[key]:
            print(f"  {title}: {len(sections[key])} item(s)")
    print(f"  Source-backed excerpts: {len(excerpts)}")
    if related:
        print(f"  Related topics: {', '.join(related[:4])}")
    sample = sections["right_fit_client_questions"][:2]
    if sample:
        print("\nSample right-fit-client questions:")
        for s in sample:
            print(f"  - {s['text'][:140]}")
    print(f"\nMarkdown -> {md_path}")
    print(f"JSON     -> {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
