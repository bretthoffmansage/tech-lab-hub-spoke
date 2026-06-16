#!/usr/bin/env python3
"""Layer 10: Run the full local pipeline in order.

    python3 scripts/run_pipeline.py

Steps:
  1. transcript_inventory.py
  2. normalize_transcripts.py
  3. chunk_transcripts.py
  4. extract_basic_signals.py
  5. build_llm_extraction_packets.py
  6. build_sqlite_database.py

Stops on the first failing step and writes pipeline_run_report.{md,json}.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import (  # noqa: E402
    PROJECT_ROOT, load_config, now_iso, write_json, write_text_report,
)

STEPS = [
    "transcript_inventory.py",
    "normalize_transcripts.py",
    "chunk_transcripts.py",
    "extract_basic_signals.py",
    "build_llm_extraction_packets.py",
    "build_sqlite_database.py",
]


def main():
    config = load_config()
    scripts_dir = PROJECT_ROOT / "scripts"
    reports_dir = PROJECT_ROOT / config["reports_output_dir"]
    results = []
    overall_ok = True
    started = now_iso()

    print("=" * 60)
    print("Tech Lab Transcript Pipeline")
    print("=" * 60)

    for i, step in enumerate(STEPS, 1):
        print(f"\n[{i}/{len(STEPS)}] Running {step} ...")
        print("-" * 60)
        t0 = time.monotonic()
        proc = subprocess.run(
            [sys.executable, str(scripts_dir / step)],
            cwd=PROJECT_ROOT,
        )
        elapsed = round(time.monotonic() - t0, 1)
        ok = proc.returncode == 0
        results.append({
            "step": step,
            "status": "ok" if ok else "FAILED",
            "exit_code": proc.returncode,
            "seconds": elapsed,
        })
        if not ok:
            overall_ok = False
            print(f"\nSTOPPING: {step} failed with exit code {proc.returncode}.")
            break

    report = {
        "started_at": started,
        "finished_at": now_iso(),
        "overall_status": "success" if overall_ok else "failed",
        "steps": results,
    }
    write_json(reports_dir / "pipeline_run_report.json", report)

    lines = [
        "# Pipeline Run Report", "",
        f"Started: {report['started_at']}",
        f"Finished: {report['finished_at']}",
        f"Overall status: **{report['overall_status'].upper()}**", "",
        "| Step | Status | Exit code | Seconds |",
        "|---|---|---:|---:|",
    ] + [
        f"| `{r['step']}` | {r['status']} | {r['exit_code']} | {r['seconds']} |"
        for r in results
    ] + [
        "",
        "Key outputs:",
        "- `processed/reports/transcript_inventory.md`",
        "- `processed/cleaned_transcripts/`",
        "- `database/transcript_chunks.jsonl`",
        "- `database/basic_signals.jsonl`",
        "- `processed/extracted_insights/llm_packets.jsonl`",
        "- `database/tech_lab_knowledge_base.sqlite`",
        "",
        "Search the knowledge base:",
        '- `python3 scripts/query_local_kb.py "right fit client"`',
    ]
    write_text_report(reports_dir / "pipeline_run_report.md", "\n".join(lines) + "\n")

    print("\n" + "=" * 60)
    print(f"Pipeline {'complete' if overall_ok else 'FAILED'}.")
    print(f"Run report -> {reports_dir / 'pipeline_run_report.md'}")
    print("=" * 60)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
