"""Shared Convex helpers: env loading and client construction.

Reads CONVEX_URL from the environment or .env.local. The Python client is an
optional dependency — install with: pip install convex
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT  # noqa: E402

ENV_LOCAL = PROJECT_ROOT / ".env.local"


def load_env_local():
    """Minimal .env.local parser (KEY=VALUE lines, # comments stripped)."""
    values = {}
    if not ENV_LOCAL.exists():
        return values
    for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def get_convex_url():
    url = os.environ.get("CONVEX_URL")
    if url:
        return url
    return load_env_local().get("CONVEX_URL")


def get_convex_client():
    """Returns (client, error_message). client is None on any failure."""
    url = get_convex_url()
    if not url:
        return None, "CONVEX_URL not set (checked environment and .env.local)"
    try:
        from convex import ConvexClient
    except ImportError:
        return None, ("The 'convex' Python package is not installed. "
                      "Run: pip install convex")
    try:
        return ConvexClient(url), None
    except Exception as e:  # noqa: BLE001
        return None, f"Could not create Convex client for {url}: {e}"


def to_convex_number(value):
    """Convex v.number() is float64; the Python client sends ints as Int64,
    which fails validation — coerce numeric scalars to float."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return float(value)
    return value
