#!/usr/bin/env python3
"""Upload the generated demo data to Convex.

    python3 scripts/upload_to_convex.py

Uploads (idempotently, via external-ID upserts — safe to re-run):
  1. database/transcript_chunks.jsonl        -> transcriptChunks
  2. database/extracted_marketing_insights.jsonl -> marketingInsights
  3. SQLite marketing_assets (flattened)     -> marketingAssets (+ topicKeys)
  4. database/topic_index.json               -> topicIndex
  5. database/topic_packs/*.json             -> topicPacks
  6. agent_index/agent_manifest.json + counts -> appMetadata

Never uploads raw transcripts or cleaned full transcripts.
Requires: pip install convex   and CONVEX_URL in env or .env.local.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, read_jsonl, write_json, write_text_report,
)
from topic_lib import load_topic_config, topic_regex  # noqa: E402
from convex_lib import get_convex_client, to_convex_number  # noqa: E402

REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"
CHUNK_BATCH = 50
INSIGHT_BATCH = 40
ASSET_BATCH = 200


def opt_str(value):
    return value if isinstance(value, str) and value else None


def batch_upsert(client, table, payloads, batch_size, label):
    # v.optional() fields must be ABSENT, not null — drop None values
    payloads = [{k: v for k, v in p.items() if v is not None}
                for p in payloads]
    inserted = updated = 0
    for i in range(0, len(payloads), batch_size):
        batch = payloads[i:i + batch_size]
        result = client.mutation(
            "techLabDemo:batchUpsert", {"table": table, "records": batch})
        inserted += int(result["inserted"])
        updated += int(result["updated"])
        done = min(i + batch_size, len(payloads))
        print(f"  {label}: {done}/{len(payloads)} "
              f"({inserted} inserted, {updated} updated)")
    return {"total": len(payloads), "inserted": inserted, "updated": updated}


def chunk_topic_map(chunks):
    """chunk_id -> [topic_key, ...] via the same alias matching the
    discovery layer uses, so hosted topic filters agree with local ones."""
    config = load_topic_config()
    regexes = {k: topic_regex(t["aliases"])
               for k, t in config["topic_aliases"].items()}
    mapping = {}
    for c in chunks:
        keys = [k for k, rgx in regexes.items() if rgx.search(c["text"])]
        if keys:
            mapping[c["chunk_id"]] = keys
    return mapping


def main():
    client, err = get_convex_client()
    if client is None:
        print(f"CONVEX ERROR: {err}")
        return 1
    print(f"Uploading to Convex deployment at "
          f"{client.address if hasattr(client, 'address') else 'CONVEX_URL'}")

    counts = {}

    # 1. transcript chunks ---------------------------------------------------
    chunks_path = PROJECT_ROOT / "database" / "transcript_chunks.jsonl"
    chunks = read_jsonl(chunks_path)
    topic_map = chunk_topic_map(chunks)
    payloads = [{
        "chunkId": c["chunk_id"],
        "sourceFile": c["source_file"],
        "cleanedFile": opt_str(c.get("cleaned_file")),
        "transcriptTitle": c["transcript_title"],
        "inferredDate": opt_str(c.get("inferred_date")),
        "chunkIndex": to_convex_number(c["chunk_index"]),
        "wordCount": to_convex_number(c.get("word_count")),
        "text": c["text"],
        "fullRecord": {"topic_keys": topic_map.get(c["chunk_id"], [])},
    } for c in chunks]
    print(f"\n[1/6] Transcript chunks ({len(payloads)}) ...")
    counts["transcriptChunks"] = batch_upsert(
        client, "transcriptChunks", payloads, CHUNK_BATCH, "chunks")

    # 2. marketing insights --------------------------------------------------
    insights_path = PROJECT_ROOT / "database" / "extracted_marketing_insights.jsonl"
    insights = read_jsonl(insights_path)
    payloads = [{
        "recordId": r["record_id"],
        "chunkId": r["chunk_id"],
        "sourceFile": r["source_file"],
        "cleanedFile": opt_str(r.get("cleaned_file")),
        "transcriptTitle": r["transcript_title"],
        "inferredDate": opt_str(r.get("inferred_date")),
        "chunkIndex": to_convex_number(r.get("chunk_index", 0)),
        "coreTopic": opt_str(r.get("core_topic")),
        "usefulnessScore": to_convex_number(r.get("usefulness_score")),
        "confidenceScore": to_convex_number(r.get("confidence_score")),
        "extractionProvider": opt_str(r.get("extraction_provider")),
        "extractionModel": opt_str(r.get("extraction_model")),
        "tags": r.get("tags") or [],
        "fullRecord": r,
    } for r in insights]
    print(f"\n[2/6] Marketing insights ({len(payloads)}) ...")
    counts["marketingInsights"] = batch_upsert(
        client, "marketingInsights", payloads, INSIGHT_BATCH, "insights")

    # 3. marketing assets (prefer the already-flattened SQLite table) --------
    db_path = PROJECT_ROOT / "database" / "tech_lab_knowledge_base.sqlite"
    payloads = []
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT asset_id, record_id, chunk_id, source_file, "
            "transcript_title, inferred_date, asset_type, asset_text, "
            "usefulness_score, confidence_score, tags_json "
            "FROM marketing_assets").fetchall()
        conn.close()
        for (asset_id, record_id, chunk_id, source_file, title, date,
             asset_type, asset_text, usefulness, confidence, tags_json) in rows:
            payloads.append({
                "assetId": asset_id,
                "recordId": record_id,
                "chunkId": chunk_id,
                "sourceFile": source_file,
                "transcriptTitle": title,
                "inferredDate": opt_str(date),
                "assetType": asset_type,
                "assetText": asset_text,
                "usefulnessScore": to_convex_number(usefulness),
                "confidenceScore": to_convex_number(confidence),
                "tags": json.loads(tags_json) if tags_json else [],
                "topicKeys": topic_map.get(chunk_id, []),
            })
        source = "SQLite marketing_assets"
    else:
        # fallback: derive from the insights JSONL directly
        field_to_type = {
            "right_fit_client_questions": "right_fit_client_question",
            "content_hooks": "content_hook",
            "client_pain_points": "pain_point",
            "client_objections": "objection",
            "frameworks_or_models": "framework",
            "stories_or_examples": "story_or_example",
            "quotable_lines": "quote",
            "youtube_angles": "youtube_angle",
            "short_form_angles": "short_form_angle",
            "email_angles": "email_angle",
            "sales_page_angles": "sales_page_angle",
            "offer_positioning_notes": "offer_positioning_note",
        }
        for r in insights:
            for field, asset_type in field_to_type.items():
                for i, text in enumerate(r.get(field) or []):
                    payloads.append({
                        "assetId": f"{r['record_id']}__{asset_type}_{i:03d}",
                        "recordId": r["record_id"],
                        "chunkId": r["chunk_id"],
                        "sourceFile": r["source_file"],
                        "transcriptTitle": r["transcript_title"],
                        "inferredDate": opt_str(r.get("inferred_date")),
                        "assetType": asset_type,
                        "assetText": text,
                        "usefulnessScore": to_convex_number(r.get("usefulness_score")),
                        "confidenceScore": to_convex_number(r.get("confidence_score")),
                        "tags": r.get("tags") or [],
                        "topicKeys": topic_map.get(r["chunk_id"], []),
                    })
        source = "derived from extracted_marketing_insights.jsonl"
    print(f"\n[3/6] Marketing assets ({len(payloads)}, {source}) ...")
    counts["marketingAssets"] = batch_upsert(
        client, "marketingAssets", payloads, ASSET_BATCH, "assets")

    # 4. topic index ----------------------------------------------------------
    index_path = PROJECT_ROOT / "database" / "topic_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    payloads = []
    for key, t in index.get("topics", {}).items():
        payloads.append({
            "topicKey": key,
            "displayName": t["display_name"],
            "matchingChunks": to_convex_number(t.get("matching_chunks", 0)),
            "sourceFilesCount": to_convex_number(t.get("matching_source_files")),
            "topAssetTypes": t.get("top_asset_types"),
            "relatedTerms": t.get("co_occurring_topics"),
            "isWeakTopic": (t.get("matching_chunks", 0) or 0) < 10,
            "fullRecord": t,
        })
    print(f"\n[4/6] Topic index ({len(payloads)}) ...")
    counts["topicIndex"] = batch_upsert(
        client, "topicIndex", payloads, 50, "topics")

    # 5. topic packs ----------------------------------------------------------
    packs_dir = PROJECT_ROOT / "database" / "topic_packs"
    payloads = []
    for path in sorted(packs_dir.glob("*_topic_pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        payloads.append({
            "topicKey": pack["topic_key"],
            "displayName": pack["display_name"],
            "pack": pack,
            "generatedAt": opt_str(pack.get("generated_at")),
            "extractionMode": opt_str(pack.get("extraction_mode")),
            "stats": pack.get("stats"),
        })
    print(f"\n[5/6] Topic packs ({len(payloads)}) ...")
    counts["topicPacks"] = batch_upsert(
        client, "topicPacks", payloads, 5, "packs")

    # 6. app metadata ----------------------------------------------------------
    print("\n[6/6] App metadata ...")
    extraction_mode = index.get("extraction_mode", "unknown")
    manifest_path = PROJECT_ROOT / "agent_index" / "agent_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.exists() else None
    upload_counts = {k: v["total"] for k, v in counts.items()}
    metadata = {
        "extraction_mode": extraction_mode,
        "mock_mode_active": extraction_mode == "mock",
        "mock_mode_warning": (manifest or {}).get("mock_mode_warning"),
        "upload_counts": upload_counts,
        "generated_at": now_iso(),
        "source_files_summary": {
            "transcripts": len({c["source_file"] for c in chunks}),
            "chunks": len(chunks),
            "insight_records": len(insights),
        },
        "topic_index": index,  # lets a hosted app hydrate the router cache
    }
    client.mutation("techLabDemo:upsertAppMetadata",
                    {"key": "demo_status", "value": metadata})
    if manifest:
        client.mutation("techLabDemo:upsertAppMetadata",
                        {"key": "agent_manifest", "value": manifest})
    counts["appMetadata"] = {"total": 2 if manifest else 1}

    # report ----------------------------------------------------------------
    report = {
        "generated_at": now_iso(),
        "convex_url_source": "environment/.env.local",
        "tables": counts,
        "topic_tagged_chunks": len(topic_map),
        "not_uploaded": ["raw transcript .txt files",
                         "cleaned full transcripts", "markdown reports",
                         "exports"],
    }
    write_json(REPORTS_DIR / "convex_upload_report.json", report)
    lines = [
        "# Convex Upload Report", "",
        f"Generated: {report['generated_at']}", "",
        "| Table | Records | Inserted | Updated |", "|---|---:|---:|---:|",
    ] + [
        f"| {t} | {c['total']} | {c.get('inserted', '—')} | "
        f"{c.get('updated', '—')} |" for t, c in counts.items()
    ] + [
        "",
        f"- Chunks tagged with at least one topic: {len(topic_map)}",
        "- Idempotent: re-running updates records in place (keyed on "
        "chunkId / recordId / assetId / topicKey).",
        "- Raw and cleaned transcripts were NOT uploaded.",
        "",
        "Verify with: `python3 scripts/verify_convex_upload.py`",
    ]
    write_text_report(REPORTS_DIR / "convex_upload_report.md",
                      "\n".join(lines) + "\n")

    print(f"\nUpload complete: " + ", ".join(
        f"{t}={c['total']}" for t, c in counts.items()))
    print(f"Report -> {REPORTS_DIR / 'convex_upload_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
