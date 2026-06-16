#!/usr/bin/env python3
"""Validate database/extracted_marketing_insights.jsonl against the schema in
docs/marketing_extraction_schema_v1.md.

Checks: JSON validity, required fields, types, score ranges, traceability
fields, forbidden speaker/timestamp fields, duplicate record_ids/chunk_ids.

Writes processed/reports/marketing_insights_validation_report.{md,json}.
Exit code 0 when valid, 1 when any errors are found.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, write_json, write_text_report,
)

INSIGHTS_PATH = PROJECT_ROOT / "database" / "extracted_marketing_insights.jsonl"
REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"
MAX_ERRORS_LISTED = 50

LIST_FIELDS = [
    "subtopics", "client_pain_points", "client_desires", "client_objections",
    "beliefs_challenged", "mistakes_identified", "better_questions",
    "frameworks_or_models", "stories_or_examples", "metaphors_or_phrases",
    "quotable_lines", "right_fit_client_questions", "content_hooks",
    "youtube_angles", "short_form_angles", "email_angles",
    "sales_page_angles", "offer_positioning_notes", "audience_segments",
    "tags", "extraction_warnings",
]
STRING_FIELDS = [
    "record_id", "source_file", "cleaned_file", "transcript_title",
    "chunk_id", "extraction_schema_version", "source_text_excerpt",
    "extraction_provider", "extraction_model", "extracted_at",
]
REQUIRED_FIELDS = STRING_FIELDS + LIST_FIELDS + [
    "inferred_date", "chunk_index", "core_topic",
    "usefulness_score", "confidence_score", "grounding_notes",
]


def validate_record(record):
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
    for field in STRING_FIELDS:
        value = record.get(field)
        if field in record and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{field} must be a non-empty string")
    for field in LIST_FIELDS:
        value = record.get(field)
        if field in record:
            if not isinstance(value, list):
                errors.append(f"{field} must be a list")
            elif not all(isinstance(x, str) for x in value):
                errors.append(f"{field} must contain only strings")
    if "chunk_index" in record and not (
            isinstance(record["chunk_index"], int)
            and not isinstance(record["chunk_index"], bool)):
        errors.append("chunk_index must be an integer")
    score = record.get("usefulness_score")
    if "usefulness_score" in record and not (
            isinstance(score, int) and not isinstance(score, bool)
            and 0 <= score <= 5):
        errors.append(f"usefulness_score out of range: {score!r}")
    conf = record.get("confidence_score")
    if "confidence_score" in record and not (
            isinstance(conf, (int, float)) and not isinstance(conf, bool)
            and 0 <= conf <= 1):
        errors.append(f"confidence_score out of range: {conf!r}")
    for key in record:
        kl = key.lower()
        if "speaker" in kl or "timestamp" in kl:
            errors.append(f"forbidden field present: {key}")
    return errors


def main():
    if not INSIGHTS_PATH.exists():
        print(f"Nothing to validate: {INSIGHTS_PATH} does not exist.")
        print("Run python3 scripts/extract_marketing_insights.py first.")
        return 1

    line_errors = []     # (line_number, record_id_or_None, [errors])
    invalid_json = 0
    records = []
    with open(INSIGHTS_PATH, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                invalid_json += 1
                line_errors.append((n, None, [f"invalid JSON: {e}"]))
                continue
            errs = validate_record(record)
            if errs:
                line_errors.append((n, record.get("record_id"), errs))
            records.append(record)

    record_id_dupes = [k for k, c in Counter(
        r.get("record_id") for r in records).items() if k and c > 1]
    chunk_id_dupes = [k for k, c in Counter(
        r.get("chunk_id") for r in records).items() if k and c > 1]

    providers = Counter(r.get("extraction_provider") for r in records)
    scores = Counter(r.get("usefulness_score") for r in records)

    schema_error_count = len(line_errors) - invalid_json
    total_errors = len(line_errors) + len(record_id_dupes) + len(chunk_id_dupes)
    valid = total_errors == 0

    report = {
        "generated_at": now_iso(),
        "input": str(INSIGHTS_PATH.relative_to(PROJECT_ROOT)),
        "total_lines_with_content": len(records) + invalid_json,
        "valid_records": len(records) - schema_error_count,
        "records_parsed": len(records),
        "invalid_json_lines": invalid_json,
        "records_with_schema_errors": schema_error_count,
        "duplicate_record_ids": record_id_dupes,
        "duplicate_chunk_ids": chunk_id_dupes,
        "providers": dict(providers),
        "usefulness_distribution": {str(k): v for k, v in sorted(
            scores.items(), key=lambda kv: str(kv[0]))},
        "overall_status": "VALID" if valid else "ERRORS_FOUND",
        "errors_sample": [
            {"line": n, "record_id": rid, "errors": errs}
            for n, rid, errs in line_errors[:MAX_ERRORS_LISTED]
        ],
    }
    write_json(REPORTS_DIR / "marketing_insights_validation_report.json", report)

    lines = [
        "# Marketing Insights Validation Report", "",
        f"Generated: {report['generated_at']}", "",
        f"**Overall status: {report['overall_status']}**", "",
        f"- Records parsed: **{len(records)}**",
        f"- Invalid JSON lines: {invalid_json}",
        f"- Records with schema errors: {report['records_with_schema_errors']}",
        f"- Duplicate record_ids: {len(record_id_dupes)}",
        f"- Duplicate chunk_ids: {len(chunk_id_dupes)}",
        f"- Providers: {dict(providers)}",
        f"- Usefulness distribution: {report['usefulness_distribution']}",
        "",
    ]
    if line_errors:
        lines += [f"## Errors (first {MAX_ERRORS_LISTED})", ""]
        for n, rid, errs in line_errors[:MAX_ERRORS_LISTED]:
            lines.append(f"- line {n} ({rid or 'unparseable'}): {'; '.join(errs)}")
        lines.append("")
    if record_id_dupes:
        lines += ["## Duplicate record_ids", ""] + [
            f"- `{d}`" for d in record_id_dupes[:MAX_ERRORS_LISTED]] + [""]
    if chunk_id_dupes:
        lines += ["## Duplicate chunk_ids", ""] + [
            f"- `{d}`" for d in chunk_id_dupes[:MAX_ERRORS_LISTED]] + [""]
    write_text_report(REPORTS_DIR / "marketing_insights_validation_report.md",
                      "\n".join(lines) + "\n")

    print(f"Validation: {report['overall_status']} — {len(records)} records, "
          f"{invalid_json} bad JSON lines, "
          f"{report['records_with_schema_errors']} schema-error records, "
          f"{len(record_id_dupes)} dup record_ids, "
          f"{len(chunk_id_dupes)} dup chunk_ids")
    print(f"Report -> {REPORTS_DIR / 'marketing_insights_validation_report.md'}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
