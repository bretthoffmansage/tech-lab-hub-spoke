"""OpenAI-backed grounded answer generation for the Transcript Assistant.

Reads OPENAI_API_KEY from the environment (Streamlit Cloud injects secrets
as env vars, so the same code works hosted). No key is ever hardcoded. With
no key — or no `openai` package — the app runs in retrieval-only mode via
generate_retrieval_only_response().

Model: OPENAI_MODEL env var, default gpt-4.1-mini (change the default below
or set the env var / Streamlit secret to switch).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_engine import format_sources_for_llm, short_excerpt  # noqa: E402

DEFAULT_MODEL = "gpt-4.1-mini"
MAX_CONTEXT_TURNS = 6          # recent conversation turns passed to the model
MAX_TURN_CHARS = 1500

SYSTEM_PROMPT = """You are the Tech Lab Transcript Assistant — a research \
assistant over an archive of company call transcripts (5 years of "Tech Lab" \
sessions about events, funnels, offers, marketing tech, and an AI tool \
called OBIE).

Hard rules:
- Ground every claim in the SOURCE MATERIAL provided in the user message. \
Never use outside knowledge to add facts about this company.
- Never invent facts, names, numbers, or quotes.
- Never attribute anything to a named speaker — the transcripts have no \
speaker labels.
- Never cite or invent timestamps — the transcripts have none.
- Sources tagged "mock-extraction hint" are keyword-extracted placeholders; \
treat them as pointers, prefer transcript chunks as ground truth.
- If the source material is weak, thin, or off-topic for the question, say \
so plainly before answering with what IS supported.
- If nothing relevant was provided, say the archive didn't return strong \
matches — do not answer from general knowledge.

Style:
- Lead with a direct, useful answer in natural prose. Short lists where they \
help. No rigid report sections, no headers unless genuinely useful.
- When the user asks for questions, hooks, or angles, write polished, \
client-ready items — but each must be grounded in the provided material, \
and they are adaptations, not verbatim transcript quotes.
- Quote short transcript phrases in quotation marks when they're strong.
- Keep answers tight: a few paragraphs or a focused list, not a report.
- End with a short "Sources used:" line listing source_file + chunk_id of \
only the sources you actually drew on."""

MODE_INSTRUCTIONS = {
    "answer": "Answer the question directly from the source material.",
    "questions": ("Turn the relevant source material into polished "
                  "right-fit-client questions — questions a strong-fit "
                  "prospect would recognize themselves in. Ground each one "
                  "in the material; do not present them as verbatim quotes."),
    "hooks": ("Turn the relevant source material into polished, scroll-"
              "stopping content hooks (one line each), grounded in the "
              "material's actual ideas and wording."),
    "client_facing": ("Rewrite the substance of the previous answer in "
                      "polished, client-facing language — clear, benefit-"
                      "led, no internal jargon — while staying strictly "
                      "grounded in the source material."),
}


def _get_api_key():
    return os.environ.get("OPENAI_API_KEY", "").strip() or None


def get_model():
    return os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL


def is_openai_configured():
    if not _get_api_key():
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def openai_status():
    if not _get_api_key():
        return "not configured (set OPENAI_API_KEY)"
    try:
        import openai  # noqa: F401
        return f"configured ({get_model()})"
    except ImportError:
        return "key present but `openai` package missing (pip install openai)"


def generate_grounded_answer(user_message, retrieved_sources,
                             conversation_context=None, mode="answer"):
    """Returns {"answer": str|None, "model": str, "error": str|None}."""
    if not is_openai_configured():
        return {"answer": None, "model": None,
                "error": "OpenAI is not configured."}
    import openai
    client = openai.OpenAI()
    model = get_model()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (conversation_context or [])[-MAX_CONTEXT_TURNS:]:
        messages.append({"role": turn["role"],
                         "content": turn["content"][:MAX_TURN_CHARS]})

    sources_block = format_sources_for_llm(retrieved_sources)
    strength_note = ""
    if retrieved_sources["strength"] == "weak":
        strength_note = ("\n\nNOTE: retrieval found limited material — open "
                         "by telling the user this answer is based on a "
                         "small set of matches.")
    instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["answer"])
    messages.append({
        "role": "user",
        "content": (f"SOURCE MATERIAL (keyword-retrieved from the transcript "
                    f"archive):\n\n{sources_block}\n\n---\n\n"
                    f"USER REQUEST: {user_message}\n\n"
                    f"TASK: {instruction}{strength_note}"),
    })

    try:
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0.4, max_tokens=1200)
        return {"answer": response.choices[0].message.content,
                "model": model, "error": None}
    except Exception as e:  # noqa: BLE001 — surface, don't crash the app
        return {"answer": None, "model": model, "error": str(e)}


def generate_retrieval_only_response(user_message, retrieved_sources):
    """No-LLM fallback: an honest summary of what retrieval found."""
    chunks = retrieved_sources["chunks"]
    assets = retrieved_sources["assets"]
    lines = [
        "OpenAI isn't configured, so here's the raw retrieved material "
        f"for **\"{user_message}\"** (keyword search, "
        f"{len(chunks)} transcript chunks + {len(assets)} extracted hints). "
        "Set `OPENAI_API_KEY` to get synthesized answers.",
        "",
    ]
    for c in chunks[:6]:
        lines.append(f"> {short_excerpt(c)}")
        lines.append(f"> — `{c['source_file']}` · chunk `{c['chunk_id']}`")
        lines.append("")
    if assets:
        lines.append("**Extracted hints (mock placeholders):**")
        for a in assets[:5]:
            lines.append(f"- *{a.get('asset_type', 'asset')}*: "
                         f"{short_excerpt(a, 180)} "
                         f"(`{a['source_file']}` · `{a['chunk_id']}`)")
    return "\n".join(lines)
