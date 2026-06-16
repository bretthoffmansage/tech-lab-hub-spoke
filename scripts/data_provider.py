"""Data provider abstraction for the natural-language demo app.

One interface, two implementations:
  ConvexDataProvider — reads the hosted demo data from Convex
  LocalDataProvider  — reads the existing local files (original behavior)

Selection (get_provider):
  TECH_LAB_DATA_PROVIDER=convex  force Convex (falls back with a warning note)
  TECH_LAB_DATA_PROVIDER=local   force local files
  TECH_LAB_DATA_PROVIDER=auto    prefer Convex when configured AND it has
                                 topics; otherwise local files (default)

The app never fails because Convex is missing — local behavior is preserved.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT, now_iso  # noqa: E402
from convex_lib import get_convex_client, get_convex_url  # noqa: E402
import query_local_kb as qkb  # noqa: E402

PACKS_JSON_DIR = PROJECT_ROOT / "database" / "topic_packs"
TOPIC_INDEX_PATH = PROJECT_ROOT / "database" / "topic_index.json"
EXPORTS_DIR = PROJECT_ROOT / "exports" / "topic_assets"
MANIFEST_PATH = PROJECT_ROOT / "agent_index" / "agent_manifest.json"

# export asset type -> (pack section, optional item-field filter)
EXPORT_SECTIONS = {
    "questions": [("right_fit_client_questions", None)],
    "hooks": [("hooks_quotables", {"content_hooks", "metaphors_or_phrases"})],
    "quotes": [("hooks_quotables", {"quotable_lines"})],
    "pain_points": [("pain_points", None)],
    "objections": [("objections_pushback", None)],
    "youtube_angles": [("youtube_angles", None)],
    "short_form_angles": [("short_form_angles", None)],
    "email_angles": [("email_angles", None)],
    "offer_notes": [("offer_positioning", None)],
}
EXPORT_SECTIONS["all"] = [pair for pairs in EXPORT_SECTIONS.values()
                          for pair in pairs]


def canonical_topic_key(value):
    """Resolve a topic key, display name, or alias to the canonical
    topicKey (e.g. 'Webinar / Event Conversion' -> 'webinar_event_conversion')
    so pack lookups never miss on display-name input."""
    if not value:
        return value
    from topic_lib import load_topic_config, resolve_topic
    config = load_topic_config()
    if value in config["topic_aliases"]:
        return value
    resolved = resolve_topic(str(value), config)
    return resolved["topic_key"] if resolved["configured"] else value


class BaseProvider:
    name = "base"
    status_note = ""

    # ---- shared, pack-based behavior ----
    def get_assets(self, topic_key=None, asset_type=None, limit=25):
        """Assets pulled from the topic pack sections (works identically for
        both providers because packs have the same shape)."""
        pack = self.get_topic_pack(topic_key) if topic_key else None
        if not pack:
            return []
        pairs = EXPORT_SECTIONS.get(asset_type or "all",
                                    EXPORT_SECTIONS["all"])
        items = []
        for section, fields in pairs:
            for item in pack.get("sections", {}).get(section, []):
                if fields and item.get("field") not in fields:
                    continue
                items.append(item)
                if len(items) >= limit:
                    return items
        return items

    def export_assets(self, topic_key, asset_type="all", limit=100,
                      display_name=None):
        """Build a hand-off markdown list. Returns
        {filename, content, path, items}. Writing to disk is best-effort
        (may be read-only on a hosted runtime)."""
        items = self.get_assets(topic_key, asset_type, limit)
        title = display_name or topic_key
        lines = [f"# {title} — {asset_type} export",
                 "", f"Generated: {now_iso()}  |  Data source: {self.name}",
                 ""]
        meta = self.get_metadata()
        if meta.get("mock_mode_active"):
            lines += ["> Mock/placeholder extraction — items are verbatim "
                      "transcript sentences, not polished copy.", ""]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item['text']}")
            lines.append(f"   - source: `{item.get('source_file', '?')}` · "
                         f"chunk `{item.get('chunk_id', '?')}`")
        content = "\n".join(lines) + "\n"
        filename = f"{topic_key}_{asset_type}.md"
        path = None
        try:
            EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
            out = EXPORTS_DIR / filename
            out.write_text(content, encoding="utf-8")
            path = str(out.relative_to(PROJECT_ROOT))
        except OSError:
            pass
        return {"filename": filename, "content": content, "path": path,
                "items": items}


class LocalDataProvider(BaseProvider):
    name = "Local files"

    def get_topics(self):
        if not TOPIC_INDEX_PATH.exists():
            return []
        index = json.loads(TOPIC_INDEX_PATH.read_text(encoding="utf-8"))
        return [{"topic_key": key, **t}
                for key, t in index.get("topics", {}).items()]

    def get_topic_pack(self, topic_key, display_name=None):
        topic_key = canonical_topic_key(topic_key)
        path = PACKS_JSON_DIR / f"{topic_key}_topic_pack.json"
        if not path.exists() and display_name:
            # safely run the existing CLI builder, then reload
            subprocess.run(
                [sys.executable,
                 str(PROJECT_ROOT / "scripts" / "build_topic_pack.py"),
                 display_name],
                cwd=PROJECT_ROOT, capture_output=True, timeout=300)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def get_available_topic_packs(self):
        return [p.stem.replace("_topic_pack", "")
                for p in sorted(PACKS_JSON_DIR.glob("*_topic_pack.json"))]

    def search_transcripts(self, query, limit=10):
        db_path = PROJECT_ROOT / "database" / "tech_lab_knowledge_base.sqlite"
        jsonl_path = PROJECT_ROOT / "database" / "transcript_chunks.jsonl"
        if db_path.exists():
            rows, backend = qkb.search_sqlite(db_path, query, limit)
        elif jsonl_path.exists():
            rows, backend = qkb.search_jsonl(jsonl_path, query, limit)
        else:
            return [], "none"
        terms = query.split()
        return [{
            "chunk_id": r[0], "source_file": r[1], "transcript_title": r[2],
            "inferred_date": r[3], "chunk_index": r[4],
            "excerpt": qkb.make_excerpt(r[5], terms),
            "text": r[5],
        } for r in rows], backend

    def search_assets(self, query, asset_type=None, limit=10):
        db_path = PROJECT_ROOT / "database" / "tech_lab_knowledge_base.sqlite"
        if not db_path.exists():
            return []
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            like = f"%{query}%"
            sql = ("SELECT asset_id, chunk_id, source_file, transcript_title, "
                   "inferred_date, asset_type, asset_text, usefulness_score "
                   "FROM marketing_assets WHERE asset_text LIKE ?")
            params = [like]
            if asset_type:
                sql += " AND asset_type = ?"
                params.append(asset_type)
            sql += " ORDER BY usefulness_score DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [{"asset_id": r[0], "chunk_id": r[1], "source_file": r[2],
                 "transcript_title": r[3], "inferred_date": r[4],
                 "asset_type": r[5], "text": r[6], "usefulness_score": r[7]}
                for r in rows]

    def get_chunk(self, chunk_id):
        jsonl_path = PROJECT_ROOT / "database" / "transcript_chunks.jsonl"
        if not jsonl_path.exists():
            return None
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if chunk_id in line:
                    record = json.loads(line)
                    if record.get("chunk_id") == chunk_id:
                        return record
        return None

    def get_metadata(self):
        meta = {"data_source": self.name}
        if TOPIC_INDEX_PATH.exists():
            index = json.loads(TOPIC_INDEX_PATH.read_text(encoding="utf-8"))
            meta["extraction_mode"] = index.get("extraction_mode", "unknown")
            meta["mock_mode_active"] = index.get("extraction_mode") == "mock"
        if MANIFEST_PATH.exists():
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            meta["mock_mode_warning"] = manifest.get("mock_mode_warning")
            meta.setdefault("mock_mode_active",
                            bool(manifest.get("mock_mode_warning")))
        return meta


class ConvexDataProvider(BaseProvider):
    name = "Convex"

    def __init__(self, client):
        self.client = client
        self._metadata = None
        self._hydrate_local_caches()

    def _hydrate_local_caches(self):
        """Write database/topic_index.json from Convex when it's missing
        (e.g. on a hosted runtime) so the keyword router keeps working
        without any code changes."""
        try:
            if not TOPIC_INDEX_PATH.exists():
                index = self.get_metadata().get("topic_index")
                if index:
                    TOPIC_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
                    TOPIC_INDEX_PATH.write_text(
                        json.dumps(index, ensure_ascii=False),
                        encoding="utf-8")
        except OSError:
            pass  # read-only filesystem: router falls back to config aliases

    def get_topics(self):
        docs = self.client.query("techLabDemo:getTopics")
        return [{"topic_key": d["topicKey"], **(d.get("fullRecord") or {
            "display_name": d["displayName"],
            "matching_chunks": d["matchingChunks"]})} for d in docs]

    def get_topic_pack(self, topic_key, display_name=None):
        doc = self.client.query("techLabDemo:getTopicPack",
                                {"topicKey": canonical_topic_key(topic_key)})
        return doc["pack"] if doc else None

    def get_available_topic_packs(self):
        docs = self.client.query("techLabDemo:getTopicPacks")
        return [d["topicKey"] for d in docs]

    def search_transcripts(self, query, limit=10):
        docs = self.client.query("techLabDemo:searchTranscriptChunks",
                                 {"query": query, "limit": float(limit)})
        terms = query.split()
        return [{
            "chunk_id": d["chunkId"], "source_file": d["sourceFile"],
            "transcript_title": d["transcriptTitle"],
            "inferred_date": d.get("inferredDate", "unknown"),
            "chunk_index": d.get("chunkIndex"),
            "excerpt": qkb.make_excerpt(d["text"], terms),
            "text": d["text"],
        } for d in docs], "convex-search"

    def search_assets(self, query, asset_type=None, limit=10):
        args = {"query": query, "limit": float(limit)}
        if asset_type:
            args["assetType"] = asset_type
        docs = self.client.query("techLabDemo:searchMarketingAssets", args)
        return [{"asset_id": d["assetId"], "chunk_id": d["chunkId"],
                 "source_file": d["sourceFile"],
                 "transcript_title": d["transcriptTitle"],
                 "inferred_date": d.get("inferredDate"),
                 "asset_type": d["assetType"], "text": d["assetText"],
                 "usefulness_score": d.get("usefulnessScore")}
                for d in docs]

    def get_chunk(self, chunk_id):
        doc = self.client.query("techLabDemo:getChunkById",
                                {"chunkId": chunk_id})
        if not doc:
            return None
        return {"chunk_id": doc["chunkId"], "source_file": doc["sourceFile"],
                "transcript_title": doc["transcriptTitle"],
                "inferred_date": doc.get("inferredDate"),
                "chunk_index": doc.get("chunkIndex"), "text": doc["text"]}

    def get_metadata(self):
        if self._metadata is None:
            meta = self.client.query("techLabDemo:getAppMetadata")
            self._metadata = dict(meta.get("demo_status") or {})
            self._metadata["data_source"] = self.name
        return self._metadata


def get_provider():
    """Returns (provider, note). Never raises — worst case is local files."""
    mode = os.environ.get("TECH_LAB_DATA_PROVIDER", "auto").strip().lower()
    if mode == "local":
        return LocalDataProvider(), "forced local via TECH_LAB_DATA_PROVIDER"

    client, err = get_convex_client()
    if client is not None:
        try:
            topics = client.query("techLabDemo:getTopics")
            if topics:
                provider = ConvexDataProvider(client)
                return provider, f"connected to {get_convex_url()}"
            err = ("Convex is configured but has no topic data yet — run "
                   "python3 scripts/upload_to_convex.py")
        except Exception as e:  # noqa: BLE001
            err = f"Convex query failed: {e}"

    if mode == "convex":
        return LocalDataProvider(), (
            f"Convex was requested but unavailable ({err}); using local files")
    return LocalDataProvider(), \
        (f"Convex unavailable ({err}); using local files" if get_convex_url()
         else "Convex not configured; using local files")
