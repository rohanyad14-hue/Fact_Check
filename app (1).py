"""
Fact-Check Agent — a "Truth Layer" for marketing PDFs.

Pipeline:
  1. Extract text from an uploaded PDF.
  2. Use an LLM to pull out checkable factual claims (stats, dates, figures).
  3. Search the live web for each claim.
  4. Use the LLM to judge each claim against the evidence:
        VERIFIED  — evidence supports it
        INACCURATE — close but outdated / off
        FALSE     — no evidence / contradicted
"""

import json
import os
import time

import requests
import streamlit as st
from pypdf import PdfReader

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Fact-Check Agent", page_icon="✓", layout="wide")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get(
    "ANTHROPIC_API_KEY", ""
)
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or st.secrets.get(
    "TAVILY_API_KEY", ""
)

MODEL = "claude-sonnet-4-6"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
TAVILY_URL = "https://api.tavily.com/search"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def extract_pdf_text(file) -> str:
    reader = PdfReader(file)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def call_claude(system: str, user: str, max_tokens: int = 2000) -> str:
    """Single-shot call to the Anthropic Messages API. Returns text."""
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        block.get("text", "") for block in data["content"] if block["type"] == "text"
    )


def parse_json(text: str):
    """Strip markdown fences and parse JSON safely."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def extract_claims(pdf_text: str) -> list:
    system = (
        "You are a fact-checking analyst. Extract specific, verifiable factual "
        "claims from the document — statistics, dates, financial figures, "
        "technical specs, named records or rankings. Ignore opinions, slogans, "
        "and vague marketing language. Return ONLY a JSON array of objects with "
        'keys "claim" (the exact claim, self-contained) and "type" '
        '(stat | date | financial | technical | other). Max 15 claims.'
    )
    user = f"Document:\n\n{pdf_text[:12000]}"
    raw = call_claude(system, user, max_tokens=2000)
    try:
        claims = parse_json(raw)
        return claims if isinstance(claims, list) else []
    except (json.JSONDecodeError, IndexError):
        return []


def web_search(query: str) -> str:
    """Search via Tavily and return concatenated snippets."""
    if not TAVILY_API_KEY:
        return ""
    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = []
        if data.get("answer"):
            parts.append("Summary: " + data["answer"])
        for r in data.get("results", []):
            parts.append(f"- {r.get('title','')}: {r.get('content','')}")
        return "\n".join(parts)
    except requests.RequestException:
        return ""


def verify_claim(claim: str, evidence: str) -> dict:
    system = (
        "You are a rigorous fact-checker. Given a CLAIM and web EVIDENCE, judge "
        "the claim. Respond ONLY as JSON with keys: "
        '"verdict" (one of VERIFIED, INACCURATE, FALSE), '
        '"correct_fact" (the real fact with the right number/date, or "" if '
        'verified), and "reason" (one sentence). '
        "VERIFIED = evidence supports the claim. "
        "INACCURATE = directionally right but outdated or off (e.g. wrong year, "
        "stale stat). FALSE = contradicted by evidence or no support found."
    )
    user = f"CLAIM: {claim}\n\nEVIDENCE:\n{evidence or '(no results found)'}"
    raw = call_claude(system, user, max_tokens=600)
    try:
        return parse_json(raw)
    except (json.JSONDecodeError, IndexError):
        return {"verdict": "FALSE", "correct_fact": "", "reason": "Could not verify."}


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
VERDICT_STYLE = {
    "VERIFIED": ("✅", "#16794a", "#e6f4ec"),
    "INACCURATE": ("⚠️", "#9a6700", "#fdf3d8"),
    "FALSE": ("❌", "#b42318", "#fce8e6"),
}

st.title("Fact-Check Agent")
st.caption(
    "A Truth Layer for marketing PDFs — extract claims, cross-reference live "
    "web data, flag what's outdated or false."
)

if not ANTHROPIC_API_KEY or not TAVILY_API_KEY:
    st.warning(
        "Missing API keys. Set `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` in your "
        "environment or Streamlit secrets to run verification."
    )

uploaded = st.file_uploader("Upload a PDF to fact-check", type=["pdf"])

if uploaded and st.button("Run fact-check", type="primary"):
    with st.spinner("Reading PDF…"):
        text = extract_pdf_text(uploaded)

    if not text.strip():
        st.error("No extractable text found in this PDF.")
        st.stop()

    with st.spinner("Extracting claims…"):
        claims = extract_claims(text)

    if not claims:
        st.error("No verifiable claims were found.")
        st.stop()

    st.subheader(f"{len(claims)} claims found")
    counts = {"VERIFIED": 0, "INACCURATE": 0, "FALSE": 0}
    progress = st.progress(0.0)
    results_area = st.container()

    for i, item in enumerate(claims):
        claim = item.get("claim", "")
        with st.spinner(f"Verifying claim {i+1} of {len(claims)}…"):
            evidence = web_search(claim)
            result = verify_claim(claim, evidence)
            time.sleep(0.2)  # gentle pacing

        verdict = result.get("verdict", "FALSE").upper()
        if verdict not in VERDICT_STYLE:
            verdict = "FALSE"
        counts[verdict] += 1
        icon, color, bg = VERDICT_STYLE[verdict]

        with results_area:
            st.markdown(
                f"""
<div style="border-left:4px solid {color};background:{bg};
padding:12px 16px;border-radius:6px;margin-bottom:10px;">
<div style="font-weight:600;color:{color};">{icon} {verdict}
<span style="color:#666;font-weight:400;font-size:0.8em;">
&nbsp;·&nbsp;{item.get('type','')}</span></div>
<div style="margin:6px 0;color:#111;"><b>Claim:</b> {claim}</div>
{f'<div style="color:#333;"><b>Correct fact:</b> {result.get("correct_fact")}</div>' if result.get("correct_fact") else ''}
<div style="color:#555;font-size:0.9em;margin-top:4px;">{result.get('reason','')}</div>
</div>
""",
                unsafe_allow_html=True,
            )
        progress.progress((i + 1) / len(claims))

    progress.empty()
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Verified", counts["VERIFIED"])
    c2.metric("⚠️ Inaccurate", counts["INACCURATE"])
    c3.metric("❌ False", counts["FALSE"])
