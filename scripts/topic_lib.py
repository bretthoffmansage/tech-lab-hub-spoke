"""Shared helpers for the topic pack workflow (Boss Demo v1).

Topic resolution, alias matching, item collection, and light dedupe.
Keyword matching only — these helpers do not claim semantic understanding.
Standard library only.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT, read_jsonl, slugify  # noqa: E402

TOPIC_CONFIG_PATH = PROJECT_ROOT / "config" / "topic_pack_config.json"
INSIGHTS_PATH = PROJECT_ROOT / "database" / "extracted_marketing_insights.jsonl"
CHUNKS_PATH = PROJECT_ROOT / "database" / "transcript_chunks.jsonl"
SIGNALS_PATH = PROJECT_ROOT / "database" / "basic_signals.jsonl"
TOPIC_INDEX_PATH = PROJECT_ROOT / "database" / "topic_index.json"

# every text-bearing field on an extraction record
INSIGHT_TEXT_FIELDS = [
    "core_topic", "subtopics", "client_pain_points", "client_desires",
    "client_objections", "beliefs_challenged", "mistakes_identified",
    "better_questions", "frameworks_or_models", "stories_or_examples",
    "metaphors_or_phrases", "quotable_lines", "right_fit_client_questions",
    "content_hooks", "youtube_angles", "short_form_angles", "email_angles",
    "sales_page_angles", "offer_positioning_notes", "audience_segments",
    "tags", "source_text_excerpt",
]


def load_topic_config():
    with open(TOPIC_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize(text):
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", t).strip()


def topic_regex(aliases):
    """One compiled regex matching any alias on word boundaries."""
    parts = sorted((re.escape(a) for a in aliases), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


def resolve_topic(query, config):
    """Match a user-typed topic against configured aliases.

    Returns {topic_key, display_name, aliases, configured}. Unrecognized
    queries become ad-hoc single-alias topics so any phrase still works.
    """
    qnorm = normalize(query)
    for key, topic in config["topic_aliases"].items():
        candidates = ([key.replace("_", " "), topic["display_name"]]
                      + topic["aliases"])
        if qnorm in {normalize(c) for c in candidates}:
            return {"topic_key": key,
                    "display_name": topic["display_name"],
                    "aliases": topic["aliases"],
                    "configured": True}
    return {"topic_key": slugify(query),
            "display_name": query.strip().title(),
            "aliases": [query.strip()],
            "configured": False}


def load_insights(config):
    """Load extraction records honoring config filters. ([], mode) if absent."""
    if not INSIGHTS_PATH.exists():
        return [], "none"
    records = read_jsonl(INSIGHTS_PATH)
    min_score = config.get("min_usefulness_score", 0)
    if not config.get("include_mock_records", True):
        records = [r for r in records
                   if r.get("extraction_provider") != "mock"]
    records = [r for r in records
               if (r.get("usefulness_score") or 0) >= min_score]
    providers = {r.get("extraction_provider") for r in records}
    if providers == {"mock"}:
        mode = "mock"
    elif "mock" in providers:
        mode = "mixed"
    elif providers:
        mode = "real"
    else:
        mode = "none"
    return records, mode


def load_chunks():
    return read_jsonl(CHUNKS_PATH) if CHUNKS_PATH.exists() else []


def record_matches(record, regex):
    """Total alias hits across all text fields of an insight record."""
    hits = 0
    for field in INSIGHT_TEXT_FIELDS:
        value = record.get(field)
        if isinstance(value, str):
            hits += len(regex.findall(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    hits += len(regex.findall(item))
    return hits


def collect_items(records, fields, regex, limit, require_alias_in_item=False):
    """Collect deduped items from the given fields of topic-matching records.

    Items whose own text contains an alias rank first, then record
    usefulness, then confidence. Each item keeps source traceability.
    """
    seen = {}
    for r in records:
        for field in fields:
            for text in r.get(field) or []:
                if not isinstance(text, str) or len(text.split()) < 3:
                    continue
                own_hits = len(regex.findall(text))
                if require_alias_in_item and not own_hits:
                    continue
                key = normalize(text)
                candidate = {
                    "text": text,
                    "field": field,
                    "alias_hits_in_item": own_hits,
                    "usefulness_score": r.get("usefulness_score"),
                    "confidence_score": r.get("confidence_score"),
                    "source_file": r["source_file"],
                    "transcript_title": r["transcript_title"],
                    "inferred_date": r.get("inferred_date"),
                    "chunk_id": r["chunk_id"],
                    "chunk_index": r.get("chunk_index"),
                    "record_id": r["record_id"],
                }
                prev = seen.get(key)
                if prev is None or (
                        candidate["alias_hits_in_item"],
                        candidate["usefulness_score"] or 0) > (
                        prev["alias_hits_in_item"],
                        prev["usefulness_score"] or 0):
                    seen[key] = candidate
    items = sorted(seen.values(), key=lambda x: (
        -x["alias_hits_in_item"], -(x["usefulness_score"] or 0),
        -(x["confidence_score"] or 0)))
    return items[:limit]


def chunk_excerpt(text, regex, window=400):
    """Excerpt centered on the first alias match."""
    m = regex.search(text)
    pos = m.start() if m else 0
    start = max(0, pos - window // 3)
    end = min(len(text), start + window)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    return (("…" if start > 0 else "") + excerpt
            + ("…" if end < len(text) else ""))


def matching_chunks(chunks, regex, limit):
    """Chunks ranked by alias hit count, with excerpt and traceability."""
    scored = []
    for c in chunks:
        hits = len(regex.findall(c["text"]))
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda x: -x[0])
    return [{
        "source_file": c["source_file"],
        "transcript_title": c["transcript_title"],
        "inferred_date": c.get("inferred_date"),
        "chunk_id": c["chunk_id"],
        "chunk_index": c.get("chunk_index"),
        "alias_hits": hits,
        "excerpt": chunk_excerpt(c["text"], regex),
    } for hits, c in scored[:limit]]


def mock_mode_banner(extraction_mode):
    if extraction_mode == "mock":
        return ("Current extraction mode appears to be mock/placeholder. "
                "This topic pack is useful for workflow testing and rough "
                "exploration, but real LLM extraction will produce better "
                "questions, hooks, and summaries.")
    if extraction_mode == "mixed":
        return ("Some records are mock/placeholder extractions; quality is "
                "mixed until a full real-provider extraction run replaces them.")
    return None
