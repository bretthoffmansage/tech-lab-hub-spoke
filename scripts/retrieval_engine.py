"""Retrieval layer for the conversational Tech Lab Transcript Assistant.

Given a user question (and optional conversation context phrase), pull the
most relevant source material from the active data provider (Convex
preferred). transcriptChunks are the primary source of truth; marketingAssets
are secondary hints (current extraction is mock). topicIndex is only used
for topic listings. Keyword retrieval — no vectors, no semantic claims.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for",
    "from", "about", "with", "at", "by", "into", "is", "are", "was", "were",
    "be", "do", "does", "did", "have", "has", "had", "what", "which", "who",
    "how", "when", "where", "why", "can", "could", "should", "would", "will",
    "i", "we", "you", "they", "it", "this", "that", "these", "those", "me",
    "my", "our", "your", "their", "say", "says", "said", "tell", "give",
    "show", "find", "get", "make", "want", "need", "please", "transcripts",
    "transcript", "archive", "material", "anything", "something", "stuff",
    # meta-verbs about the archive, not content terms
    "teach", "teaches", "teaching", "taught", "learn", "learned", "cover",
    "covers", "covered", "discuss", "discussed", "mention", "mentioned",
    "talk", "talks", "talked", "explain", "explained", "search",
}
# asset/intent vocabulary that shouldn't drive retrieval
MODE_WORDS = {
    "question", "questions", "hook", "hooks", "angle", "angles", "quote",
    "quotes", "client-facing", "facing", "polished", "turn", "convert",
    "rewrite", "list", "ideas", "right-fit", "right-fit-client",
}

MAX_TEXT_CHARS = 2400  # per-source cap when formatting for the LLM


def simplify_query(query):
    """Strip stopwords and asset/mode words to get retrieval keywords."""
    words = re.findall(r"[a-z0-9'-]+", query.lower())
    kept = [w for w in words if w not in STOPWORDS and w not in MODE_WORDS
            and len(w) > 1]
    return " ".join(kept)


def search_chunks(query, provider, limit):
    try:
        results, _backend = provider.search_transcripts(query, limit=limit)
        return results
    except Exception:  # noqa: BLE001 — retrieval must never crash the app
        return []


def search_assets(query, provider, limit):
    try:
        return provider.search_assets(query, limit=limit)
    except Exception:  # noqa: BLE001
        return []


def list_topics(provider):
    try:
        topics = provider.get_topics()
        topics.sort(key=lambda t: -(t.get("matching_chunks") or 0))
        return topics
    except Exception:  # noqa: BLE001
        return []


def _coverage(text, terms):
    """Fraction of distinct query terms present in the text (loose plural
    matching). Guards against OR-semantics search returning chunks that
    match only one incidental word of a multi-word query."""
    if not terms:
        return 1.0
    lower = text.lower()
    hits = 0
    for term in terms:
        stem = term[:-1] if len(term) > 3 and term.endswith("s") else term
        if stem in lower:
            hits += 1
    return hits / len(terms)


def retrieve_sources(query, data_provider, limit_chunks=8, limit_assets=8,
                     context_phrase=None):
    """Multi-pass keyword retrieval, deduped, with provenance per source.

    Passes: the query as-is, the stopword-stripped keywords, and (for
    follow-ups) the prior conversation phrase. Chunks first, assets second.
    Sources covering under half the query's content terms are dropped —
    full-text search has OR semantics, so single-incidental-word matches
    would otherwise look like relevant results.
    """
    queries = [query.strip()]
    simplified = simplify_query(query)
    if simplified and simplified.lower() != query.strip().lower():
        queries.append(simplified)
    if context_phrase and context_phrase.strip():
        combined = simplify_query(f"{context_phrase} {query}")
        if combined and combined not in queries:
            queries.append(combined)

    chunks, seen_chunks = [], set()
    for q in queries:
        if len(chunks) >= limit_chunks or not q:
            continue
        for r in search_chunks(q, data_provider, limit_chunks):
            if r["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(r["chunk_id"])
            chunks.append({**r, "origin": "transcriptChunks"})
            if len(chunks) >= limit_chunks:
                break

    assets, seen_assets = [], set()
    for q in queries:
        if len(assets) >= limit_assets or not q:
            continue
        for a in search_assets(q, data_provider, limit_assets):
            key = a.get("asset_id") or a.get("text")
            if key in seen_assets:
                continue
            seen_assets.add(key)
            assets.append({**a, "origin": "marketingAssets"})
            if len(assets) >= limit_assets:
                break

    # relevance gate: drop sources covering too few of the query's content
    # terms. 2-term queries require both (one incidental word ≠ relevance);
    # longer queries require half. Title/filename count toward coverage so
    # "the OBIE material" matches chunks of "Introducing OBIE" even where
    # the transcription spells it "Obi".
    terms = simplify_query(query).split()
    if terms:
        # "offers AND pricing" coordinates two concepts — either suffices;
        # "dog grooming" is one compound concept — require both words
        coordinated = bool(re.search(r"\b(and|or|vs|versus)\b",
                                     query.lower()))
        threshold = 0.6 if (len(terms) == 2 and not coordinated) else 0.5

        def src_text(s):
            return " ".join([s.get("transcript_title") or "",
                             s.get("source_file") or "",
                             s.get("text") or s.get("excerpt") or ""])

        scored = [(c, _coverage(src_text(c), terms)) for c in chunks]
        chunks = [c for c, cov in sorted(scored, key=lambda x: -x[1])
                  if cov >= threshold]
        assets = [a for a in assets if _coverage(src_text(a), terms)
                  >= threshold]

    total = len(chunks) + len(assets)
    if total == 0:
        strength = "none"
    elif len(chunks) == 0 or total < 3:
        strength = "weak"
    else:
        strength = "ok"

    return {
        "query": query,
        "effective_queries": queries,
        "chunks": chunks,
        "assets": assets,
        "total": total,
        "strength": strength,
        "method": "keyword search (Convex full-text / local FTS5), not semantic",
    }


def _trim_text(text, query_terms, max_chars=MAX_TEXT_CHARS):
    """Window the text around the first query-term hit to bound prompt size."""
    if len(text) <= max_chars:
        return text
    lower = text.lower()
    pos = -1
    for term in query_terms:
        pos = lower.find(term.lower())
        if pos != -1:
            break
    if pos == -1:
        pos = 0
    start = max(0, pos - max_chars // 3)
    end = min(len(text), start + max_chars)
    return ("…" if start > 0 else "") + text[start:end] \
        + ("…" if end < len(text) else "")


def format_sources_for_llm(retrieval_result):
    """Numbered source blocks the LLM can ground on and cite."""
    terms = [t for t in
             simplify_query(retrieval_result["query"]).split() if t]
    blocks = []
    for i, c in enumerate(retrieval_result["chunks"], 1):
        text = c.get("text") or c.get("excerpt") or ""
        blocks.append(
            f"[S{i}] TRANSCRIPT CHUNK — source_file: {c['source_file']} | "
            f"chunk_id: {c['chunk_id']} | title: {c['transcript_title']} | "
            f"date: {c.get('inferred_date', 'unknown')}\n"
            f"{_trim_text(text, terms)}")
    for i, a in enumerate(retrieval_result["assets"], 1):
        blocks.append(
            f"[A{i}] EXTRACTED ASSET ({a.get('asset_type', 'asset')}, "
            f"mock-extraction hint) — source_file: {a['source_file']} | "
            f"chunk_id: {a['chunk_id']}\n\"{a.get('text', '')}\"")
    return "\n\n".join(blocks)


def short_excerpt(source, max_chars=300):
    text = source.get("excerpt") or source.get("text") or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars] + ("…" if len(text) > max_chars else "")
