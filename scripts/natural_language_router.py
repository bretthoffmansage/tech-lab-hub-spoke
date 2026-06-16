#!/usr/bin/env python3
"""Natural-language router for the Tech Lab Transcript Intelligence demo.

Classifies a plain-English request into a supported intent, extracts the
topic phrase / asset type / search phrase, and resolves topics to the
closest configured topic. Transparent keyword matching only — no ML, and it
never pretends to be semantic understanding.

Importable API (used by app.py):
    route_request(text, current_topic_key=None) -> dict
    resolve_topic_phrase(phrase)                -> dict | None
    load_topic_index()                          -> dict | None
    top_topic_options(n=8, exclude=None)        -> list[dict]

CLI test mode:
    python3 scripts/natural_language_router.py "Give me hooks from webinar conversion"
    python3 scripts/natural_language_router.py "Give me hooks" --topic right_fit_client
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from topic_lib import (  # noqa: E402
    TOPIC_INDEX_PATH, load_topic_config, normalize,
)

WEAK_CHUNK_THRESHOLD = 10     # topics with fewer matching chunks are "thin"
MIN_TOPIC_SCORE = 0.55        # below this, a phrase does not resolve to a topic

INTENTS = [
    "discover_topics", "build_topic_pack", "get_questions", "get_hooks",
    "get_pain_points", "get_desires", "get_objections", "get_beliefs_mistakes",
    "get_content_angles", "get_youtube_angles", "get_short_form_angles",
    "get_email_angles", "get_sales_page_angles", "get_offer_notes",
    "get_quotes", "get_source_excerpts", "search_transcripts",
    "export_assets", "related_topics", "help", "unknown",
]

# how each asset intent maps onto topic-pack sections (used by the app)
ASSET_INTENT_SECTIONS = {
    "get_questions": {"section": "right_fit_client_questions", "fields": None,
                      "title": "Right-Fit-Client Questions"},
    "get_hooks": {"section": "hooks_quotables",
                  "fields": ["content_hooks", "metaphors_or_phrases"],
                  "title": "Hooks"},
    "get_quotes": {"section": "hooks_quotables", "fields": ["quotable_lines"],
                   "title": "Quotable Lines"},
    "get_pain_points": {"section": "pain_points", "fields": None,
                        "title": "Pain Points"},
    "get_desires": {"section": "client_desires", "fields": None,
                    "title": "Client Desires"},
    "get_objections": {"section": "objections_pushback", "fields": None,
                       "title": "Objections and Pushback"},
    "get_beliefs_mistakes": {"section": "beliefs_mistakes", "fields": None,
                             "title": "Beliefs Challenged / Mistakes"},
    "get_youtube_angles": {"section": "youtube_angles", "fields": None,
                           "title": "YouTube Angles"},
    "get_short_form_angles": {"section": "short_form_angles", "fields": None,
                              "title": "Short-Form Angles"},
    "get_email_angles": {"section": "email_angles", "fields": None,
                         "title": "Email Angles"},
    "get_sales_page_angles": {"section": "sales_page_angles", "fields": None,
                              "title": "Sales-Page Angles"},
    "get_offer_notes": {"section": "offer_positioning", "fields": None,
                        "title": "Offer Positioning Notes"},
}

# asset vocabulary for scripts/export_topic_assets.py
EXPORT_TYPE_BY_INTENT = {
    "get_questions": "questions", "get_hooks": "hooks",
    "get_pain_points": "pain_points", "get_objections": "objections",
    "get_youtube_angles": "youtube_angles",
    "get_short_form_angles": "short_form_angles",
    "get_email_angles": "email_angles", "get_offer_notes": "offer_notes",
    "get_quotes": "quotes",
}

PRONOUN_PHRASES = {"that", "this", "it", "this topic", "that topic",
                   "this one", "the current topic", "current topic"}

PREP_RE = re.compile(
    r"\b(?:about|on|from|for|around|regarding)\s+(.+?)\s*$")
SEARCH_PATTERNS = [
    re.compile(r"search (?:the )?transcripts? for (.+)$"),
    re.compile(r"search for (.+)$"),
    re.compile(r"search (.+)$"),
    re.compile(r"find where (?:the |they |transcripts? )*(?:talk about |mention |say about )?(.+)$"),
    re.compile(r"what do the transcripts say about (.+)$"),
    re.compile(r"is there anything (?:about |on )?(.+)$"),
    re.compile(r"find (.+)$"),
]


# ----------------------------------------------------------- topic matching

def _stem(token):
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _tokens(text):
    return {_stem(t) for t in normalize(text).split()}


def load_topic_index():
    if TOPIC_INDEX_PATH.exists():
        return json.loads(TOPIC_INDEX_PATH.read_text(encoding="utf-8"))
    return None


def top_topic_options(n=8, exclude=None):
    """Top topics by chunk coverage, for fallback suggestions."""
    index = load_topic_index()
    if index:
        topics = [
            {"topic_key": k, "display_name": t["display_name"],
             "matching_chunks": t.get("matching_chunks", 0)}
            for k, t in index.get("topics", {}).items() if k != exclude
        ]
        topics.sort(key=lambda t: -t["matching_chunks"])
        return topics[:n]
    config = load_topic_config()
    return [{"topic_key": k, "display_name": t["display_name"],
             "matching_chunks": None}
            for k, t in list(config["topic_aliases"].items())[:n]
            if k != exclude]


def resolve_topic_phrase(phrase):
    """Closest-match topic resolution. Returns None when nothing is close.

    Match levels (most to least confident):
      exact   — phrase equals a key/display name/alias        (score 1.0)
      alias   — phrase contains a multi-word alias            (score 0.9)
      partial — single-word alias, or >=50% alias-token overlap (0.55-0.7)
    Scores below MIN_TOPIC_SCORE do not resolve.
    """
    if not phrase or not phrase.strip():
        return None
    config = load_topic_config()
    pn = normalize(phrase)
    ptoks = _tokens(phrase)
    if not ptoks:
        return None

    best = None
    for key, topic in config["topic_aliases"].items():
        candidates = ([key.replace("_", " "), topic["display_name"]]
                      + topic["aliases"])
        for cand in candidates:
            cn = normalize(cand)
            ctoks = _tokens(cand)
            if not ctoks:
                continue
            if pn == cn:
                score, level = 1.0, "exact"
                why = f'phrase equals "{cand}"'
            elif ctoks <= ptoks:
                if len(ctoks) > 1:
                    score, level = 0.9, "alias"
                    why = f'phrase contains alias "{cand}"'
                else:
                    score, level = 0.7, "partial"
                    why = f'keyword overlap on "{cand}"'
            else:
                shared = ctoks & ptoks
                ratio = len(shared) / len(ctoks)
                if shared and ratio >= 0.5:
                    score = 0.4 + 0.3 * ratio  # 0.55 .. 0.7
                    level = "partial"
                    why = (f'partial overlap with alias "{cand}" '
                           f'({", ".join(sorted(shared))})')
                else:
                    continue
            if best is None or score > best["score"]:
                best = {"topic_key": key,
                        "display_name": topic["display_name"],
                        "score": round(score, 2),
                        "match_level": level,
                        "match_reason": why}

    if best is None or best["score"] < MIN_TOPIC_SCORE:
        return None

    # enrich with archive coverage so weak topics can be flagged honestly
    index = load_topic_index()
    if index:
        entry = index.get("topics", {}).get(best["topic_key"])
        if entry:
            chunks = entry.get("matching_chunks", 0)
            best["matching_chunks"] = chunks
            best["matching_source_files"] = entry.get("matching_source_files")
            best["weak"] = chunks < WEAK_CHUNK_THRESHOLD
            if best["weak"]:
                best["stronger_alternatives"] = [
                    t["display_name"]
                    for t in top_topic_options(4, exclude=best["topic_key"])
                ]
    best.setdefault("matching_chunks", None)
    best.setdefault("weak", False)
    best.setdefault("stronger_alternatives", [])
    return best


# -------------------------------------------------------- intent + phrases

def _extract_topic_phrase(text):
    n = normalize(text)
    m = PREP_RE.search(n)
    if m:
        phrase = m.group(1).strip()
        phrase = re.sub(r"^(?:the|a|an|my|our|this|these)\s+", "", phrase)
        return phrase or None
    return None


def _extract_search_phrase(text):
    n = normalize(text)
    for pattern in SEARCH_PATTERNS:
        m = pattern.search(n)
        if m:
            phrase = m.group(1).strip()
            phrase = re.sub(r"^(?:the|a|an)\s+", "", phrase)
            return phrase or None
    return None


def _extract_limit(text):
    m = re.search(r"\b(\d{1,3})\b", text)
    return int(m.group(1)) if m else None


def _detect_asset_type(n_padded):
    """Detect an export-style asset type mentioned anywhere in the text."""
    def has(*phrases):
        return any(f" {p} " in n_padded for p in phrases)
    if has("youtube"):
        return "youtube_angles"
    if " short form " in n_padded or has("shorts", "reels", "tiktok"):
        return "short_form_angles"
    if " email angle " in n_padded or " email angles " in n_padded or \
            (has("email", "emails") and has("angle", "angles", "idea", "ideas")):
        return "email_angles"
    if has("quote", "quotes", "quotable"):
        return "quotes"
    if has("objection", "objections", "pushback"):
        return "objections"
    if " pain point " in n_padded or " pain points " in n_padded or has("pains"):
        return "pain_points"
    if has("hook", "hooks"):
        return "hooks"
    if has("question", "questions"):
        return "questions"
    if " offer note " in n_padded or " offer notes " in n_padded or \
            " positioning notes " in n_padded:
        return "offer_notes"
    if has("everything", "all"):
        return "all"
    return None


def classify_intent(text):
    """Returns (intent, base_confidence, reason). First matching rule wins."""
    n = normalize(text)
    padded = f" {n} "

    def has(*phrases):
        return any(f" {p} " in padded for p in phrases)

    if n in ("help", "example", "examples") or "how do i use" in n or \
            n == "what can i ask":
        return "help", 0.95, "help keyword"
    if has("related") or "what else" in n or "nearby topics" in n or \
            "similar topics" in n:
        return "related_topics", 0.9, "asked for related/nearby topics"
    if has("export", "download") or "save this" in n:
        return "export_assets", 0.9, "export/download keyword"
    if has("search") or "find where" in n or \
            "what do the transcripts say" in n or "is there anything" in n or \
            ("transcript" in n and has("find")):
        return "search_transcripts", 0.9, "raw transcript search phrasing"
    if has("source", "sources", "excerpt", "excerpts", "receipts"):
        return "get_source_excerpts", 0.9, "asked for sources/excerpts"
    if has("topic", "topics") and has(
            "what", "which", "show", "list", "available", "have", "ask"):
        return "discover_topics", 0.95, "asked what topics exist"
    if has("youtube"):
        return "get_youtube_angles", 0.9, "asked for YouTube angles"
    if " short form " in padded or has("shorts", "reels", "tiktok"):
        return "get_short_form_angles", 0.9, "asked for short-form angles"
    if " email angle " in padded or " email angles " in padded or \
            (has("email", "emails") and has("angle", "angles", "idea", "ideas")):
        return "get_email_angles", 0.9, "asked for email angles"
    if " sales page " in padded:
        return "get_sales_page_angles", 0.9, "asked for sales-page angles"
    if has("angle", "angles"):
        return "get_content_angles", 0.85, "asked for content angles"
    if has("objection", "objections", "pushback", "resistance", "hesitation"):
        return "get_objections", 0.9, "asked for objections"
    if has("question", "questions"):
        return "get_questions", 0.9, "asked for questions"
    if has("hook", "hooks"):
        return "get_hooks", 0.9, "asked for hooks"
    if " pain point " in padded or " pain points " in padded or \
            has("pains", "struggles"):
        return "get_pain_points", 0.9, "asked for pain points"
    if has("desire", "desires", "dreams") or " what do clients want " in padded:
        return "get_desires", 0.9, "asked for desires"
    if has("belief", "beliefs", "mistake", "mistakes", "misconception",
           "misconceptions"):
        return "get_beliefs_mistakes", 0.9, "asked for beliefs/mistakes"
    if has("quote", "quotes", "quotable"):
        return "get_quotes", 0.9, "asked for quotable lines"
    if " offer note " in padded or " offer notes " in padded or \
            " positioning notes " in padded:
        return "get_offer_notes", 0.9, "asked for offer notes"
    if has("everything") or " topic pack " in padded or \
            "what do we have" in n or "what do you have" in n or \
            "tell me about" in n or "all useful" in n or \
            "all the information" in n or "build a pack" in n:
        return "build_topic_pack", 0.85, "asked for everything on a topic"
    return "unknown", 0.2, "no intent keyword matched"


ASSET_INTENTS = set(ASSET_INTENT_SECTIONS) | {"get_content_angles"}
TOPIC_INTENTS = ASSET_INTENTS | {
    "build_topic_pack", "related_topics", "get_source_excerpts",
    "export_assets"}

# words to ignore when trying to read a topic out of the full request text,
# so "give me hooks" never resolves to a topic via the word "hooks" itself
GENERIC_STRIP = {
    "give", "me", "show", "get", "pull", "list", "want", "need", "please",
    "now", "the", "a", "an", "some", "all", "my", "our", "us", "can", "you",
    "i", "what", "do", "does", "we", "have", "has", "of", "to", "in", "with",
    "for", "from", "about", "on", "around", "like", "totally", "unrelated",
    "something", "useful", "information", "everything", "topic", "topics",
    "pack", "related", "else", "explore", "next", "export", "download",
    "save", "build", "this", "that", "it",
}
INTENT_STRIP = {
    "get_questions": {"question", "questions"},
    "get_hooks": {"hook", "hooks"},
    "get_pain_points": {"pain", "point", "points", "pains", "struggles"},
    "get_desires": {"desire", "desires", "dreams"},
    "get_objections": {"objection", "objections", "pushback", "resistance",
                       "hesitation"},
    "get_beliefs_mistakes": {"belief", "beliefs", "mistake", "mistakes",
                             "misconception", "misconceptions"},
    "get_content_angles": {"angle", "angles", "content"},
    "get_youtube_angles": {"youtube", "video", "videos", "angle", "angles"},
    "get_short_form_angles": {"short", "form", "shorts", "reels", "tiktok",
                              "angle", "angles"},
    "get_email_angles": {"email", "emails", "angle", "angles", "idea",
                         "ideas"},
    "get_sales_page_angles": {"sales", "page", "angle", "angles"},
    "get_offer_notes": {"note", "notes", "positioning"},
    "get_quotes": {"quote", "quotes", "quotable"},
    "get_source_excerpts": {"source", "sources", "excerpt", "excerpts",
                            "receipts"},
    "related_topics": {"related", "similar", "nearby"},
    "export_assets": {"question", "questions", "hook", "hooks", "quote",
                      "quotes", "objection", "objections", "pain", "point",
                      "points", "note", "notes", "angle", "angles",
                      "youtube", "email", "emails", "short", "form"},
}


def _strip_intent_words(text, intent):
    """Remove intent/asset vocabulary, keep only candidate topic words."""
    drop = {_stem(w) for w in GENERIC_STRIP | INTENT_STRIP.get(intent, set())}
    kept = [t for t in normalize(text).split() if _stem(t) not in drop]
    return " ".join(kept)


def route_request(text, current_topic_key=None):
    """Classify a request and resolve its topic. Pure function, no I/O writes."""
    text = (text or "").strip()
    intent, base_conf, reason = classify_intent(text)
    n = normalize(text)
    padded = f" {n} "

    search_phrase = _extract_search_phrase(text) \
        if intent == "search_transcripts" else None
    topic_phrase = _extract_topic_phrase(text)
    requested_limit = _extract_limit(text)
    asset_type = _detect_asset_type(padded)

    topic = None
    needs_topic = False
    use_current = False
    phrase_failed = False
    if intent in TOPIC_INTENTS:
        if topic_phrase and normalize(topic_phrase) in PRONOUN_PHRASES:
            topic_phrase, use_current = None, True
        if topic_phrase:
            topic = resolve_topic_phrase(topic_phrase)
            if topic is None:
                # an explicit phrase that doesn't resolve is a real "no
                # match" — never silently substitute the current topic
                phrase_failed = True
                needs_topic = True
                reason += f'; no configured topic matched "{topic_phrase}"'
        elif not use_current:
            # no explicit phrase — try the text minus intent vocabulary
            cleaned = _strip_intent_words(text, intent)
            if cleaned:
                topic = resolve_topic_phrase(cleaned)
        if topic is None and not phrase_failed:
            if current_topic_key:
                config = load_topic_config()
                entry = config["topic_aliases"].get(current_topic_key)
                if entry:
                    topic = resolve_topic_phrase(entry["display_name"])
                    if topic:
                        topic["match_level"] = "current_topic"
                        topic["match_reason"] = "using the current session topic"
                        reason += "; used current topic"
            if topic is None:
                needs_topic = True

    # unknown intent: if the text clearly names a topic, treat as a pack request
    if intent == "unknown":
        topic = resolve_topic_phrase(topic_phrase or text)
        if topic and topic["score"] >= MIN_TOPIC_SCORE:
            intent = "build_topic_pack"
            base_conf = 0.6
            reason = ("no explicit intent keyword; topic matched, "
                      "defaulting to topic pack")
        else:
            topic = None

    confidence = base_conf
    if intent in TOPIC_INTENTS:
        if topic:
            confidence = round(min(base_conf, 0.4 + 0.6 * topic["score"]), 2)
        elif needs_topic:
            confidence = round(base_conf * 0.5, 2)

    return {
        "input": text,
        "intent": intent,
        "confidence": confidence,
        "reason": reason,
        "requested_topic_phrase": topic_phrase,
        "requested_asset_type": asset_type,
        "requested_limit": requested_limit,
        "search_phrase": search_phrase,
        "export_requested": intent == "export_assets",
        "needs_topic": needs_topic,
        "topic": topic,
        "fallback_options": [t["display_name"] for t in top_topic_options(8)],
        "method_note": "keyword/phrase matching, not semantic understanding",
    }


def main():
    args = [a for a in sys.argv[1:]]
    current = None
    if "--topic" in args:
        i = args.index("--topic")
        current = args[i + 1]
        args = args[:i] + args[i + 2:]
    text = " ".join(args) or "help"
    print(json.dumps(route_request(text, current_topic_key=current),
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
