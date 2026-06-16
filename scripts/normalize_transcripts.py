#!/usr/bin/env python3
"""Layer 4: Conservative cleaning and normalization.

Reads supported transcript files, removes caption/transcription noise,
repairs line wrapping, and writes cleaned markdown files with frontmatter to
processed/cleaned_transcripts/. Never modifies the raw files.

Cleaning rules: docs/cleaning_rules.md
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, find_transcript_files, infer_title, infer_date,
    file_sha256, read_text, word_count, slugify, now_iso, write_json,
    write_text_report,
)

CAPTION_TAG_RE = re.compile(
    r"<(?:inaudible|crosstalk|laughter|laughs|music|silence|affirmative|negative)[^>]*>"
    r"|\[(?:inaudible|crosstalk|laughter|laughs|music|silence|applause)[^\]]*\]",
    re.IGNORECASE,
)
SRT_TIME_LINE_RE = re.compile(
    r"^\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}.*$"
)
VTT_NOTE_RE = re.compile(r"^\s*(WEBVTT|NOTE|STYLE|REGION|Kind:|Language:)", re.IGNORECASE)
SEQ_NUM_RE = re.compile(r"^\s*\d{1,5}\s*$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def looks_like_captions(text):
    head = text[:4000]
    return head.lstrip().startswith("WEBVTT") or bool(
        re.search(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", head)
    )


def clean_text(text):
    """Apply conservative cleaning. Returns (cleaned_text, stats)."""
    stats = {"caption_tags_removed": 0, "timestamp_lines_removed": 0,
             "sequence_lines_removed": 0, "duplicate_adjacent_lines_removed": 0}

    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL_CHARS_RE.sub("", text)

    is_captions = looks_like_captions(text)

    kept_lines = []
    prev_stripped = None
    for line in text.split("\n"):
        stripped = line.strip()
        if is_captions:
            if VTT_NOTE_RE.match(stripped):
                continue
            if SRT_TIME_LINE_RE.match(line):
                stats["timestamp_lines_removed"] += 1
                continue
            if SEQ_NUM_RE.match(line):
                stats["sequence_lines_removed"] += 1
                continue
        if stripped and stripped == prev_stripped:
            stats["duplicate_adjacent_lines_removed"] += 1
            continue
        prev_stripped = stripped if stripped else prev_stripped
        kept_lines.append(line)
    text = "\n".join(kept_lines)

    # remove inline caption artifact tags like <inaudible>
    text, n = CAPTION_TAG_RE.subn(" ", text)
    stats["caption_tags_removed"] = n

    # collapse runs of spaces created by tag removal (but keep newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.;:?!])", r"\1", text)

    # join machine-wrapped lines into paragraphs; blank lines separate paragraphs
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        joined = " ".join(seg.strip() for seg in block.split("\n") if seg.strip())
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs) + ("\n" if paragraphs else ""), stats


def build_frontmatter(meta):
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, str):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def main():
    config = load_config()
    source_dir, files = find_transcript_files(config, include_unsupported=True)
    supported_exts = set(e.lower() for e in config.get("supported_extensions", []))
    out_dir = PROJECT_ROOT / config["cleaned_output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    skip_dupes = config.get("skip_exact_duplicates", True)
    skip_empty = config.get("skip_empty_files", True)
    min_words = config.get("min_file_words", 30)

    processed, skipped, unsupported, warnings = [], [], [], []
    seen_hashes = {}

    for path in files:
        rel = str(path.relative_to(PROJECT_ROOT))
        if path.suffix.lower() not in supported_exts:
            unsupported.append({"file": rel, "reason": f"unsupported extension {path.suffix}"})
            continue

        raw = read_text(path)
        if skip_empty and not raw.strip():
            skipped.append({"file": rel, "reason": "empty file"})
            continue

        content_hash = file_sha256(path)
        if skip_dupes and content_hash in seen_hashes:
            skipped.append({"file": rel,
                            "reason": f"exact duplicate of {seen_hashes[content_hash]}"})
            continue
        seen_hashes[content_hash] = rel

        original_words = word_count(raw)
        if original_words < min_words:
            skipped.append({"file": rel,
                            "reason": f"too small ({original_words} words)"})
            continue

        cleaned, stats = clean_text(raw)
        cleaned_words = word_count(cleaned)
        reduction = (1 - cleaned_words / original_words) * 100 if original_words else 0.0
        if reduction > 15:
            warnings.append(
                f"{rel}: cleaning removed {reduction:.1f}% of words — review manually"
            )

        meta = {
            "source_file": rel,
            "original_extension": path.suffix.lower(),
            "transcript_title": infer_title(path.name),
            "inferred_date": infer_date(path.name) or "unknown",
            "word_count_original": original_words,
            "word_count_cleaned": cleaned_words,
            "processing_status": "cleaned",
        }
        out_name = slugify(path.name) + ".md"
        out_path = out_dir / out_name
        out_path.write_text(
            build_frontmatter(meta) + "\n\n" + cleaned, encoding="utf-8"
        )

        processed.append({
            "file": rel,
            "cleaned_file": str(out_path.relative_to(PROJECT_ROOT)),
            "word_count_original": original_words,
            "word_count_cleaned": cleaned_words,
            "reduction_pct": round(reduction, 2),
            "cleaning_stats": stats,
        })
        print(f"cleaned: {path.name} ({original_words:,} -> {cleaned_words:,} words)")

    total_original = sum(p["word_count_original"] for p in processed)
    total_cleaned = sum(p["word_count_cleaned"] for p in processed)
    report = {
        "generated_at": now_iso(),
        "source_dir": str(source_dir),
        "files_processed": len(processed),
        "files_skipped": len(skipped),
        "files_unsupported": len(unsupported),
        "total_word_count_original": total_original,
        "total_word_count_cleaned": total_cleaned,
        "overall_reduction_pct": round(
            (1 - total_cleaned / total_original) * 100, 2) if total_original else 0.0,
        "warnings": warnings,
        "skipped": skipped,
        "unsupported": unsupported,
        "processed": processed,
    }

    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    write_json(reports_dir / "cleaning_report.json", report)

    lines = [
        "# Cleaning Report", "",
        f"Generated: {report['generated_at']}", "",
        f"- Files processed: **{report['files_processed']}**",
        f"- Files skipped: {report['files_skipped']}",
        f"- Unsupported files: {report['files_unsupported']}",
        f"- Total words (original): {total_original:,}",
        f"- Total words (cleaned): {total_cleaned:,}",
        f"- Overall reduction: {report['overall_reduction_pct']}%", "",
    ]
    if warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in warnings] + [""]
    if skipped:
        lines += ["## Skipped files", ""] + [
            f"- `{s['file']}` — {s['reason']}" for s in skipped] + [""]
    if unsupported:
        lines += ["## Unsupported files", ""] + [
            f"- `{u['file']}` — {u['reason']}" for u in unsupported] + [""]
    lines += ["## Processed files", "",
              "| Source | Original words | Cleaned words | Reduction |",
              "|---|---:|---:|---:|"]
    for p in processed:
        lines.append(f"| `{p['file']}` | {p['word_count_original']:,} "
                     f"| {p['word_count_cleaned']:,} | {p['reduction_pct']}% |")
    write_text_report(reports_dir / "cleaning_report.md", "\n".join(lines) + "\n")

    print(f"\nCleaning complete: {len(processed)} files -> {out_dir}")
    print(f"  Reduction overall: {report['overall_reduction_pct']}% "
          f"(conservative cleaning should stay small)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
