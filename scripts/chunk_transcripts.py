#!/usr/bin/env python3
"""Layer 5: Chunk cleaned transcripts into retrieval-friendly records.

Reads processed/cleaned_transcripts/*.md, splits each into ~1000-word chunks
with ~150-word overlap (boundaries near paragraph breaks when possible), and
writes:
  - one markdown file per chunk under processed/transcript_chunks/<slug>/
  - all chunk records to database/transcript_chunks.jsonl
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, now_iso, parse_frontmatter, word_count,
    write_json, write_jsonl, write_text_report,
)


def split_into_chunks(paragraphs, target, overlap, min_words):
    """Greedy paragraph packing to ~target words, then word-level overlap.

    Returns a list of chunk texts. A paragraph longer than target words is
    split at word level so no chunk balloons far past the target.
    """
    # explode oversized paragraphs first
    units = []
    for para in paragraphs:
        words = para.split()
        if len(words) <= target:
            units.append(para)
        else:
            for i in range(0, len(words), target):
                units.append(" ".join(words[i:i + target]))

    chunks = []
    current, current_words = [], 0
    for unit in units:
        uw = word_count(unit)
        if current and current_words + uw > target:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(unit)
        current_words += uw
    if current:
        # merge a tiny trailing chunk into the previous one
        if chunks and current_words < min_words:
            chunks[-1] = chunks[-1] + "\n\n" + "\n\n".join(current)
        else:
            chunks.append("\n\n".join(current))

    # add word-level overlap from the end of the previous chunk
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = " ".join(prev.split()[-overlap:])
            overlapped.append(tail + "\n\n" + cur)
        chunks = overlapped
    return chunks


def main():
    config = load_config()
    cleaned_dir = PROJECT_ROOT / config["cleaned_output_dir"]
    chunks_dir = PROJECT_ROOT / config["chunks_output_dir"]
    db_dir = PROJECT_ROOT / config["database_output_dir"]
    target = int(config.get("chunk_word_target", 1000))
    overlap = int(config.get("chunk_word_overlap", 150))
    min_words = int(config.get("min_chunk_words", 250))

    cleaned_files = sorted(cleaned_dir.glob("*.md"))
    if not cleaned_files:
        print(f"No cleaned transcripts found in {cleaned_dir}. "
              "Run scripts/normalize_transcripts.py first.")
        return 1

    all_records = []
    per_file = []
    for path in cleaned_files:
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        chunk_texts = split_into_chunks(paragraphs, target, overlap, min_words)

        slug = path.stem
        out_subdir = chunks_dir / slug
        out_subdir.mkdir(parents=True, exist_ok=True)

        ids = [f"{slug}__chunk_{i:04d}" for i in range(len(chunk_texts))]
        for i, text in enumerate(chunk_texts):
            record = {
                "chunk_id": ids[i],
                "source_file": meta.get("source_file", "unknown"),
                "cleaned_file": str(path.relative_to(PROJECT_ROOT)),
                "transcript_title": meta.get("transcript_title", slug),
                "inferred_date": meta.get("inferred_date", "unknown"),
                "chunk_index": i,
                "word_count": word_count(text),
                "text": text,
                "previous_chunk_id": ids[i - 1] if i > 0 else None,
                "next_chunk_id": ids[i + 1] if i < len(ids) - 1 else None,
            }
            all_records.append(record)
            (out_subdir / f"chunk_{i:04d}.md").write_text(
                f"---\nchunk_id: \"{ids[i]}\"\nsource_file: \"{record['source_file']}\"\n"
                f"transcript_title: \"{record['transcript_title']}\"\n"
                f"inferred_date: \"{record['inferred_date']}\"\n"
                f"chunk_index: {i}\nword_count: {record['word_count']}\n---\n\n{text}\n",
                encoding="utf-8",
            )
        per_file.append({
            "cleaned_file": path.name,
            "transcript_title": meta.get("transcript_title", slug),
            "chunks": len(chunk_texts),
            "total_words": sum(word_count(t) for t in chunk_texts),
        })
        print(f"chunked: {path.name} -> {len(chunk_texts)} chunks")

    write_jsonl(db_dir / "transcript_chunks.jsonl", all_records)

    sizes = [r["word_count"] for r in all_records]
    report = {
        "generated_at": now_iso(),
        "chunk_word_target": target,
        "chunk_word_overlap": overlap,
        "min_chunk_words": min_words,
        "transcripts_chunked": len(per_file),
        "total_chunks": len(all_records),
        "avg_chunk_words": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "min_chunk_words_actual": min(sizes) if sizes else 0,
        "max_chunk_words_actual": max(sizes) if sizes else 0,
        "per_file": per_file,
    }
    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    write_json(reports_dir / "chunking_report.json", report)

    lines = [
        "# Chunking Report", "",
        f"Generated: {report['generated_at']}", "",
        f"- Transcripts chunked: **{report['transcripts_chunked']}**",
        f"- Total chunks: **{report['total_chunks']}**",
        f"- Target words per chunk: {target} (overlap {overlap}, min {min_words})",
        f"- Actual chunk size: avg {report['avg_chunk_words']}, "
        f"min {report['min_chunk_words_actual']}, max {report['max_chunk_words_actual']}",
        "", "## Per transcript", "",
        "| Cleaned file | Title | Chunks | Words |",
        "|---|---|---:|---:|",
    ]
    for p in per_file:
        lines.append(f"| `{p['cleaned_file']}` | {p['transcript_title']} "
                     f"| {p['chunks']} | {p['total_words']:,} |")
    write_text_report(reports_dir / "chunking_report.md", "\n".join(lines) + "\n")

    print(f"\nChunking complete: {len(all_records)} chunks "
          f"-> {db_dir / 'transcript_chunks.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
