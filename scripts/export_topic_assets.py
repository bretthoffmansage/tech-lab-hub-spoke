#!/usr/bin/env python3
"""Export a clean, hand-off-ready list of assets for one topic.

Usage:
    python3 scripts/export_topic_assets.py "founder bottleneck" --asset-type questions
    python3 scripts/export_topic_assets.py "right fit client" --asset-type hooks
    python3 scripts/export_topic_assets.py "offer" --asset-type all

Writes:
    exports/topic_assets/<topic>_<asset_type>.md
    exports/topic_assets/<topic>_<asset_type>.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT, now_iso, write_json  # noqa: E402
from topic_lib import (  # noqa: E402
    load_topic_config, resolve_topic, topic_regex, load_insights,
    record_matches, collect_items, mock_mode_banner,
)

EXPORTS_DIR = PROJECT_ROOT / "exports" / "topic_assets"

ASSET_TYPES = {
    "questions": ("Right-Fit-Client Questions",
                  ["right_fit_client_questions", "better_questions"]),
    "hooks": ("Content Hooks", ["content_hooks", "metaphors_or_phrases"]),
    "pain_points": ("Pain Points", ["client_pain_points"]),
    "objections": ("Objections", ["client_objections"]),
    "youtube_angles": ("YouTube Angles", ["youtube_angles"]),
    "short_form_angles": ("Short-Form Angles", ["short_form_angles"]),
    "email_angles": ("Email Angles", ["email_angles"]),
    "offer_notes": ("Offer Positioning Notes", ["offer_positioning_notes"]),
    "quotes": ("Quotable Lines", ["quotable_lines"]),
}


def main():
    parser = argparse.ArgumentParser(description="Export topic assets.")
    parser.add_argument("topic", help='Topic, e.g. "founder bottleneck"')
    parser.add_argument("--asset-type", dest="asset_type", default="all",
                        choices=sorted(ASSET_TYPES) + ["all"],
                        help="Which asset list to export (default: all)")
    parser.add_argument("--limit", type=int,
                        help="Max items per asset type (default from config)")
    args = parser.parse_args()

    config = load_topic_config()
    limit = args.limit or config.get("default_asset_limit_per_section", 25)
    topic = resolve_topic(args.topic, config)
    regex = topic_regex(topic["aliases"])
    insights, extraction_mode = load_insights(config)
    if not insights:
        print("No extraction records found. Run "
              "python3 scripts/run_marketing_extraction_pipeline.py first.")
        return 1

    matched_records = [r for r in insights if record_matches(r, regex)]
    print(f"Topic: {topic['display_name']} — "
          f"{len(matched_records)} matching extraction record(s)")

    wanted = sorted(ASSET_TYPES) if args.asset_type == "all" \
        else [args.asset_type]
    banner = mock_mode_banner(extraction_mode)

    asset_groups = {}
    for asset_type in wanted:
        title, fields = ASSET_TYPES[asset_type]
        items = collect_items(matched_records, fields, regex, limit,
                              require_alias_in_item=True)
        if len(items) < limit:
            extra = collect_items(matched_records, fields, regex,
                                  limit - len(items))
            seen = {i["text"] for i in items}
            items += [e for e in extra if e["text"] not in seen]
        asset_groups[asset_type] = items[:limit]

    payload = {
        "topic_key": topic["topic_key"],
        "display_name": topic["display_name"],
        "query": args.topic,
        "asset_type": args.asset_type,
        "generated_at": now_iso(),
        "extraction_mode": extraction_mode,
        "mock_mode_warning": banner,
        "assets": asset_groups,
    }

    slug = topic["topic_key"]
    json_path = EXPORTS_DIR / f"{slug}_{args.asset_type}.json"
    write_json(json_path, payload)

    lines = [f"# {topic['display_name']} — "
             + (", ".join(ASSET_TYPES[t][0] for t in wanted)
                if args.asset_type != "all" else "All Assets"),
             "", f"Generated: {payload['generated_at']}", ""]
    if banner:
        lines += [f"> ⚠️ {banner}", ""]
    total = 0
    for asset_type in wanted:
        title, _ = ASSET_TYPES[asset_type]
        items = asset_groups[asset_type]
        total += len(items)
        if args.asset_type == "all":
            lines += [f"## {title}", ""]
        if not items:
            lines += ["_None found for this topic in current extraction output._", ""]
            continue
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item['text']}")
            lines.append(f"   - source: `{item['source_file']}` · "
                         f"chunk `{item['chunk_id']}`")
        lines.append("")
    md_path = EXPORTS_DIR / f"{slug}_{args.asset_type}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Exported {total} item(s) across {len(wanted)} asset type(s)")
    print(f"  -> {md_path}")
    print(f"  -> {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
