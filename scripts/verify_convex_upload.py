#!/usr/bin/env python3
"""Verify the Convex demo data is complete and retrievable.

    python3 scripts/verify_convex_upload.py

Writes processed/reports/convex_verify_report.{md,json}.
Exit 0 when all checks pass, 1 otherwise.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, write_json, write_text_report,
)
from convex_lib import get_convex_client  # noqa: E402

REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"
SEARCH_TERMS = ["right fit client", "offer", "webinar", "registration"]
KNOWN_TOPICS = ["right_fit_client", "high_ticket_offer"]


def main():
    client, err = get_convex_client()
    if client is None:
        print(f"CONVEX ERROR: {err}")
        return 1

    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")

    print("Verifying Convex demo data ...")
    for table, minimum in [("transcriptChunks", 1), ("marketingInsights", 1),
                           ("marketingAssets", 1), ("topicIndex", 1),
                           ("topicPacks", 1)]:
        try:
            n = client.query("techLabDemo:countTable", {"table": table})
            check(f"{table} count > 0", n >= minimum, f"{int(n)} records")
        except Exception as e:  # noqa: BLE001
            check(f"{table} count > 0", False, e)

    try:
        topics = client.query("techLabDemo:getTopics")
        check("getTopics returns ranked topics", len(topics) > 0,
              f"{len(topics)} topics, top: "
              + ", ".join(t["displayName"] for t in topics[:3]))
    except Exception as e:  # noqa: BLE001
        check("getTopics returns ranked topics", False, e)

    for key in KNOWN_TOPICS:
        try:
            topic = client.query("techLabDemo:getTopicByKey", {"topicKey": key})
            check(f"topic '{key}' retrievable", topic is not None,
                  topic["displayName"] if topic else "missing")
            pack = client.query("techLabDemo:getTopicPack", {"topicKey": key})
            sections = sum(
                len(v) for v in (pack or {}).get("pack", {})
                .get("sections", {}).values())
            check(f"topic pack '{key}' retrievable", pack is not None,
                  f"{sections} section items" if pack else "missing")
        except Exception as e:  # noqa: BLE001
            check(f"topic '{key}' retrievable", False, e)

    for term in SEARCH_TERMS:
        try:
            rows = client.query("techLabDemo:searchTranscriptChunks",
                                {"query": term, "limit": 3.0})
            check(f'chunk search "{term}"', len(rows) > 0,
                  f"{len(rows)} hits, first: {rows[0]['sourceFile']}"
                  if rows else "no hits")
        except Exception as e:  # noqa: BLE001
            check(f'chunk search "{term}"', False, e)

    try:
        rows = client.query(
            "techLabDemo:searchMarketingAssets",
            {"query": "right fit client", "limit": 3.0,
             "assetType": "right_fit_client_question"})
        check("asset search with assetType filter", len(rows) > 0,
              f"{len(rows)} hits")
    except Exception as e:  # noqa: BLE001
        check("asset search with assetType filter", False, e)

    try:
        assets = client.query(
            "techLabDemo:getAssetsByTopic",
            {"topicKey": "right_fit_client", "limit": 5.0})
        check("getAssetsByTopic(right_fit_client)", len(assets) > 0,
              f"{len(assets)} assets (topicKeys tagging works)")
    except Exception as e:  # noqa: BLE001
        check("getAssetsByTopic(right_fit_client)", False, e)

    try:
        meta = client.query("techLabDemo:getAppMetadata")
        status = meta.get("demo_status", {})
        check("app metadata exists", bool(status),
              f"extraction_mode={status.get('extraction_mode')}, "
              f"mock={status.get('mock_mode_active')}")
    except Exception as e:  # noqa: BLE001
        check("app metadata exists", False, e)

    passed = sum(1 for c in checks if c["ok"])
    ok = passed == len(checks)
    report = {
        "generated_at": now_iso(),
        "overall_status": "PASS" if ok else "FAIL",
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
    write_json(REPORTS_DIR / "convex_verify_report.json", report)
    lines = [
        "# Convex Verify Report", "",
        f"Generated: {report['generated_at']}", "",
        f"**Overall: {report['overall_status']}** "
        f"({passed}/{len(checks)} checks passed)", "",
        "| Check | Result | Detail |", "|---|---|---|",
    ] + [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |"
         for c in checks]
    write_text_report(REPORTS_DIR / "convex_verify_report.md",
                      "\n".join(lines) + "\n")
    print(f"\n{report['overall_status']}: {passed}/{len(checks)} checks passed")
    print(f"Report -> {REPORTS_DIR / 'convex_verify_report.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
