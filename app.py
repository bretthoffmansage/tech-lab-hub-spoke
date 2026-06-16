#!/usr/bin/env python3
"""Tech Lab Hub & Spoke Answer Builder — manual Q&A capture via Convex.

No LLM. Users browse hubs, answer prewritten SEO/AEO questions, and export
results. Convex is the sole source of truth.

Launch:
    streamlit run app.py
"""

import csv
import io
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

import streamlit as st  # noqa: E402

from convex_lib import get_convex_client  # noqa: E402

APP_TITLE = "Tech Lab Hub & Spoke Answer Builder"

# ------------------------------------------------------------------ Convex


def get_convex_url():
    url = os.environ.get("CONVEX_URL")
    if url:
        return url
    try:
        return st.secrets.get("CONVEX_URL")
    except Exception:  # noqa: BLE001
        return None


@st.cache_resource
def boot_convex():
    url = get_convex_url()
    if not url:
        return None, "CONVEX_URL is not set. Add it to .env.local locally or Streamlit Cloud secrets."
    os.environ.setdefault("CONVEX_URL", url)
    client, err = get_convex_client()
    if client is None:
        return None, err or "Could not connect to Convex."
    return client, None


def q(name, args=None):
    return st.session_state.convex.query(f"hubSpoke:{name}", args or {})


def m(name, args):
    return st.session_state.convex.mutation(f"hubSpoke:{name}", args)


# ------------------------------------------------------------------ CSS

APP_CSS = """
<style>
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes slideIn {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}
.hub-spoke-panel {
  animation: fadeIn 0.45s ease-out;
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem 0;
}
.answer-mode-panel .question-counter-answer {
  font-size: 1rem;
  color: #e2e8f0;
  margin-bottom: 0.5rem;
}
.answer-mode-panel .hub-progress-answer {
  font-size: 0.92rem;
  color: #cbd5e1;
  margin-bottom: 1rem;
}
.answer-mode-panel .hub-progress-answer strong {
  color: #f8fafc;
}
.hub-context-answer {
  background: #171923;
  border-left: 4px solid #4a90d9;
  padding: 18px 20px;
  border-radius: 8px;
  margin-bottom: 1rem;
}
.hub-context-answer .hub-context-name {
  color: #ffffff;
  font-weight: 700;
  font-size: 1.05rem;
  margin-bottom: 0.35rem;
}
.hub-context-answer .hub-context-desc {
  color: #d1d5db;
  font-size: 0.92rem;
  line-height: 1.45;
}
.question-hero-answer {
  animation: slideIn 0.5s ease-out;
  color: #c084fc;
  font-size: 1.85rem;
  font-weight: 800;
  line-height: 1.25;
  margin-top: 28px;
  margin-bottom: 22px;
}
.answer-mode-panel label[data-testid="stWidgetLabel"] p,
.answer-mode-panel label[data-testid="stWidgetLabel"] span {
  color: #f1f5f9 !important;
}
.answer-mode-panel textarea {
  background-color: #1e293b !important;
  color: #f8fafc !important;
  border-color: #475569 !important;
}
.answer-mode-panel textarea::placeholder {
  color: #94a3b8 !important;
  opacity: 1;
}
.question-hero {
  animation: slideIn 0.5s ease-out;
  font-size: 1.55rem;
  font-weight: 600;
  line-height: 1.35;
  margin: 1rem 0 1.25rem 0;
  color: #1a1a2e;
}
.hub-context {
  background: #f0f4f8;
  border-left: 4px solid #4a90d9;
  padding: 0.75rem 1rem;
  border-radius: 0 8px 8px 0;
  margin-bottom: 1rem;
}
.badge-answered {
  display: inline-block;
  background: #d4edda;
  color: #155724;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}
.badge-unanswered {
  display: inline-block;
  background: #fff3cd;
  color: #856404;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}
.progress-label {
  font-size: 0.9rem;
  color: #555;
}
.question-counter {
  font-size: 1rem;
  color: #666;
  margin-bottom: 0.5rem;
}
.answer-preview {
  font-size: 0.85rem;
  color: #555;
  font-style: italic;
  margin-top: 0.25rem;
}
.badge-lock-available {
  display: inline-block;
  background: #e8f4fd;
  color: #0c5460;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 0.35rem;
}
.badge-lock-yours {
  display: inline-block;
  background: #cce5ff;
  color: #004085;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 0.35rem;
}
.badge-lock-other {
  display: inline-block;
  background: #f8d7da;
  color: #721c24;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 0.35rem;
}
.badge-lock-done {
  display: inline-block;
  background: #e2e3e5;
  color: #383d41;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 0.35rem;
}
</style>
"""


# ------------------------------------------------------------------ helpers


def hub_map(hubs):
    return {h["hubId"]: h for h in hubs}


def ensure_session():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.session_label = f"Session {st.session_state.session_id[:8]}"


def lock_status_map(lock_rows):
    return {r["hubId"]: r for r in lock_rows}


def hub_lock_badge(row, session_id):
    if row["unanswered"] == 0:
        return '<span class="badge-lock-done">Completed</span>'
    if row.get("lockStatus") == "locked" and not row.get("isStale"):
        if row.get("lockedBySessionId") == session_id:
            return '<span class="badge-lock-yours">Reserved by you</span>'
        label = row.get("lockedByLabel") or "another session"
        return f'<span class="badge-lock-other">In progress — {label}</span>'
    return '<span class="badge-lock-available">Available</span>'


def hub_locked_by_other(row, session_id):
    return (
        row.get("lockStatus") == "locked"
        and not row.get("isStale")
        and row.get("lockedBySessionId") != session_id
    )


def release_active_hub_lock():
    hub_id = st.session_state.get("active_answer_hub_id")
    if not hub_id:
        return True
    ensure_session()
    result = m("releaseHubLock", {
        "hubId": hub_id,
        "sessionId": st.session_state.session_id,
    })
    return result.get("success", False)


def clear_answer_session(show_warning=False):
    if st.session_state.get("active_answer_hub_id"):
        ok = release_active_hub_lock()
        if not ok and show_warning:
            st.session_state.lock_warning = (
                "Could not release hub lock. It will expire automatically after "
                "5 minutes of inactivity."
            )
    st.session_state.active_answer_hub_id = None
    st.session_state.active_answer_hub_name = None
    st.session_state.active_question_id = None


def claim_and_start_answer():
    ensure_session()
    result = m("claimNextAvailableHub", {
        "sessionId": st.session_state.session_id,
        "lockedByLabel": st.session_state.session_label,
    })
    if result.get("claimed"):
        hub = result["hub"]
        question = result.get("firstQuestion")
        st.session_state.active_answer_hub_id = hub["hubId"]
        st.session_state.active_answer_hub_name = hub["hubName"]
        st.session_state.active_question_id = (
            question["questionId"] if question else None
        )
        st.session_state.mode = "answer"
        st.session_state.lock_warning = None
    else:
        st.session_state.save_flash = result.get(
            "message", "No hubs available to claim."
        )
    return result


def renew_active_lock():
    hub_id = st.session_state.get("active_answer_hub_id")
    if not hub_id or st.session_state.mode != "answer":
        return
    ensure_session()
    result = m("renewHubLock", {
        "hubId": hub_id,
        "sessionId": st.session_state.session_id,
    })
    if not result.get("success"):
        st.session_state.lock_warning = (
            "Could not renew your hub lock. The hub may have expired or been "
            "claimed by another session."
        )


def per_hub_progress(progress, hub_id):
    for ph in progress.get("perHub", []):
        if ph["hubId"] == hub_id:
            return ph
    return {"answered": 0, "total": 0, "unanswered": 0}


def answer_preview(text, limit=120):
    if not text or not text.strip():
        return ""
    t = " ".join(text.strip().split())
    return t if len(t) <= limit else t[: limit - 1] + "…"


def status_badge(status):
    if status == "answered":
        return '<span class="badge-answered">answered</span>'
    return '<span class="badge-unanswered">unanswered</span>'


def render_hub_context(hub, answer_mode=False):
    if not hub:
        return
    if answer_mode:
        st.markdown(
            f'<div class="hub-context-answer">'
            f'<div class="hub-context-name">{hub["hubName"]}</div>'
            f'<div class="hub-context-desc">{hub["description"]}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f'<div class="hub-context">'
        f'<strong>{hub["hubName"]}</strong><br>'
        f'<span style="color:#555;font-size:0.9rem;">{hub["description"]}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def question_editor(question, hub, key_prefix, show_notes=False):
    render_hub_context(hub)
    st.markdown(
        f'<div class="question-hero">{question["question"]}</div>',
        unsafe_allow_html=True,
    )
    answer_key = f"{key_prefix}_answer"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = question.get("answer") or ""

    answer = st.text_area(
        "Your answer",
        key=answer_key,
        height=220,
        placeholder="Type your answer here. Press Enter for new lines.",
    )
    notes = None
    if show_notes:
        notes_key = f"{key_prefix}_notes"
        if notes_key not in st.session_state:
            st.session_state[notes_key] = question.get("notes") or ""
        notes = st.text_input("Notes (optional)", key=notes_key)

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Save", key=f"{key_prefix}_save", type="primary"):
            updated = m(
                "saveAnswer",
                {"questionId": question["questionId"], "answer": answer},
            )
            if show_notes and notes is not None:
                m("updateQuestionNotes", {"questionId": question["questionId"], "notes": notes})
            st.session_state.pop(answer_key, None)
            st.session_state.save_flash = "Saved to Convex."
            st.session_state.selected_question_id = updated["questionId"]
            st.rerun()
    with col2:
        if question.get("status") == "answered":
            if st.button("Reset answer", key=f"{key_prefix}_reset"):
                m("resetAnswer", {"questionId": question["questionId"]})
                st.session_state.pop(answer_key, None)
                st.session_state.save_flash = "Answer reset."
                st.rerun()


# ------------------------------------------------------------------ export


def build_markdown(export_rows, title=APP_TITLE):
    lines = [f"# {title}", ""]
    for hub in export_rows:
        lines += [
            f"## Hub: {hub['hubName']}",
            "",
            f"**Description:** {hub['description']}",
            "",
        ]
        for qrow in hub["questions"]:
            lines += [
                f"**Question:** {qrow['question']}",
                "",
                "**Answer:**",
                qrow.get("answer") or "_(empty)_",
                "",
                f"**Status:** {qrow['status']}",
            ]
            if qrow.get("notes"):
                lines += [f"**Notes:** {qrow['notes']}", ""]
            lines.append("")
    return "\n".join(lines)


def build_csv(export_rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "hub_id", "hub_name", "question_id", "question", "answer",
        "status", "notes", "updated_at",
    ])
    for hub in export_rows:
        for qrow in hub["questions"]:
            writer.writerow([
                hub["hubId"],
                hub["hubName"],
                qrow["questionId"],
                qrow["question"],
                qrow.get("answer") or "",
                qrow["status"],
                qrow.get("notes") or "",
                qrow.get("updatedAt") or "",
            ])
    return buf.getvalue()


def build_json(export_rows):
    return json.dumps(export_rows, indent=2, ensure_ascii=False)


def render_export_panel(hubs):
    st.subheader("Export answers")
    prefix = st.text_input("File name prefix", value="tech_lab_hub_spoke")

    hub_ids = [h["hubId"] for h in hubs]
    select_all = st.checkbox("Select all hubs", value=True)
    if select_all:
        selected = hub_ids
    else:
        selected = st.multiselect("Hubs to include", hub_ids,
                                  format_func=lambda x: hub_map(hubs)[x]["hubName"])

    if st.button("Generate export", type="primary"):
        st.session_state.export_data = q(
            "exportData",
            {"selectedHubIds": selected if selected else None},
        )

    data = st.session_state.get("export_data")
    if not data:
        st.caption("Select hubs and click Generate export.")
        return

    md = build_markdown(data)
    csv_data = build_csv(data)
    json_data = build_json(data)

    st.download_button("Download Markdown", md,
                       file_name=f"{prefix}.md", mime="text/markdown")
    st.download_button("Download CSV", csv_data,
                       file_name=f"{prefix}.csv", mime="text/csv")
    st.download_button("Download JSON", json_data,
                       file_name=f"{prefix}.json", mime="application/json")


# ------------------------------------------------------------------ modes


def render_explore(hubs, questions, progress, lock_rows):
    ensure_session()
    session_id = st.session_state.session_id
    locks = lock_status_map(lock_rows)
    hub_by_id = hub_map(hubs)
    questions_by_hub = {h["hubId"]: [] for h in hubs}
    for qu in questions:
        hid = qu["primaryHubId"]
        if hid in questions_by_hub:
            questions_by_hub[hid].append(qu)

    tab_hubs, tab_all = st.tabs(["Hubs", "All Questions"])

    with tab_hubs:
        for hub in hubs:
            hub_qs = questions_by_hub.get(hub["hubId"], [])
            answered = sum(1 for x in hub_qs if x["status"] == "answered")
            total = len(hub_qs)
            lock_row = locks.get(hub["hubId"], {})
            badge = hub_lock_badge(lock_row, session_id)
            with st.expander(f"{hub['hubName']}  ({answered}/{total} answered)"):
                st.markdown(badge, unsafe_allow_html=True)
                st.markdown(hub["description"])
                if hub_locked_by_other(lock_row, session_id):
                    st.warning(
                        "Another session is currently working through this hub. "
                        "Manual edits are still allowed in v1, but the guided "
                        "Answer Questions mode will skip this hub."
                    )
                for qu in hub_qs:
                    cols = st.columns([5, 1])
                    with cols[0]:
                        st.markdown(f"**{qu['question']}**")
                        st.markdown(status_badge(qu["status"]), unsafe_allow_html=True)
                        prev = answer_preview(qu.get("answer") or "")
                        if prev:
                            st.markdown(f'<p class="answer-preview">{prev}</p>',
                                        unsafe_allow_html=True)
                    with cols[1]:
                        if st.button("Open", key=f"open_{qu['questionId']}"):
                            st.session_state.selected_question_id = qu["questionId"]
                            st.session_state.mode = "explore_edit"
                            st.rerun()

    with tab_all:
        for qu in questions:
            hub = hub_by_id.get(qu["primaryHubId"], {})
            hub_name = hub.get("hubName", qu["primaryHubId"])
            lock_row = locks.get(qu["primaryHubId"], {})
            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(f"**{qu['question']}**")
                st.caption(f"Hub: {hub_name}")
                st.markdown(status_badge(qu["status"]), unsafe_allow_html=True)
                st.markdown(hub_lock_badge(lock_row, session_id), unsafe_allow_html=True)
            with cols[1]:
                if st.button("Answer", key=f"all_{qu['questionId']}"):
                    st.session_state.selected_question_id = qu["questionId"]
                    st.session_state.mode = "explore_edit"
                    st.rerun()


def render_explore_edit(hubs, lock_rows):
    qid = st.session_state.selected_question_id
    if not qid:
        st.session_state.mode = "explore"
        st.rerun()
        return

    question = q("getQuestion", {"questionId": qid})
    if not question:
        st.error("Question not found.")
        if st.button("Back to Explore"):
            st.session_state.mode = "explore"
            st.session_state.selected_question_id = None
            st.rerun()
        return

    hub = hub_map(hubs).get(question["primaryHubId"])
    ensure_session()
    lock_row = lock_status_map(lock_rows).get(question["primaryHubId"], {})
    if hub_locked_by_other(lock_row, st.session_state.session_id):
        st.warning(
            "Another session is currently working through this hub. "
            "Manual edits are still allowed in v1, but the guided "
            "Answer Questions mode will skip this hub."
        )

    if st.button("← Back to Explore"):
        st.session_state.mode = "explore"
        st.session_state.selected_question_id = None
        st.rerun()

    st.markdown('<div class="hub-spoke-panel">', unsafe_allow_html=True)
    question_editor(question, hub, key_prefix=f"explore_{qid}", show_notes=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_answer_mode(hubs, progress):
    ensure_session()
    renew_active_lock()
    progress = q("getProgress")

    st.markdown('<div class="hub-spoke-panel answer-mode-panel">', unsafe_allow_html=True)

    flash = st.session_state.pop("save_flash", None)
    if flash:
        st.toast(flash, icon="✅")
    if st.session_state.get("lock_warning"):
        st.warning(st.session_state.lock_warning)

    hub_id = st.session_state.get("active_answer_hub_id")
    if not hub_id:
        result = claim_and_start_answer()
        if not result.get("claimed"):
            st.info(result.get("message", "No hubs available."))
            if st.button("Back to Explore Hubs"):
                st.session_state.mode = "explore"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            return
        st.rerun()

    hub = hub_map(hubs).get(hub_id)
    if not hub:
        st.error("Active hub not found.")
        clear_answer_session()
        st.session_state.mode = "explore"
        st.rerun()

    total = progress["totalQuestions"]
    x = progress["nextQuestionNumber"]
    hub_prog = per_hub_progress(progress, hub_id)

    st.markdown(
        f'<p class="question-counter-answer">Question {x}/{total}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="hub-progress-answer">Hub progress: {hub_prog["answered"]}/{hub_prog["total"]} '
        f'answered in <strong>{hub["hubName"]}</strong></p>',
        unsafe_allow_html=True,
    )
    render_hub_context(hub, answer_mode=True)

    question_id = st.session_state.get("active_question_id")
    question = None
    if question_id:
        question = q("getQuestion", {"questionId": question_id})
    if not question or question.get("status") == "answered":
        question = q("getNextUnansweredQuestionForHubQuery", {"hubId": hub_id})
        if question:
            st.session_state.active_question_id = question["questionId"]

    if not question:
        m("releaseHubLock", {
            "hubId": hub_id,
            "sessionId": st.session_state.session_id,
        })
        st.session_state.active_answer_hub_id = None
        st.session_state.active_answer_hub_name = None
        st.session_state.active_question_id = None
        result = claim_and_start_answer()
        if result.get("claimed"):
            st.session_state.save_flash = (
                f"Hub complete! Continuing with **{result['hub']['hubName']}**."
            )
            st.rerun()
        progress = q("getProgress")
        if progress["unansweredQuestions"] == 0:
            st.balloons()
            st.success("All questions answered!")
            st.markdown(
                f"**{progress['answeredQuestions']}/{progress['totalQuestions']}** "
                f"complete ({progress['percentComplete']}%)"
            )
            render_export_panel(hubs)
        else:
            st.info(
                result.get("message", "Hub complete. No other hubs available right now.")
            )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to Explore Hubs"):
                st.session_state.mode = "explore"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.markdown(
        f'<div class="question-hero-answer">{question["question"]}</div>',
        unsafe_allow_html=True,
    )

    answer_key = "answer_mode_input"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = ""

    answer = st.text_area(
        "Your answer",
        key=answer_key,
        height=280,
        placeholder="Type your full answer. Enter creates new lines — use the button to submit.",
    )

    col_submit, col_exit = st.columns([1, 1])
    with col_submit:
        if st.button("Submit Answer", type="primary", key="submit_answer_btn"):
            m("saveAnswer", {
                "questionId": question["questionId"],
                "answer": answer,
            })
            st.session_state.pop(answer_key, None)
            next_q = q("getNextUnansweredQuestionForHubQuery", {"hubId": hub_id})
            if next_q:
                st.session_state.active_question_id = next_q["questionId"]
                st.session_state.save_flash = "Submitted — loading next question…"
            else:
                st.session_state.active_question_id = None
                st.session_state.save_flash = "Submitted — hub complete!"
            st.rerun()
    with col_exit:
        if st.button("Exit Answer Mode", key="exit_answer_mode"):
            clear_answer_session(show_warning=True)
            st.session_state.mode = "explore"
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ main


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    st.markdown(APP_CSS, unsafe_allow_html=True)

    client, err = boot_convex()
    if client is None:
        st.error("Convex connection required")
        st.markdown(
            f"**{err}**\n\n"
            "This app stores all hubs, questions, and answers in Convex. "
            "Set `CONVEX_URL` in `.env.local` (local) or Streamlit Cloud secrets (hosted). "
            "There is no local-file fallback."
        )
        st.stop()

    st.session_state.convex = client

    for key, default in [
        ("mode", "explore"),
        ("selected_question_id", None),
        ("export_data", None),
        ("save_flash", None),
        ("lock_warning", None),
        ("active_answer_hub_id", None),
        ("active_answer_hub_name", None),
        ("active_question_id", None),
    ]:
        st.session_state.setdefault(key, default)

    ensure_session()
    progress = q("getProgress")
    hubs = q("listHubs")
    questions = q("listQuestions")
    lock_rows = q("listHubLockStatuses")

    with st.sidebar:
        st.markdown("**Data source:** Convex")
        st.caption("All data read/write via Convex deployment")
        st.caption(f"**Session:** {st.session_state.session_label}")
        st.divider()
        st.markdown("**Global progress**")
        st.progress(progress["percentComplete"] / 100 if progress["totalQuestions"] else 0)
        st.markdown(
            f'<p class="progress-label">'
            f'{progress["answeredQuestions"]}/{progress["totalQuestions"]} answered '
            f'({progress["percentComplete"]}%)'
            f"</p>",
            unsafe_allow_html=True,
        )

        if st.session_state.mode == "answer" and st.session_state.active_answer_hub_id:
            st.divider()
            st.markdown("**Answer session**")
            st.markdown(f"Locked hub: **{st.session_state.active_answer_hub_name}**")
            st.caption("This hub is reserved for your session while you answer.")

        with st.expander("Hub lock status (debug)"):
            for row in lock_rows:
                badge = hub_lock_badge(row, st.session_state.session_id)
                st.markdown(f"{row['hubName']} {badge}", unsafe_allow_html=True)
                if row.get("lockExpiresAt") and row.get("lockStatus") == "locked":
                    stale = " (stale)" if row.get("isStale") else ""
                    st.caption(f"Expires: {row['lockExpiresAt']}{stale}")

        st.divider()
        if st.button("Explore Hubs", use_container_width=True):
            if st.session_state.mode == "answer":
                clear_answer_session(show_warning=True)
            st.session_state.mode = "explore"
            st.session_state.selected_question_id = None
            st.rerun()
        if st.button("Start Answering Questions", type="primary", use_container_width=True):
            if st.session_state.get("active_answer_hub_id"):
                renew_active_lock()
                st.session_state.mode = "answer"
            else:
                claim_and_start_answer()
            st.rerun()
        if st.button("Export", use_container_width=True):
            if st.session_state.mode == "answer":
                clear_answer_session(show_warning=True)
            st.session_state.mode = "export"
            st.rerun()

    st.title(APP_TITLE)

    mode = st.session_state.mode
    if mode == "answer":
        render_answer_mode(hubs, progress)
    elif mode == "explore_edit":
        render_explore_edit(hubs, lock_rows)
    elif mode == "export":
        if st.button("← Back"):
            st.session_state.mode = "explore"
            st.rerun()
        render_export_panel(hubs)
    else:
        render_explore(hubs, questions, progress, lock_rows)


if __name__ == "__main__":
    main()
