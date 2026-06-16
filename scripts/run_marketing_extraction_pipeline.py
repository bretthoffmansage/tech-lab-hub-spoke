#!/usr/bin/env python3
"""Run the Marketing Intelligence Extraction v1 pipeline.

    python3 scripts/run_marketing_extraction_pipeline.py --provider mock --max-packets 10
    python3 scripts/run_marketing_extraction_pipeline.py --provider mock
    python3 scripts/run_marketing_extraction_pipeline.py --provider anthropic --max-packets 25

Steps:
  1. extract_marketing_insights.py   (provider/max-packets/overwrite/resume flags pass through)
  2. validate_marketing_insights.py
  3. build_marketing_rollups.py
  4. build_sqlite_database.py

If a real provider is selected and its package or API key is missing, step 1
fails with a clear message BEFORE writing anything, and the pipeline stops —
existing outputs are never corrupted.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT  # noqa: E402

SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_step(name, argv, results):
    print(f"\n[{len(results) + 1}] Running {name} ...")
    print("-" * 60)
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / name)] + argv,
                          cwd=PROJECT_ROOT)
    results.append((name, proc.returncode, round(time.monotonic() - t0, 1)))
    return proc.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Run the marketing extraction pipeline.")
    parser.add_argument("--provider", choices=["mock", "anthropic", "openai"],
                        help="Extraction provider (default: config value, mock)")
    parser.add_argument("--max-packets", type=int, dest="max_packets",
                        help="Process at most N packets (test runs)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace the existing insights output file")
    parser.add_argument("--resume", action="store_true",
                        help="Skip chunk_ids already extracted (config default: on)")
    args = parser.parse_args()

    extract_args = []
    if args.provider:
        extract_args += ["--provider", args.provider]
    if args.max_packets is not None:
        extract_args += ["--max-packets", str(args.max_packets)]
    if args.overwrite:
        extract_args += ["--overwrite"]
    if args.resume:
        extract_args += ["--resume"]

    print("=" * 60)
    print("Marketing Intelligence Extraction Pipeline v1")
    print("=" * 60)

    results = []
    ok = run_step("extract_marketing_insights.py", extract_args, results)
    if not ok:
        print("\nExtraction failed or was blocked (see message above). "
              "Stopping before validation/rollups/database so existing "
              "outputs are not touched.")
    else:
        ok = (run_step("validate_marketing_insights.py", [], results)
              and run_step("build_marketing_rollups.py", [], results)
              and run_step("build_sqlite_database.py", [], results))

    print("\n" + "=" * 60)
    for name, code, secs in results:
        status = "ok" if code == 0 else f"FAILED (exit {code})"
        print(f"  {name}: {status} [{secs}s]")
    print(f"Pipeline {'complete' if ok else 'FAILED'}.")
    print("=" * 60)
    if ok:
        print("\nNext: inspect processed/reports/marketing_insights_rollup_report.md")
        print('Search: python3 scripts/query_marketing_insights.py "right fit client"')
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
