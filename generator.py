"""
Zureon Fetch Framework — generator.py
======================================
Framework 3: Creative Engine & Storyboard Generator

Accepts the audit analysis payload from Framework 2 (analyzer.py) and
generates two outputs:
    1. A conversational praise narrative to open the outreach message.
    2. A detailed 9:16 vertical video generation prompt (Before vs. After).

Usage:
    from generator import generate_pitch_assets
    pitch = generate_pitch_assets(audit_dict)
"""

from __future__ import annotations

import json
import re
import os
import logging
from typing import Optional

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
import requests

try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False

try:
    from groq import Groq
    _HAS_GROQ = True
except ImportError:
    _HAS_GROQ = False

try:
    import openai
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("zureon.generator")

# ---------------------------------------------------------------------------
# Configuration (shared with analyzer.py — same env vars)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("ZUREON_LLM_PROVIDER", "groq").lower()
LLM_API_KEY = os.getenv("ZUREON_LLM_API_KEY", "")
LLM_MODEL = os.getenv("ZUREON_LLM_MODEL", "")
OLLAMA_HOST = os.getenv("ZUREON_OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Fallback Data
# ---------------------------------------------------------------------------

def _fallback_data(analysis_data: dict) -> dict:
    """Return default structured output when LLM fails."""
    business_name = analysis_data.get("business_name", "your business")
    business_id = analysis_data.get("business_id", "unknown")
    return {
        "business_id": business_id,
        "praise_narrative": (
            f"Great work establishing a strong brand presence for {business_name}. "
            f"Your visual presentation builds immediate customer trust and sets you apart in the market."
        ),
        "ai_video_prompt": (
            "Cinematic 9:16 vertical video. "
            "SCENE 1 (BEFORE): A customer sends a DM on a smartphone asking 'Price and specs?'. "
            "A clock spins showing 24 HOURS LATER with no reply. "
            "SCENE 2 (AFTER): Same DM sent. Within 1 second, an automated AI assistant replies "
            "with full pricing, photos, and a direct link to book a consultation on WhatsApp. "
            "TEXT OVERLAY: 'Never Lose Another Lead. Zureon AI.'"
        ),
    }


# ---------------------------------------------------------------------------
# LLM Wrappers (mirrors analyzer.py for consistency)
# ---------------------------------------------------------------------------

def _llm_call_gemini(prompt: str, api_key: str, model: str = "gemini-1.5-flash") -> str:
    if not _HAS_GEMINI:
        raise RuntimeError("google.generativeai not installed. Run: pip install google-generativeai")
    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(model)
    resp = m.generate_content(prompt)
    return resp.text


def _llm_call_groq(prompt: str, api_key: str, model: str = "llama3-8b-8192") -> str:
    if not _HAS_GROQ:
        raise RuntimeError("groq not installed. Run: pip install groq")
    client = Groq(api_key=api_key)
    chat = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a B2B creative director. Return ONLY raw JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=900,
    )
    return chat.choices[0].message.content


def _llm_call_openai(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    if not _HAS_OPENAI:
        raise RuntimeError("openai not installed. Run: pip install openai")
    client = openai.OpenAI(api_key=api_key)
    chat = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a B2B creative director. Return ONLY raw JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=900,
    )
    return chat.choices[0].message.content


def _llm_call_ollama(prompt: str, host: str, model: str = "llama3") -> str:
    url = f"{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "system": "You are a B2B creative director. Return ONLY raw JSON.",
        "options": {"temperature": 0.5},
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", "")


def _call_llm(prompt: str) -> str:
    """Route to the configured LLM provider."""
    provider = LLM_PROVIDER
    api_key = LLM_API_KEY

    if provider == "gemini":
        model = LLM_MODEL or "gemini-1.5-flash"
        return _llm_call_gemini(prompt, api_key, model)
    elif provider == "groq":
        model = LLM_MODEL or "llama3-8b-8192"
        return _llm_call_groq(prompt, api_key, model)
    elif provider == "openai":
        model = LLM_MODEL or "gpt-4o-mini"
        return _llm_call_openai(prompt, api_key, model)
    elif provider == "ollama":
        model = LLM_MODEL or "llama3"
        return _llm_call_ollama(prompt, OLLAMA_HOST, model)
    else:
        raise RuntimeError(f"Unknown LLM provider: {provider}")


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def _build_creative_prompt(analysis_data: dict) -> str:
    """Construct the exact creative director prompt for the LLM."""
    business_name = analysis_data.get("business_name", "Unknown")
    business_id = analysis_data.get("business_id", "unknown")
    category = analysis_data.get("category", "Local Business")
    praise_points = analysis_data.get("praise_points", [])
    critical_gaps = analysis_data.get("critical_gaps", [])
    primary_fix = analysis_data.get("primary_fix_type", "AI Automation Solution")

    # Format lists for readability
    praise_bullets = "\n".join(f"  - {p}" for p in praise_points) if praise_points else "  - Strong local reputation"
    gap_bullets = "\n".join(f"  - {g}" for g in critical_gaps) if critical_gaps else "  - Missing automation systems"

    prompt = f"""You are an expert B2B creative director and direct-response advertising strategist.

Target Business Audit Data:
- Business Name: {business_name}
- Category: {category}
- Praise Points:
{praise_bullets}
- Critical Gaps:
{gap_bullets}
- Primary Fix Solution: {primary_fix}

Tasks:
1. Praise Narrative: Write a 2-sentence opening narrative highlighting what they do well so the pitch opens on a high note. Be warm, specific, and conversational — like a marketer who has genuinely studied their business.

2. AI Video Storyboard Prompt: Create a detailed, cinematic 9:16 vertical video prompt for AI video generators (Runway/Sora). 

The video prompt MUST follow this strict structure:
- Format: 9:16 vertical smartphone format.
- Visual Style: Photorealistic, cinematic lighting, sharp detail.
- Scene 1 (The Problem / Before): Show the customer experiencing friction on a phone screen (e.g., sending an Instagram DM or website inquiry asking for pricing/specs, a clock spinning or time-lapse passing, and leaving without a reply).
- Scene 2 (The Zureon Fix / After): Show the same interaction, but an instant AI bot responds within 1 second delivering pricing, spec sheet PDF, and an automated button to book via WhatsApp.
- Text Overlay: A bold 3-word closing text overlay on screen summarizing the fix.

Return ONLY a valid JSON string matching this exact structure:
{{
  "business_id": "{business_id}",
  "praise_narrative": "string",
  "ai_video_prompt": "string"
}}

Do NOT wrap the JSON in markdown code blocks. Return raw JSON only."""

    return prompt


# ---------------------------------------------------------------------------
# JSON Sanitizer
# ---------------------------------------------------------------------------

def _sanitize_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pitch_assets(analysis_data: dict) -> dict:
    """
    Generate outreach pitch assets from an audit analysis.

    Parameters
    ----------
    analysis_data : dict
        A single entry from analyzer.py output (Framework 2 payload).

    Returns
    -------
    dict
        {
            "business_id": str,
            "praise_narrative": str,
            "ai_video_prompt": str
        }
    """
    business_name = analysis_data.get("business_name", "?")
    logger.info(f"Generating pitch assets for '{business_name}'...")

    try:
        prompt = _build_creative_prompt(analysis_data)
        raw_response = _call_llm(prompt)
        result = _sanitize_llm_json(raw_response)

        # Validate required keys
        required = {"business_id", "praise_narrative", "ai_video_prompt"}
        if not required.issubset(result.keys()):
            raise ValueError(f"LLM response missing keys: {required - result.keys()}")

        logger.info(f"Creative generation succeeded for '{business_name}'.")
        return result

    except Exception as exc:
        logger.warning(f"[WARN] Creative generation failed for '{business_name}': {exc}. Using fallback.")
        return _fallback_data(analysis_data)


# ---------------------------------------------------------------------------
# Batch API (convenience)
# ---------------------------------------------------------------------------

def generate_batch_pitch_assets(analysis_list: list[dict]) -> list[dict]:
    """Run generate_pitch_assets over a list of audit analyses."""
    return [generate_pitch_assets(a) for a in analysis_list]


# ---------------------------------------------------------------------------
# CLI / Quick Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Demo with mock audit data from Framework 2
    demo_audit = {
        "business_id": "abj_car_001",
        "business_name": "Apex Motors Abuja",
        "category": "Car Dealers",
        "current_score": 35,
        "potential_score": 85,
        "praise_points": [
            "Multi-channel social presence builds brand awareness across platforms.",
            "Strong showroom reputation in Maitama, Abuja.",
        ],
        "critical_gaps": [
            "No functioning website found — the business is invisible to search-driven customers.",
            "No WhatsApp click-to-chat link — Nigeria's #1 conversion channel is untapped.",
        ],
        "primary_fix_type": "Single-Page Business Website with WhatsApp Integration",
    }

    result = generate_pitch_assets(demo_audit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
