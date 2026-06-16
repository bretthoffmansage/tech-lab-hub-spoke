"""Shared helpers for the Tech Lab transcript pipeline.

Standard library only. All scripts in this folder import from here so that
config loading, date/title inference, and file discovery behave identically
across the pipeline.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline_config.json"

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_source_dir(config):
    """Pick the transcript source directory.

    "auto" means: use raw_transcripts/ if it contains supported files,
    otherwise the project root folder itself.
    """
    configured = config.get("transcript_source_dir", "auto")
    if configured and configured != "auto":
        return (PROJECT_ROOT / configured).resolve()
    raw_dir = PROJECT_ROOT / "raw_transcripts"
    exts = set(config.get("supported_extensions", [".txt"]))
    if raw_dir.is_dir() and any(
        p.suffix.lower() in exts for p in raw_dir.iterdir() if p.is_file()
    ):
        return raw_dir
    return PROJECT_ROOT


def find_transcript_files(config, include_unsupported=False):
    """Return a sorted list of transcript file Paths in the source dir.

    Only scans the source directory and one level of subdirectories,
    skipping excluded dirs. Never returns anything inside generated folders.
    """
    source_dir = resolve_source_dir(config)
    exts = set(e.lower() for e in config.get("supported_extensions", []))
    unsupported = set(
        e.lower() for e in config.get("detected_but_unsupported_extensions", [])
    )
    excluded_dirs = set(config.get("excluded_dirs", []))
    excluded_files = set(config.get("excluded_files", []))

    wanted = exts | unsupported if include_unsupported else exts
    results = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source_dir)
        if any(part in excluded_dirs or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if path.name in excluded_files or path.name.startswith("."):
            continue
        if path.suffix.lower() in wanted:
            results.append(path)
    return source_dir, results


def infer_title(filename):
    """Turn a filename like 'Tech-Lab---July-23-2024---Part-2.txt' into a title."""
    stem = Path(filename).stem
    stem = stem.replace("_", " ")
    stem = re.sub(r"-{2,}", " - ", stem)
    stem = stem.replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def infer_date(filename):
    """Infer a date from a filename. Returns 'YYYY-MM-DD', 'YYYY-MM', or None.

    Handles patterns like:
      February-24-2026  -> 2026-02-24
      January-2025      -> 2025-01
      Apr-23 / Oct-23   -> 2023-04 / 2023-10  (2-digit year, 20-29 assumed 20xx)
      2024-07-23        -> 2024-07-23
    """
    name = Path(filename).stem.lower()
    tokens = re.split(r"[^a-z0-9]+", name)
    tokens = [t for t in tokens if t]

    m = re.search(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})", name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    for i, tok in enumerate(tokens):
        if tok not in MONTHS:
            continue
        month = MONTHS[tok]
        rest = tokens[i + 1:i + 3]
        # month day year (e.g. july 23 2024)
        if (
            len(rest) >= 2
            and rest[0].isdigit() and rest[1].isdigit()
            and 1 <= int(rest[0]) <= 31 and len(rest[1]) == 4
            and rest[1].startswith("20")
        ):
            return f"{int(rest[1]):04d}-{month:02d}-{int(rest[0]):02d}"
        # month year (4-digit)
        if rest and rest[0].isdigit() and len(rest[0]) == 4 and rest[0].startswith("20"):
            return f"{int(rest[0]):04d}-{month:02d}"
        # month + 2-digit year (apr 23 -> 2023-04); only safe when 20-29
        if rest and rest[0].isdigit() and len(rest[0]) == 2 and 20 <= int(rest[0]) <= 29:
            return f"20{int(rest[0]):02d}-{month:02d}"
    return None


def file_sha256(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def word_count(text):
    return len(text.split())


def slugify(name):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", Path(name).stem).strip("-").lower()
    return slug or "untitled"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_text_report(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_frontmatter(text):
    """Parse a simple '---' delimited frontmatter block. Returns (meta, body)."""
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1:
        return meta, text
    block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"')
        meta[key.strip()] = value
    return meta, body
