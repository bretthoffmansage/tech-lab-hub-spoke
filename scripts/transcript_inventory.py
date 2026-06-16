#!/usr/bin/env python3
"""Layer 3: Inventory of all transcript files.

Scans the transcript source directory, profiles every transcript-like file,
and writes processed/reports/transcript_inventory.{json,md}.

Read-only: never modifies transcript files.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, find_transcript_files, infer_title, infer_date,
    file_sha256, read_text, word_count, now_iso, write_json, write_text_report,
)

CAPTION_TAG_RE = re.compile(r"<(inaudible|crosstalk|laughter|music|silence|affirmative)[^>]*>|\[(inaudible|crosstalk|laughter|music|silence)[^\]]*\]", re.IGNORECASE)
SRT_TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}")
MIN_FILE_WORDS_DEFAULT = 30


def detect_format(text):
    head = text[:4000]
    if head.lstrip().startswith("WEBVTT"):
        return "vtt"
    if SRT_TIME_RE.search(head):
        return "srt"
    return "plain_text"


def profile_file(path, config):
    text = read_text(path)
    words = word_count(text)
    fmt = detect_format(text) if text.strip() else "empty"
    caption_tags = len(CAPTION_TAG_RE.findall(text))
    min_words = config.get("min_file_words", MIN_FILE_WORDS_DEFAULT)
    return {
        "file": path.name,
        "relative_path": str(path.relative_to(PROJECT_ROOT)),
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "word_count": words,
        "char_count": len(text),
        "inferred_title": infer_title(path.name),
        "inferred_date": infer_date(path.name),
        "detected_format": fmt,
        "caption_artifact_count": caption_tags,
        "is_empty": not text.strip(),
        "is_too_small": 0 < words < min_words,
        "content_sha256": file_sha256(path) if text.strip() else None,
    }


def main():
    config = load_config()
    source_dir, files = find_transcript_files(config, include_unsupported=True)
    supported_exts = set(e.lower() for e in config.get("supported_extensions", []))

    print(f"Scanning {source_dir} ...")
    entries = []
    for path in files:
        entry = profile_file(path, config)
        entry["supported"] = entry["extension"] in supported_exts
        entries.append(entry)

    # duplicate detection by content hash
    by_hash = defaultdict(list)
    for e in entries:
        if e["content_sha256"]:
            by_hash[e["content_sha256"]].append(e["file"])
    duplicate_groups = [v for v in by_hash.values() if len(v) > 1]
    dup_files = {f for group in duplicate_groups for f in group[1:]}
    for e in entries:
        e["is_duplicate_of"] = None
        if e["file"] in dup_files:
            group = next(g for g in duplicate_groups if e["file"] in g)
            e["is_duplicate_of"] = group[0]

    # naming pattern observations
    series = defaultdict(int)
    for e in entries:
        prefix = re.split(r"-{2,}|_", e["file"])[0].strip("-")
        series[prefix] += 1
    naming_patterns = sorted(series.items(), key=lambda kv: -kv[1])

    supported = [e for e in entries if e["supported"]]
    unsupported = [e for e in entries if not e["supported"]]
    dated = [e for e in entries if e["inferred_date"]]
    empty = [e for e in entries if e["is_empty"]]
    tiny = [e for e in entries if e["is_too_small"]]

    summary = {
        "generated_at": now_iso(),
        "source_dir": str(source_dir),
        "total_files_found": len(entries),
        "supported_files": len(supported),
        "unsupported_files": len(unsupported),
        "total_words": sum(e["word_count"] for e in entries),
        "total_chars": sum(e["char_count"] for e in entries),
        "files_with_inferred_date": len(dated),
        "empty_files": [e["file"] for e in empty],
        "too_small_files": [e["file"] for e in tiny],
        "duplicate_groups": duplicate_groups,
        "formats_detected": dict(defaultdict(int, {
            fmt: sum(1 for e in entries if e["detected_format"] == fmt)
            for fmt in {e["detected_format"] for e in entries}
        })),
        "extensions_present": sorted({e["extension"] for e in entries}),
        "naming_pattern_prefixes": naming_patterns[:15],
        "files_with_caption_artifacts": sum(1 for e in entries if e["caption_artifact_count"] > 0),
        "total_caption_artifacts": sum(e["caption_artifact_count"] for e in entries),
    }

    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    write_json(reports_dir / "transcript_inventory.json",
               {"summary": summary, "files": entries})

    lines = [
        "# Transcript Inventory",
        "",
        f"Generated: {summary['generated_at']}",
        f"Source directory: `{summary['source_dir']}`",
        "",
        "## Summary",
        "",
        f"- Files found: **{summary['total_files_found']}**"
        f" ({summary['supported_files']} supported, {summary['unsupported_files']} unsupported)",
        f"- Total words: **{summary['total_words']:,}**",
        f"- Total characters: **{summary['total_chars']:,}**",
        f"- Files with an inferable date in the filename: {summary['files_with_inferred_date']}",
        f"- Formats detected: {summary['formats_detected']}",
        f"- Extensions present: {', '.join(summary['extensions_present'])}",
        f"- Files containing caption artifacts (e.g. `<inaudible>`): "
        f"{summary['files_with_caption_artifacts']} "
        f"({summary['total_caption_artifacts']:,} artifacts total)",
        "",
    ]
    if summary["empty_files"]:
        lines += ["## Empty files", ""] + [f"- `{f}`" for f in summary["empty_files"]] + [""]
    if summary["too_small_files"]:
        lines += ["## Suspiciously small files", ""] + [f"- `{f}`" for f in summary["too_small_files"]] + [""]
    if duplicate_groups:
        lines += ["## Exact duplicate files (same content hash)", ""]
        for group in duplicate_groups:
            lines.append("- " + " == ".join(f"`{f}`" for f in group))
        lines.append("")
    lines += ["## Naming pattern prefixes", ""]
    for prefix, count in naming_patterns[:15]:
        lines.append(f"- `{prefix}`: {count} file(s)")
    lines += ["", "## All files", "",
              "| File | Words | Date | Format | Notes |",
              "|---|---:|---|---|---|"]
    for e in sorted(entries, key=lambda x: x["file"].lower()):
        notes = []
        if not e["supported"]:
            notes.append("unsupported")
        if e["is_empty"]:
            notes.append("EMPTY")
        if e["is_too_small"]:
            notes.append("too small")
        if e["is_duplicate_of"]:
            notes.append(f"duplicate of {e['is_duplicate_of']}")
        lines.append(
            f"| `{e['file']}` | {e['word_count']:,} | {e['inferred_date'] or 'unknown'} "
            f"| {e['detected_format']} | {', '.join(notes)} |"
        )
    write_text_report(reports_dir / "transcript_inventory.md", "\n".join(lines) + "\n")

    print(f"Inventory complete: {len(entries)} files, {summary['total_words']:,} words.")
    print(f"  -> {reports_dir / 'transcript_inventory.md'}")
    print(f"  -> {reports_dir / 'transcript_inventory.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
