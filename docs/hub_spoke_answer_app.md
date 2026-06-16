# Hub & Spoke Answer Capture App

A Streamlit app for manually answering prewritten tech-related SEO/AEO questions organized as **hubs** (content pillars) and **spokes** (questions). There is no LLM, no chat assistant, and no transcript retrieval — users type answers directly and everything persists in **Convex**.

## What it does

- **Explore Hubs** — browse all hubs, see per-hub progress, open any question to answer or edit.
- **Answer Questions** — guided flow through unanswered questions in sort order (`Question X/Y`).
- **Export** — download selected hubs as Markdown, CSV, or JSON.

Convex is the **only** source of truth. Multiple users on Streamlit Cloud share the same data. **Answer Questions mode** uses hub-level locking so two people are not guided through the same hub at once.

## Hub locking (Answer Questions mode)

When someone clicks **Start Answering Questions**:

1. Convex runs `claimNextAvailableHub` in a single mutation (clears expired locks first).
2. The first hub in `sortOrder` with unanswered questions and no active lock from another session is **claimed** for that browser session.
3. The user stays in that hub until all its unanswered questions are done — the app does not jump between hubs mid-session.
4. When the hub is complete, the lock is released and the next available hub is claimed automatically.
5. A second person clicking **Start Answering Questions** gets the next unlocked hub.

Each browser tab gets a stable `session_id` (UUID in `st.session_state`) and label like `Session abc12345`. No login required.

### Lock heartbeat and timeout

- Default lock timeout: **5 minutes** (`lockExpiresAt`).
- While in Answer Questions mode, every Streamlit rerun calls `renewHubLock` to refresh the heartbeat.
- If a tab is closed without clicking **Exit Answer Mode**, the lock remains until `lockExpiresAt` passes, then the hub becomes available again.
- Streamlit has no reliable tab-close hook — timeout is the safety net.

### Manual Explore edits

Explore Hubs still allows opening and editing any question. If another session holds the hub lock, a warning is shown but edits are not blocked (v1). Guided Answer Questions mode skips hubs locked by others.

## Data model (Convex)

### `hubs`

| Field | Type | Notes |
|-------|------|-------|
| `hubId` | string | Stable public ID (e.g. `hub-event-tech-foundations`) |
| `hubName` | string | Display name |
| `description` | string | Hub description |
| `sortOrder` | number | Display order |
| `createdAt` | string | ISO timestamp |
| `updatedAt` | string | ISO timestamp |
| `lockStatus` | string? | `locked` or absent/`unlocked` |
| `lockedBySessionId` | string? | Browser session UUID |
| `lockedByLabel` | string? | Display label, e.g. `Session abc12345` |
| `lockedAt` | string? | When lock was taken |
| `lockHeartbeatAt` | string? | Last lock renewal |
| `lockExpiresAt` | string? | Stale after this time (default 5 min) |

Indexes: `by_hub_id`, `by_sort_order`

### `questions`

| Field | Type | Notes |
|-------|------|-------|
| `questionId` | string | Stable public ID |
| `question` | string | Question text |
| `answer` | string | User-written answer |
| `status` | string | `answered` or `unanswered` |
| `primaryHubId` | string | Primary hub |
| `secondaryHubIds` | string[] | Optional secondary hubs |
| `notes` | string? | Optional notes |
| `sortOrder` | number | Order within hub |
| `createdAt` | string | ISO timestamp |
| `updatedAt` | string | ISO timestamp |
| `answeredAt` | string? | When last answered |
| `answeredBy` | string? | Optional author label |

Indexes: `by_question_id`, `by_primary_hub`, `by_status`, `by_sort_order`, `by_primary_hub_and_sort_order`

### `appMetadata`

Existing table — unchanged. Used for legacy demo metadata; hub/spoke data lives in `hubs` and `questions`.

## Convex functions

File: `convex/hubSpoke.ts`

**Queries:** `listHubs`, `listQuestions`, `listQuestionsByHub`, `listUnansweredQuestions`, `getQuestion`, `getProgress`, `exportData`, `getNextUnansweredQuestionForHubQuery`, `listHubLockStatuses`

**Mutations:** `upsertHub`, `upsertQuestion`, `saveAnswer`, `updateQuestionNotes`, `resetAnswer`, `claimNextAvailableHub`, `renewHubLock`, `releaseHubLock`, `releaseExpiredHubLocksMutation`

## Seed initial questions

```bash
# Deploy schema/functions first
npx convex dev --once

# Seed 8 hubs and 24 questions
python3 scripts/seed_hub_spoke_questions.py
```

The seed script:

- Upserts all hubs and questions by stable ID
- **Preserves existing non-empty answers** on re-run (default)
- Updates question text and hub metadata if changed
- **Preserves existing lock fields** on hub upsert
- Writes `processed/reports/hub_spoke_seed_report.md` when the reports folder exists

To force overwriting answers (destructive):

```bash
python3 scripts/seed_hub_spoke_questions.py --force-answers
```

## Run locally

```bash
pip install -r requirements.txt

# CONVEX_URL must be set — typically in .env.local:
# CONVEX_URL=https://your-deployment.convex.cloud

npx convex dev --once          # push schema + functions
python3 scripts/seed_hub_spoke_questions.py
streamlit run app.py
```

Open http://localhost:8501

## Deploy to Streamlit Cloud

1. Push this repo to GitHub.
2. Create a new Streamlit Cloud app pointing at `app.py`.
3. Add a secret in the Streamlit Cloud dashboard:

   ```
   CONVEX_URL = "https://your-deployment.convex.cloud"
   ```

4. Deploy. No local files are required at runtime.

Ensure Convex functions are deployed (`npx convex deploy` or `npx convex dev --once` from your machine).

## Export

1. Click **Export** in the sidebar (or use the export panel after completing all questions).
2. Select hubs (or use **Select all hubs**).
3. Click **Generate export**.
4. Download Markdown, CSV, or JSON via the download buttons.
5. Set a file name prefix before downloading.

### Markdown format

```
# Tech Lab Hub & Spoke Answers

## Hub: Event Tech Foundations

**Description:** …

**Question:** What tech do I actually need to run a virtual event?

**Answer:**
…

**Status:** answered
```

### CSV columns

`hub_id`, `hub_name`, `question_id`, `question`, `answer`, `status`, `notes`, `updated_at`

## Testing two sessions

1. Open the app in a normal browser window. Click **Start Answering Questions** — note which hub is locked (sidebar shows session label and locked hub).
2. Open an incognito/private window to the same URL. Click **Start Answering Questions** — you should get a **different** hub.
3. In Explore Hubs, the first hub should show **In progress** with the first session's label; the second hub should show **Reserved by you** in the incognito window.
4. Close the first window without exiting. Wait up to 5 minutes (or call `releaseExpiredHubLocksMutation` from the Convex dashboard for faster testing). The hub should become **Available** again.

For faster timeout testing during development, pass `lockTimeoutMinutes` to `claimNextAvailableHub` / `renewHubLock` (not exposed in the UI by default).

## Known limitations

- **No LLM** — answers are manual only.
- **No auth** — anyone with the Streamlit URL can read/write answers; session IDs are browser-local only.
- **Hub locks are cooperative** — guided Answer Questions mode respects locks; manual Explore edits do not (last save wins).
- **Closed tabs** release locks after timeout (5 minutes), not instantly.
- **No background heartbeat** — lock renewal happens on Streamlit reruns only (submit, navigation, etc.), not on a timer unless the page reruns for another reason.
- **No offline mode** — Convex must be reachable; there is no local JSON fallback.
- **Legacy transcript tables** remain in the Convex schema from the previous demo but are unused by this app.

## Manual test checklist

- [ ] App loads and shows **Data source: Convex** in sidebar
- [ ] Explore Hubs shows all 8 hubs
- [ ] All Questions tab lists every question
- [ ] Clicking a question opens the answer editor
- [ ] Saving writes to Convex (refresh browser to confirm persistence)
- [ ] Start Answering Questions claims a hub and stays in that hub
- [ ] Second browser/incognito session gets a different hub
- [ ] Explore Hubs shows lock badges (Available / In progress / Reserved by you / Completed)
- [ ] Exit Answer Mode releases the hub lock
- [ ] Global Question X/Y reflects live Convex counts across all hubs
- [ ] Export generates Markdown and CSV for selected hubs
- [ ] No OpenAI/Anthropic/LLM calls anywhere
