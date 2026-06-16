#!/usr/bin/env python3
"""Boss demo convenience runner.

    python3 scripts/run_boss_demo_pack.py

Runs topic discovery, builds topic packs for the default demo topics, exports
selected asset lists, and refreshes the agent_index manifest status. Writes
processed/reports/boss_demo_run_report.{md,json}.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, now_iso, read_jsonl, write_json, write_text_report,
)
from topic_lib import INSIGHTS_PATH  # noqa: E402

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"
MANIFEST_PATH = PROJECT_ROOT / "agent_index" / "agent_manifest.json"

DEMO_TOPICS = [
    "founder bottleneck",
    "right fit client",
    "offer positioning",
    "content strategy",
    "objections",
]
DEMO_EXPORTS = [
    ("founder bottleneck", "questions"),
    ("right fit client", "hooks"),
    ("objections", "objections"),
]


def run(script, argv, results):
    label = f"{script} {' '.join(argv)}".strip()
    print(f"\n>>> {label}")
    print("-" * 60)
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / script)] + argv,
                          cwd=PROJECT_ROOT)
    results.append({"command": label, "exit_code": proc.returncode,
                    "seconds": round(time.monotonic() - t0, 1)})
    return proc.returncode == 0


def refresh_manifest():
    """Update the agent manifest's dynamic status fields."""
    if not MANIFEST_PATH.exists():
        return "agent_manifest.json missing — not refreshed"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["last_demo_run"] = now_iso()
    if INSIGHTS_PATH.exists():
        providers = {r.get("extraction_provider")
                     for r in read_jsonl(INSIGHTS_PATH)}
        if providers == {"mock"}:
            manifest["mock_mode_warning"] = (
                "All records in database/extracted_marketing_insights.jsonl "
                "currently have extraction_provider='mock'. Treat "
                "questions/hooks/angles as placeholders for workflow testing.")
        elif "mock" in providers:
            manifest["mock_mode_warning"] = (
                "Extraction records are a MIX of mock and real providers; "
                "quality varies by record (check extraction_provider).")
        else:
            manifest["mock_mode_warning"] = None
    write_json(MANIFEST_PATH, manifest)
    return "agent_manifest.json refreshed (last_demo_run, mock_mode_warning)"


def main():
    print("=" * 60)
    print("Boss Demo Pack Runner")
    print("=" * 60)

    results = []
    ok = run("discover_topics.py", [], results)
    for topic in DEMO_TOPICS:
        ok = run("build_topic_pack.py", [topic], results) and ok
    for topic, asset_type in DEMO_EXPORTS:
        ok = run("export_topic_assets.py",
                 [topic, "--asset-type", asset_type], results) and ok
    manifest_note = refresh_manifest()

    report = {
        "generated_at": now_iso(),
        "overall_status": "success" if ok else "had_failures",
        "demo_topics": DEMO_TOPICS,
        "exports": [f"{t} ({a})" for t, a in DEMO_EXPORTS],
        "agent_index": manifest_note,
        "commands": results,
        "inspect_first": [
            "processed/reports/topic_discovery_report.md",
            "processed/reports/topic_packs/right_fit_client_topic_pack.md",
            "exports/topic_assets/right_fit_client_hooks.md",
            "docs/boss_demo_guide.md",
        ],
    }
    write_json(REPORTS_DIR / "boss_demo_run_report.json", report)
    lines = [
        "# Boss Demo Run Report", "",
        f"Generated: {report['generated_at']}",
        f"Status: **{report['overall_status'].upper()}**", "",
        "| Command | Exit | Seconds |", "|---|---:|---:|",
    ] + [f"| `{r['command']}` | {r['exit_code']} | {r['seconds']} |"
         for r in results] + [
        "", f"- {manifest_note}",
        "", "## Inspect first", "",
    ] + [f"- `{p}`" for p in report["inspect_first"]] + [
        "", "## Demo flow", "",
        "See `docs/boss_demo_guide.md` for the step-by-step demo script.",
    ]
    write_text_report(REPORTS_DIR / "boss_demo_run_report.md",
                      "\n".join(lines) + "\n")

    print("\n" + "=" * 60)
    print(f"Demo pack run {'complete' if ok else 'finished WITH FAILURES'}.")
    print(f"Report -> {REPORTS_DIR / 'boss_demo_run_report.md'}")
    print("Demo script -> docs/boss_demo_guide.md")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
