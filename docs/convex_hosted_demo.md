# Convex Hosted Demo

The natural-language Streamlit app can now read its demo data from Convex
instead of local files, so the demo no longer depends on this computer once
the data is uploaded. Local files remain a full fallback.

## Architecture in one line

`app.py` → `scripts/data_provider.py` → **Convex** (preferred when
configured and populated) or **local files** (original behavior, unchanged).
The sidebar always shows which data source is active.

## How to run locally with Convex

```bash
npx convex dev          # keeps schema/functions synced (or: npm run convex:dev)
streamlit run app.py    # sidebar should show "Data source: Convex"
```

`CONVEX_URL` is read from the environment or `.env.local` (already present).
Provider selection can be forced:

```bash
TECH_LAB_DATA_PROVIDER=local  streamlit run app.py   # force local files
TECH_LAB_DATA_PROVIDER=convex streamlit run app.py   # force Convex
# default is auto: Convex when configured AND populated, else local
```

## How to upload data to Convex

```bash
pip install convex                       # one-time
python3 scripts/upload_to_convex.py
```

Uploads chunks, insights, flattened marketing assets (with topic tags),
the topic index, topic packs, and app metadata. Idempotent — re-running
updates records in place (keyed on chunkId / recordId / assetId / topicKey),
so re-upload any time the local pipeline regenerates data. Report:
`processed/reports/convex_upload_report.md`.

**Never uploaded:** raw transcript `.txt` files, cleaned full transcripts,
markdown reports, exports.

## How to verify the upload

```bash
python3 scripts/verify_convex_upload.py
```

Checks table counts, known topics (`right_fit_client`,
`high_ticket_offer`), topic packs, search ("right fit client", "offer",
"webinar", "registration"), topic-tagged assets, and app metadata. Report:
`processed/reports/convex_verify_report.md`.

## How to deploy to Streamlit Cloud

1. Push the repo to GitHub **without**: `.env.local` (gitignored), raw
   transcript `.txt` files, `processed/cleaned_transcripts/`, or any
   secrets. Check `git status` before the first push. The app needs only:
   `app.py`, `scripts/`, `config/`, `requirements.txt`, `.streamlit/config.toml`.
2. On https://share.streamlit.io create an app pointing at `app.py`.
3. In the app's **Secrets** panel add (Streamlit Cloud exposes secrets as
   environment variables, which is how the app reads them):

   ```toml
   CONVEX_URL = "https://accurate-giraffe-844.convex.cloud"
   TECH_LAB_DATA_PROVIDER = "convex"
   OPENAI_API_KEY = "sk-..."
   OPENAI_MODEL = "gpt-4.1-mini"
   ```

   Without `OPENAI_API_KEY` the app still runs in retrieval-only mode
   (raw source excerpts, no synthesized answers). `OPENAI_MODEL` is
   optional — the default is `gpt-4.1-mini`, set in
   `scripts/openai_answerer.py`.

4. Deploy. The app pulls topics, packs, search, and metadata from Convex;
   on first load it also caches the topic index locally so the keyword
   router works identically to the local setup.

For a production (non-dev) Convex deployment later: `npx convex deploy`
(or `npm run convex:deploy`) and switch `CONVEX_URL` to the prod URL.

## Keeping the local fallback

Nothing about the local pipeline changed. With no `CONVEX_URL` (or with
`TECH_LAB_DATA_PROVIDER=local`), the app behaves exactly as before, reading
`database/` and building packs through the existing CLI scripts. If Convex
is configured but empty, the app says so and tells you to run the upload
script — it does not fail.

## Do not commit

- `.env.local` (deployment URLs + any future keys) — gitignored
- `.streamlit/secrets.toml` — gitignored
- Raw transcripts (only with explicit approval, and the hosted demo doesn't
  need them — it uses processed chunks)

## Known limitations (v1, by design)

- `getAssetsByTopic` filters the `topicKeys` array in JS after an indexed
  scan — fine at demo scale (~5k assets), not a production pattern.
- Convex full-text search is keyword-based (like the local FTS5); no vector
  search in this package.
- Exports on a hosted runtime are download-only (the file write is
  best-effort and skipped on read-only filesystems).
- Data is mock-extraction placeholders until a real LLM extraction run is
  uploaded.
