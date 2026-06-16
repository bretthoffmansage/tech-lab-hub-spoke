#!/usr/bin/env python3
"""Marketing Intelligence Extraction v1 — extraction runner.

Processes LLM packets (processed/extracted_insights/llm_packets.jsonl) into
structured marketing-intelligence records
(database/extracted_marketing_insights.jsonl).

Providers:
  mock      (default) — no API, no keys, standard library only. Builds a
            conservative placeholder extraction from the packet text and its
            heuristic basic_signals. Good enough to validate schema, file
            writing, resume behavior, reports, and search integration.
  anthropic — requires `pip install anthropic` and ANTHROPIC_API_KEY.
  openai    — requires `pip install openai` and OPENAI_API_KEY.

Usage:
  python3 scripts/extract_marketing_insights.py                 # config defaults
  python3 scripts/extract_marketing_insights.py --provider mock --max-packets 10
  python3 scripts/extract_marketing_insights.py --overwrite
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, read_jsonl, write_json, write_text_report,
)

LLM_CONFIG_PATH = PROJECT_ROOT / "config" / "llm_extraction_config.json"

LIST_FIELDS = [
    "subtopics", "client_pain_points", "client_desires", "client_objections",
    "beliefs_challenged", "mistakes_identified", "better_questions",
    "frameworks_or_models", "stories_or_examples", "metaphors_or_phrases",
    "quotable_lines", "right_fit_client_questions", "content_hooks",
    "youtube_angles", "short_form_angles", "email_angles",
    "sales_page_angles", "offer_positioning_notes", "audience_segments",
    "tags", "extraction_warnings",
]
REQUIRED_FIELDS = [
    "record_id", "source_file", "cleaned_file", "transcript_title",
    "inferred_date", "chunk_id", "chunk_index", "extraction_schema_version",
    "source_text_excerpt", "core_topic", "usefulness_score",
    "confidence_score", "grounding_notes", "extraction_provider",
    "extraction_model", "extracted_at",
] + LIST_FIELDS


class ProviderError(Exception):
    """Raised when a real provider cannot be used. Message explains why."""


# ---------------------------------------------------------------- mock mode

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")
DESIRE_RE = re.compile(
    r"\b(want to|wanted to|i want|we want|the goal is|your goal|dream|"
    r"wish|so that you can|be able to)\b", re.IGNORECASE)
STORY_RE = re.compile(
    r"\b(for example|for instance|one of our|a client of|let me show you|"
    r"here's an example|true story|when i first)\b", re.IGNORECASE)
FRAMEWORK_RE = re.compile(
    r"\b(framework|the process is|step one|first step|three steps|"
    r"the model|the formula|the system is)\b", re.IGNORECASE)
OFFER_RE = re.compile(
    r"\b(offer|pricing|price point|high ticket|positioning|package|"
    r"enroll|enrollment)\b", re.IGNORECASE)

MAX_ITEMS = 8


def split_sentences(text, max_chars=400):
    out = []
    for para in text.split("\n\n"):
        for s in SENTENCE_SPLIT_RE.split(para.strip()):
            s = s.strip()
            if 15 <= len(s) <= max_chars:
                out.append(s)
    return out


def mock_extract(packet, config):
    """Conservative placeholder extraction: only verbatim sentences from the
    chunk, routed by the packet's heuristic basic_signals plus a few simple
    patterns. Never invents content. Real extraction will rewrite these into
    polished marketing assets; mock mode exists to validate the pipeline."""
    text = packet["text"]
    sentences = split_sentences(text)
    bs = packet.get("basic_signals") or {}
    signals = bs.get("signals") or {}

    def take(items):
        return list(dict.fromkeys(items))[:MAX_ITEMS]

    questions = take(signals.get("questions", []))
    hooks = take(signals.get("hooks", []))
    you_questions = [q for q in questions if re.search(r"\byou\b", q.lower())]

    term_counts = signals.get("strategic_term_counts", {})
    top_terms = sorted(term_counts.items(), key=lambda kv: -kv[1])
    core_topic = top_terms[0][0] if top_terms else None

    excerpt = re.sub(r"\s+", " ", text)[:300].strip()
    usefulness = bs.get("potential_usefulness_score", 1)

    return {
        "record_id": f"{packet['chunk_id']}__extract_v1",
        "source_file": packet["source_file"],
        "cleaned_file": packet["cleaned_file"],
        "transcript_title": packet["transcript_title"],
        "inferred_date": packet["inferred_date"],
        "chunk_id": packet["chunk_id"],
        "chunk_index": packet["chunk_index"],
        "extraction_schema_version": config["extraction_schema_version"],
        "source_text_excerpt": excerpt,

        "core_topic": core_topic,
        "subtopics": [t for t, _ in top_terms[1:6]],
        "client_pain_points": take(signals.get("pain_points", [])),
        "client_desires": take(s for s in sentences if DESIRE_RE.search(s)),
        "client_objections": take(signals.get("objections", [])),
        "beliefs_challenged": [],
        "mistakes_identified": take(signals.get("mistakes", [])),
        "better_questions": take(
            q for q in questions
            if re.match(r"(?i)\s*(why|what if|how do you|how can you|what would)", q)
        ),
        "frameworks_or_models": take(s for s in sentences if FRAMEWORK_RE.search(s)),
        "stories_or_examples": take(s for s in sentences if STORY_RE.search(s)),
        "metaphors_or_phrases": [],
        "quotable_lines": take(signals.get("teaching_points", [])),

        "right_fit_client_questions": take(you_questions),
        "content_hooks": hooks,
        "youtube_angles": hooks[:3],
        "short_form_angles": hooks[:3],
        "email_angles": hooks[:3],
        "sales_page_angles": [],
        "offer_positioning_notes": take(s for s in sentences if OFFER_RE.search(s)),
        "audience_segments": [],
        "tags": sorted(term_counts.keys()),

        "usefulness_score": int(usefulness),
        "confidence_score": 0.3,
        "grounding_notes": (
            "Mock heuristic extraction: every item is a verbatim sentence "
            "from the chunk, routed by keyword signals. No rewriting, no "
            "inference. Angle fields reuse hook sentences as placeholders."
        ),
        "extraction_warnings": ["mock_mode_placeholder_extraction"],
        "extraction_provider": "mock",
        "extraction_model": "mock",
        "extracted_at": now_iso(),
    }


# ----------------------------------------------------------- real providers

def build_llm_prompt(packet, config):
    prompt_path = PROJECT_ROOT / config["prompt_path"]
    template = prompt_path.read_text(encoding="utf-8")
    packet_json = json.dumps(
        {k: packet[k] for k in (
            "packet_id", "chunk_id", "source_file", "cleaned_file",
            "transcript_title", "inferred_date", "chunk_index", "text",
            "basic_signals")},
        ensure_ascii=False, indent=2,
    )
    return f"{template}\n\n## Packet\n\n```json\n{packet_json}\n```\n"


def parse_llm_json(raw_text):
    """Parse an LLM response that should be a single JSON object."""
    text = raw_text.strip()
    # tolerate accidental code fences despite instructions
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model response")
    return json.loads(text[start:end + 1])


def anthropic_extract(packet, config):
    key_var = config["api_key_env_vars"]["anthropic"]
    if not os.environ.get(key_var):
        raise ProviderError(
            f"Provider 'anthropic' selected but {key_var} is not set. "
            "Export the key or use --provider mock.")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        raise ProviderError(
            "Provider 'anthropic' selected but the 'anthropic' package is "
            "not installed. Run: pip install anthropic  (or use --provider mock)")
    client = anthropic.Anthropic()
    model = config.get("model")
    if not model or model == "mock":
        model = config["provider_models"]["anthropic"]
    response = client.messages.create(
        model=model,
        max_tokens=int(config["max_output_tokens"]),
        temperature=float(config["temperature"]),
        messages=[{"role": "user", "content": build_llm_prompt(packet, config)}],
    )
    record = parse_llm_json(response.content[0].text)
    record["extraction_provider"] = "anthropic"
    record["extraction_model"] = model
    record.setdefault("extracted_at", now_iso())
    return record


def openai_extract(packet, config):
    key_var = config["api_key_env_vars"]["openai"]
    if not os.environ.get(key_var):
        raise ProviderError(
            f"Provider 'openai' selected but {key_var} is not set. "
            "Export the key or use --provider mock.")
    try:
        import openai  # noqa: F401
    except ImportError:
        raise ProviderError(
            "Provider 'openai' selected but the 'openai' package is not "
            "installed. Run: pip install openai  (or use --provider mock)")
    client = openai.OpenAI()
    model = config.get("model")
    if not model or model == "mock":
        model = config["provider_models"]["openai"]
    response = client.chat.completions.create(
        model=model,
        max_tokens=int(config["max_output_tokens"]),
        temperature=float(config["temperature"]),
        messages=[{"role": "user", "content": build_llm_prompt(packet, config)}],
    )
    record = parse_llm_json(response.choices[0].message.content)
    record["extraction_provider"] = "openai"
    record["extraction_model"] = model
    record.setdefault("extracted_at", now_iso())
    return record


PROVIDERS = {
    "mock": mock_extract,
    "anthropic": anthropic_extract,
    "openai": openai_extract,
}


# ------------------------------------------------------------- validation

def validate_record(record, packet, config):
    """Return a list of problems (empty list = valid)."""
    problems = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            problems.append(f"missing field: {field}")
    for field in LIST_FIELDS:
        if field in record and not isinstance(record[field], list):
            problems.append(f"{field} must be a list")
    # traceability must match the packet exactly
    for field in ("source_file", "cleaned_file", "transcript_title",
                  "inferred_date", "chunk_id", "chunk_index"):
        if field in record and record[field] != packet[field]:
            problems.append(f"traceability field altered: {field}")
    score = record.get("usefulness_score")
    if not (isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 5):
        problems.append("usefulness_score must be an integer 0-5")
    conf = record.get("confidence_score")
    if not (isinstance(conf, (int, float)) and not isinstance(conf, bool)
            and 0 <= conf <= 1):
        problems.append("confidence_score must be a number 0-1")
    for key in record:
        kl = key.lower()
        if "speaker" in kl or "timestamp" in kl:
            problems.append(f"forbidden field present: {key}")
    return problems


# -------------------------------------------------------------------- main

def load_llm_config():
    with open(LLM_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Extract marketing intelligence from LLM packets.")
    parser.add_argument("--provider", choices=sorted(PROVIDERS),
                        help="Override config provider (default: config value)")
    parser.add_argument("--max-packets", type=int, dest="max_packets",
                        help="Process at most N packets (test runs)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace any existing output file")
    parser.add_argument("--resume", dest="resume", action="store_true",
                        default=None, help="Skip chunk_ids already extracted")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                        help="Disable resume (with existing output and no "
                             "--overwrite, this aborts to protect the file)")
    args = parser.parse_args()

    config = load_llm_config()
    provider = args.provider or config.get("provider", "mock")
    max_packets = args.max_packets if args.max_packets is not None \
        else config.get("max_packets")
    overwrite = args.overwrite or config.get("overwrite", False)
    resume = args.resume if args.resume is not None else config.get("resume", True)
    min_keep = int(config.get("min_usefulness_to_keep", 0))

    extract_fn = PROVIDERS[provider]
    input_path = PROJECT_ROOT / config["input_packets_path"]
    output_path = PROJECT_ROOT / config["output_path"]
    failures_path = PROJECT_ROOT / config["failures_path"]
    reports_dir = PROJECT_ROOT / config["reports_dir"]

    if not input_path.exists():
        print(f"Missing input packets: {input_path}")
        print("Run python3 scripts/run_pipeline.py first.")
        return 1

    # fail fast on provider problems BEFORE touching any output files
    if provider != "mock":
        try:
            key_var = config["api_key_env_vars"][provider]
            if not os.environ.get(key_var):
                raise ProviderError(
                    f"Provider '{provider}' selected but {key_var} is not set. "
                    "Export the key or use --provider mock.")
            __import__(provider)
        except ProviderError as e:
            print(f"PROVIDER ERROR: {e}")
            print("No output files were modified.")
            return 1
        except ImportError:
            print(f"PROVIDER ERROR: the '{provider}' package is not installed. "
                  f"Run: pip install {provider}  (or use --provider mock)")
            print("No output files were modified.")
            return 1

    packets = read_jsonl(input_path)
    print(f"Loaded {len(packets)} packets. Provider: {provider}")

    existing_ids = set()
    if output_path.exists():
        if overwrite:
            output_path.unlink()
            print("Overwrite enabled: removed existing output file.")
        elif resume:
            existing_ids = {r["chunk_id"] for r in read_jsonl(output_path)}
            print(f"Resume: {len(existing_ids)} chunk_ids already extracted; skipping them.")
        else:
            print(f"Output exists at {output_path} and neither --resume nor "
                  "--overwrite is enabled. Aborting to protect existing data.")
            return 1

    todo = [p for p in packets if p["chunk_id"] not in existing_ids]
    if max_packets is not None:
        todo = todo[:max_packets]
    print(f"Processing {len(todo)} packet(s) ...")

    written = filtered = failed = 0
    failures = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as out:
        for i, packet in enumerate(todo, 1):
            try:
                record = extract_fn(packet, config)
                problems = validate_record(record, packet, config)
                if problems:
                    raise ValueError("; ".join(problems))
                if record["usefulness_score"] < min_keep:
                    filtered += 1
                else:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
            except ProviderError as e:
                print(f"\nPROVIDER ERROR: {e}")
                print("Stopping. Already-written records are preserved; "
                      "rerun with resume to continue.")
                break
            except Exception as e:  # noqa: BLE001 — record and continue
                failed += 1
                failures.append({
                    "chunk_id": packet["chunk_id"],
                    "source_file": packet["source_file"],
                    "provider": provider,
                    "error": str(e),
                    "failed_at": now_iso(),
                })
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} processed "
                      f"({written} written, {filtered} filtered, {failed} failed)")

    if failures:
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        with open(failures_path, "a", encoding="utf-8") as f:
            for rec in failures:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_records = len(read_jsonl(output_path)) if output_path.exists() else 0
    report = {
        "generated_at": now_iso(),
        "provider": provider,
        "model": "mock" if provider == "mock" else config.get("model"),
        "packets_total": len(packets),
        "packets_skipped_resume": len(packets) - len(
            [p for p in packets if p["chunk_id"] not in existing_ids]),
        "packets_processed": len(todo),
        "records_written_this_run": written,
        "records_filtered_low_usefulness": filtered,
        "min_usefulness_to_keep": min_keep,
        "failures_this_run": failed,
        "total_records_in_output": total_records,
        "output_path": str(output_path.relative_to(PROJECT_ROOT)),
        "mock_mode": provider == "mock",
    }
    write_json(reports_dir / "marketing_extraction_report.json", report)
    lines = [
        "# Marketing Extraction Report", "",
        f"Generated: {report['generated_at']}", "",
        f"- Provider: **{provider}**" + (" (placeholder extraction — items are "
          "verbatim sentences routed by keyword signals)" if provider == "mock" else ""),
        f"- Packets available: {report['packets_total']}",
        f"- Skipped via resume: {report['packets_skipped_resume']}",
        f"- Processed this run: {report['packets_processed']}",
        f"- Records written this run: **{written}**",
        f"- Filtered (usefulness < {min_keep}): {filtered}",
        f"- Failures this run: {failed}" + (
            " (see `marketing_extraction_failures.jsonl`)" if failed else ""),
        f"- Total records now in output: **{total_records}**",
        f"- Output: `{report['output_path']}`",
    ]
    if provider == "mock":
        lines += ["", "> MOCK MODE: these records validate the pipeline "
                  "(schema, resume, reports, search). Re-run with a real "
                  "provider to produce polished marketing assets."]
    write_text_report(reports_dir / "marketing_extraction_report.md",
                      "\n".join(lines) + "\n")

    print(f"\nDone. {written} written, {filtered} filtered, {failed} failed. "
          f"Output now holds {total_records} records.")
    print(f"Report -> {reports_dir / 'marketing_extraction_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
