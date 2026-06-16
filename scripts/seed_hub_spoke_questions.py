#!/usr/bin/env python3
"""Seed hub & spoke questions into Convex.

    python3 scripts/seed_hub_spoke_questions.py

Upserts hubs and questions via Convex mutations. Preserves existing non-empty
answers unless --force-answers is passed.

Requires: pip install convex   and CONVEX_URL in env or .env.local.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_lib import PROJECT_ROOT  # noqa: E402
from convex_lib import get_convex_client, to_convex_number  # noqa: E402

REPORTS_DIR = PROJECT_ROOT / "processed" / "reports"

INITIAL_HUBS = [
    {
        "hubId": "hub-event-tech-foundations",
        "hubName": "Event Tech Foundations",
        "description": (
            "Core technology decisions and setup principles for running "
            "virtual or hybrid events."
        ),
        "sortOrder": 1,
    },
    {
        "hubId": "hub-zoom-virtual-rooms",
        "hubName": "Zoom and Virtual Room Management",
        "description": (
            "Zoom setup, breakout rooms, room monitors, attendee movement, "
            "and virtual room operations."
        ),
        "sortOrder": 2,
    },
    {
        "hubId": "hub-registration-onboarding",
        "hubName": "Registration and Attendee Onboarding",
        "description": (
            "Registration flow, attendee view, onboarding experience, "
            "attendee instructions, access, login, and show-up readiness."
        ),
        "sortOrder": 3,
    },
    {
        "hubId": "hub-clickfunnels-funnel-tech",
        "hubName": "ClickFunnels / Funnel Tech",
        "description": (
            "ClickFunnels setup, registration pages, funnel simplification, "
            "funnel tech issues, and pre-event conversion flow."
        ),
        "sortOrder": 4,
    },
    {
        "hubId": "hub-obie-event-platform",
        "hubName": "OBIE / Event Platform",
        "description": (
            "OBIE setup, attendee onboarding, platform navigation, event "
            "platform experience, and support workflows."
        ),
        "sortOrder": 5,
    },
    {
        "hubId": "hub-studio-av-production",
        "hubName": "Studio / AV / Production Setup",
        "description": (
            "Camera, audio, lighting, ATEM Mini, software vs. hardware "
            "production choices, and studio setup."
        ),
        "sortOrder": 6,
    },
    {
        "hubId": "hub-event-support-help-desk",
        "hubName": "Event Support and Help Desk",
        "description": (
            "Help desk workflows, support agents, attendee access issues, "
            "live troubleshooting, and event support systems."
        ),
        "sortOrder": 7,
    },
    {
        "hubId": "hub-event-operations-team",
        "hubName": "Event Operations and Team Workflows",
        "description": (
            "Team roles, room monitors, registration agents, support "
            "workflows, backstage operations, and operational readiness."
        ),
        "sortOrder": 8,
    },
]

INITIAL_QUESTIONS = [
    # Event Tech Foundations
    ("hub-event-tech-foundations", 1,
     "q-event-tech-1",
     "What tech do I actually need to run a virtual event?"),
    ("hub-event-tech-foundations", 2,
     "q-event-tech-2",
     "How do I avoid overwhelming attendees with too many tools?"),
    ("hub-event-tech-foundations", 3,
     "q-event-tech-3",
     "What should I test before going live?"),
    # Zoom and Virtual Room Management
    ("hub-zoom-virtual-rooms", 1,
     "q-zoom-1",
     "How do I set up Zoom rooms for a smoother virtual event?"),
    ("hub-zoom-virtual-rooms", 2,
     "q-zoom-2",
     "What causes attendees to get lost between breakout rooms?"),
    ("hub-zoom-virtual-rooms", 3,
     "q-zoom-3",
     "How should I train a Zoom room monitor?"),
    # Registration and Attendee Onboarding
    ("hub-registration-onboarding", 1,
     "q-registration-1",
     "What should happen after someone registers for my virtual event?"),
    ("hub-registration-onboarding", 2,
     "q-registration-2",
     "How do I make sure attendees know where to go?"),
    ("hub-registration-onboarding", 3,
     "q-registration-3",
     "Why do people register but fail to show up prepared?"),
    # ClickFunnels / Funnel Tech
    ("hub-clickfunnels-funnel-tech", 1,
     "q-funnel-1",
     "How do I simplify my ClickFunnels setup before an event?"),
    ("hub-clickfunnels-funnel-tech", 2,
     "q-funnel-2",
     "What funnel tech mistakes create friction for buyers?"),
    ("hub-clickfunnels-funnel-tech", 3,
     "q-funnel-3",
     "How should my registration page connect to the event experience?"),
    # OBIE / Event Platform
    ("hub-obie-event-platform", 1,
     "q-obie-1",
     "How should I onboard attendees into OBIE before an event?"),
    ("hub-obie-event-platform", 2,
     "q-obie-2",
     "What does a client need to understand before using OBIE?"),
    ("hub-obie-event-platform", 3,
     "q-obie-3",
     "How can an event platform improve the attendee experience?"),
    # Studio / AV / Production Setup
    ("hub-studio-av-production", 1,
     "q-studio-1",
     "What camera, lighting, and audio setup do I need for a better virtual event?"),
    ("hub-studio-av-production", 2,
     "q-studio-2",
     "How does poor lighting affect trust during an online event?"),
    ("hub-studio-av-production", 3,
     "q-studio-3",
     "What is the simplest studio setup for a high-quality event?"),
    # Event Support and Help Desk
    ("hub-event-support-help-desk", 1,
     "q-support-1",
     "What should my help desk team be ready to troubleshoot during a live event?"),
    ("hub-event-support-help-desk", 2,
     "q-support-2",
     "How should support agents handle attendee access issues?"),
    ("hub-event-support-help-desk", 3,
     "q-support-3",
     "What support systems help attendees feel taken care of during an event?"),
    # Event Operations and Team Workflows
    ("hub-event-operations-team", 1,
     "q-ops-1",
     "What roles does my team need to manage event tech smoothly?"),
    ("hub-event-operations-team", 2,
     "q-ops-2",
     "How should registration agents, room monitors, and support staff work together?"),
    ("hub-event-operations-team", 3,
     "q-ops-3",
     "What operational checks should happen before the event starts?"),
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_hub_record(hub):
    ts = now_iso()
    return {
        "hubId": hub["hubId"],
        "hubName": hub["hubName"],
        "description": hub["description"],
        "sortOrder": to_convex_number(hub["sortOrder"]),
        "createdAt": ts,
        "updatedAt": ts,
    }


def build_question_record(primary_hub_id, sort_order, question_id, question_text):
    ts = now_iso()
    return {
        "questionId": question_id,
        "question": question_text,
        "answer": "",
        "status": "unanswered",
        "primaryHubId": primary_hub_id,
        "secondaryHubIds": [],
        "sortOrder": to_convex_number(sort_order),
        "createdAt": ts,
        "updatedAt": ts,
    }


def write_report(lines):
    report_path = REPORTS_DIR / "hub_spoke_seed_report.md"
    if REPORTS_DIR.exists():
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Report written to {report_path}")
    else:
        print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Seed hub/spoke data to Convex")
    parser.add_argument(
        "--force-answers",
        action="store_true",
        help="Allow overwriting existing non-empty answers",
    )
    args = parser.parse_args()

    client, err = get_convex_client()
    if client is None:
        print(f"CONVEX ERROR: {err}")
        return 1

    preserve = not args.force_answers
    hub_inserted = hub_updated = 0
    q_inserted = q_updated = q_preserved = 0

    print(f"Seeding {len(INITIAL_HUBS)} hubs and {len(INITIAL_QUESTIONS)} questions…")
    print(f"Preserve existing answers: {preserve}")

    for hub in INITIAL_HUBS:
        result = client.mutation("hubSpoke:upsertHub", {"hub": build_hub_record(hub)})
        if result["result"] == "inserted":
            hub_inserted += 1
        else:
            hub_updated += 1
        print(f"  Hub {hub['hubId']}: {result['result']}")

    for primary_hub_id, sort_order, question_id, question_text in INITIAL_QUESTIONS:
        existing = client.query("hubSpoke:getQuestion", {"questionId": question_id})
        had_answer = bool(existing and (existing.get("answer") or "").strip())

        result = client.mutation(
            "hubSpoke:upsertQuestion",
            {
                "question": build_question_record(
                    primary_hub_id, sort_order, question_id, question_text
                ),
                "preserveAnswer": preserve,
            },
        )
        if result["result"] == "inserted":
            q_inserted += 1
        else:
            q_updated += 1
            if had_answer and preserve:
                q_preserved += 1
        print(f"  Question {question_id}: {result['result']}")

    progress = client.query("hubSpoke:getProgress", {})
    lines = [
        "# Hub & Spoke Seed Report",
        "",
        f"Generated: {now_iso()}",
        "",
        "## Summary",
        "",
        f"- Hubs inserted: {hub_inserted}",
        f"- Hubs updated: {hub_updated}",
        f"- Questions inserted: {q_inserted}",
        f"- Questions updated: {q_updated}",
        f"- Answers preserved: {q_preserved}",
        "",
        "## Progress after seed",
        "",
        f"- Total questions: {progress['totalQuestions']}",
        f"- Answered: {progress['answeredQuestions']}",
        f"- Unanswered: {progress['unansweredQuestions']}",
        f"- Percent complete: {progress['percentComplete']}%",
    ]
    write_report(lines)

    print("\nSeed complete.")
    print(f"  Hubs: {hub_inserted} inserted, {hub_updated} updated")
    print(f"  Questions: {q_inserted} inserted, {q_updated} updated")
    print(f"  Answers preserved: {q_preserved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
