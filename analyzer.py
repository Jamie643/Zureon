"""
Zureon Fetch Framework — analyzer.py
=====================================
Framework 2: Marketing & Operations Auditor

Accepts the JSON payload from Framework 1 (fetcher.py), runs programmatic
technical checks, feeds the facts to an LLM for strategic evaluation, and
returns a structured audit with scores, praise points, critical gaps, and
recommended fixes.

Usage:
    from analyzer import analyze_business_gaps
    audit = analyze_business_gaps(business_profile)
"""

from __future__ import annotations

import json
import re
import os
import logging
from typing import Optional
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
import requests

# Optional LLM SDKs — imported lazily so the script loads even if absent
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
logger = logging.getLogger("zureon.analyzer")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("ZUREON_LLM_PROVIDER", "groq").lower()  # gemini | groq | openai | ollama
LLM_API_KEY = os.getenv("ZUREON_LLM_API_KEY", "")
LLM_MODEL = os.getenv("ZUREON_LLM_MODEL", "")
OLLAMA_HOST = os.getenv("ZUREON_OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Step 1: Programmatic Rule Checker
# ---------------------------------------------------------------------------

def _check_website(url: Optional[str]) -> tuple[bool, bool]:
    """Return (has_website, has_ssl)."""
    if not url:
        return False, False

    has_ssl = url.startswith("https://")

    try:
        resp = requests.get(url, timeout=3.0, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        has_website = resp.status_code == 200
    except Exception as exc:
        logger.debug(f"Website check failed for {url}: {exc}")
        has_website = False

    return has_website, has_ssl


def _check_whatsapp_cta(website_url: Optional[str], snippet: str) -> bool:
    """Search website HTML or snippet for WhatsApp CTA links."""
    # 1. Check snippet first (fast, no extra HTTP)
    if "wa.me" in snippet.lower() or "api.whatsapp.com" in snippet.lower():
        return True

    # 2. If website exists, fetch and scan HTML
    if website_url:
        try:
            resp = requests.get(
                website_url,
                timeout=3.0,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            html = resp.text.lower()
            if "wa.me" in html or "api.whatsapp.com" in html:
                return True
        except Exception as exc:
            logger.debug(f"WhatsApp CTA check failed for {website_url}: {exc}")

    return False


def _count_social_channels(digital_assets: dict) -> int:
    """Count non-None social links (Instagram, Facebook, X/Twitter)."""
    keys = ["instagram", "facebook", "x_twitter"]
    return sum(1 for k in keys if digital_assets.get(k) is not None)


def run_rule_checks(business_data: dict) -> dict:
    """
    Run pure-Python technical checks on a single business profile.

    Returns a dict with:
        has_website, has_ssl, has_whatsapp_cta, social_count
    """
    website_url = business_data.get("digital_assets", {}).get("website")
    snippet = business_data.get("raw_snippet_summary", "")

    has_website, has_ssl = _check_website(website_url)
    has_whatsapp_cta = _check_whatsapp_cta(website_url, snippet)
    social_count = _count_social_channels(business_data.get("digital_assets", {}))

    return {
        "has_website": has_website,
        "has_ssl": has_ssl,
        "has_whatsapp_cta": has_whatsapp_cta,
        "social_count": social_count,
    }


# ---------------------------------------------------------------------------
# Step 2: Manual Score Calculator (used for fallback + LLM grounding)
# ---------------------------------------------------------------------------

def calculate_scores(rule_results: dict) -> tuple[int, int]:
    """
    Calculate current_score and potential_score using the defined rules.

    Scoring Rules:
        Base = 100
        -30  if no website
        -20  if no WhatsApp CTA
        -15  if no SSL
        -10  per missing social channel under 2
        Target potential = 85-95
    """
    score = 100

    if not rule_results.get("has_website", False):
        score -= 30
    if not rule_results.get("has_whatsapp_cta", False):
        score -= 20
    if not rule_results.get("has_ssl", False):
        score -= 15

    social = rule_results.get("social_count", 0)
    missing_under_2 = max(0, 2 - social)
    score -= missing_under_2 * 10

    current_score = max(0, score)
    # Potential is what they could reach by fixing all gaps
    potential_score = min(95, max(85, current_score + 25))

    return current_score, potential_score


# ---------------------------------------------------------------------------
# LLM Wrappers
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
            {"role": "system", "content": "You are a B2B marketing auditor. Return ONLY raw JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    return chat.choices[0].message.content


def _llm_call_openai(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    if not _HAS_OPENAI:
        raise RuntimeError("openai not installed. Run: pip install openai")
    client = openai.OpenAI(api_key=api_key)
    chat = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a B2B marketing auditor. Return ONLY raw JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    return chat.choices[0].message.content


def _llm_call_ollama(prompt: str, host: str, model: str = "llama3") -> str:
    url = f"{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "system": "You are a B2B marketing auditor. Return ONLY raw JSON.",
        "options": {"temperature": 0.3},
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

def _build_audit_prompt(business_data: dict, rule_results: dict) -> str:
    """Construct the exact system prompt + facts for the LLM."""
    business_name = business_data.get("business_name", "Unknown")
    business_id = business_data.get("business_id", "unknown")
    preferred = business_data.get("contact_metadata", {}).get("preferred_outreach_channel", "Unknown")
    snippet = business_data.get("raw_snippet_summary", "")
    digital = business_data.get("digital_assets", {})

    current_score, potential_score = calculate_scores(rule_results)

    # Build a clean list of active channels for context
    active_channels = [k for k, v in digital.items() if v is not None and k != "website"]
    channel_str = ", ".join(active_channels) if active_channels else "None"

    prompt = f"""You are an elite B2B marketing auditor for small local businesses. Translate these technical audit facts into a structured audit JSON payload.

Calculated Technical Facts:
- Business Name: {business_name}
- Has Website: {rule_results['has_website']}
- Has SSL Security: {rule_results['has_ssl']}
- Has Direct WhatsApp CTA: {rule_results['has_whatsapp_cta']}
- Active Social Channels: {rule_results['social_count']} ({channel_str})
- Preferred Outreach: {preferred}
- Business Snippet: {snippet}

Scoring Rules:
1. Base score = 100.
2. Deduct 30 points if `has_website` is False.
3. Deduct 20 points if `has_whatsapp_cta` is False.
4. Deduct 15 points if `has_ssl` is False.
5. Deduct 10 points for each missing social channel under 2.
6. Target Potential Score should be between 85 and 95.

Current calculated score: {current_score}
Target potential score: {potential_score}

Return ONLY a raw JSON string matching this exact structure:
{{
  "business_id": "{business_id}",
  "current_score": int,
  "potential_score": int,
  "praise_points": [
    "Praise 1 (What they are doing well based on their active channels or snippet)",
    "Praise 2"
  ],
  "critical_gaps": [
    "Gap 1 (Main technical/operational flaw hurting conversions)",
    "Gap 2"
  ],
  "primary_fix_type": "Specific software or bot solution (e.g., Automated WhatsApp Lead Capture Bot)"
}}

Do NOT wrap the JSON in markdown code blocks. Return raw JSON only."""

    return prompt


# ---------------------------------------------------------------------------
# JSON Sanitizer
# ---------------------------------------------------------------------------

def _sanitize_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Fallback Builder
# ---------------------------------------------------------------------------

def _build_fallback_audit(business_data: dict, rule_results: dict) -> dict:
    """Manually construct the audit dict when the LLM fails."""
    business_id = business_data.get("business_id", "unknown")
    business_name = business_data.get("business_name", "Unknown")
    current_score, potential_score = calculate_scores(rule_results)

    # Build praise based on what they HAVE
    praise = []
    if rule_results.get("has_website"):
        praise.append(f"{business_name} has an active website — a strong foundation for digital trust.")
    if rule_results.get("has_ssl"):
        praise.append("SSL certificate is enabled, protecting visitor data and improving search ranking.")
    if rule_results.get("has_whatsapp_cta"):
        praise.append("Direct WhatsApp CTA is present — customers can reach them instantly.")
    if rule_results.get("social_count", 0) >= 2:
        praise.append("Multi-channel social presence builds brand awareness across platforms.")
    if not praise:
        praise.append("Business has a discoverable online presence — the first step toward digital growth.")

    # Build gaps based on what they LACK
    gaps = []
    if not rule_results.get("has_website"):
        gaps.append("No functioning website found — the business is invisible to search-driven customers.")
    if not rule_results.get("has_ssl") and rule_results.get("has_website"):
        gaps.append("Website lacks SSL (HTTPS) — browsers flag it as insecure, killing trust and SEO.")
    if not rule_results.get("has_whatsapp_cta"):
        gaps.append("No WhatsApp click-to-chat link — Nigeria's #1 conversion channel is untapped.")
    if rule_results.get("social_count", 0) < 2:
        gaps.append(f"Only {rule_results['social_count']} social channel(s) active — under-2 channels limit reach and retargeting.")
    if not gaps:
        gaps.append("Consider adding a newsletter or CRM to capture leads beyond social DMs.")

    # Determine primary fix
    if not rule_results.get("has_website"):
        fix = "Single-Page Business Website with WhatsApp Integration"
    elif not rule_results.get("has_whatsapp_cta"):
        fix = "Automated WhatsApp Lead Capture Bot"
    elif not rule_results.get("has_ssl"):
        fix = "SSL Certificate + HTTPS Migration"
    elif rule_results.get("social_count", 0) < 2:
        fix = "Social Media Cross-Posting Automation"
    else:
        fix = "CRM + Newsletter Lead Nurturing System"

    return {
        "business_id": business_id,
        "business_name": business_name,
        "category": business_data.get("category", "Local Business"),
        "current_score": current_score,
        "potential_score": potential_score,
        "praise_points": praise[:2],
        "critical_gaps": gaps[:2],
        "primary_fix_type": fix,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_business_gaps(business_data: dict) -> dict:
    """
    Run the full audit pipeline on a single business profile.

    Parameters
    ----------
    business_data : dict
        A single entry from fetcher.py output (Framework 1 payload).

    Returns
    -------
    dict
        Structured audit JSON with scores, praise, gaps, and fix recommendation.
    """
    # 1. Rule checks
    rule_results = run_rule_checks(business_data)
    logger.info(
        f"Rule checks for '{business_data.get('business_name', '?')}': "
        f"website={rule_results['has_website']}, ssl={rule_results['has_ssl']}, "
        f"whatsapp={rule_results['has_whatsapp_cta']}, social={rule_results['social_count']}"
    )

    # 2. Try LLM
    try:
        prompt = _build_audit_prompt(business_data, rule_results)
        raw_response = _call_llm(prompt)
        audit = _sanitize_llm_json(raw_response)

        # Validate required keys
        required = {"business_id", "current_score", "potential_score", "praise_points", "critical_gaps", "primary_fix_type"}
        if not required.issubset(audit.keys()):
            raise ValueError(f"LLM response missing keys: {required - audit.keys()}")

        logger.info(f"LLM audit succeeded for '{business_data.get('business_name', '?')}'.")
        return audit

    except Exception as exc:
        logger.warning(f"[WARN] LLM audit failed for '{business_data.get('business_name', '?')}': {exc}. Using manual fallback.")
        return _build_fallback_audit(business_data, rule_results)


# ---------------------------------------------------------------------------
# Batch API (convenience)
# ---------------------------------------------------------------------------

def analyze_batch(business_profiles: list[dict]) -> list[dict]:
    """Run analyze_business_gaps over a list of profiles."""
    return [analyze_business_gaps(p) for p in business_profiles]


# ---------------------------------------------------------------------------
# CLI / Quick Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Demo with mock data from Framework 1
    demo_profile = {
        "business_id": "abj_car_001",
        "business_name": "Apex Motors Abuja",
        "category": "Car Dealers",
        "location": "Abuja, Nigeria",
        "digital_assets": {
            "website": "http://apexmotors.example.ng",
            "instagram": "https://instagram.com/apexmotors_abj",
            "facebook": "https://facebook.com/apexmotorsabj",
            "x_twitter": None,
        },
        "contact_metadata": {
            "phone_whatsapp": "+2348012345678",
            "email": "sales@apexmotors.example.ng",
            "preferred_outreach_channel": "WhatsApp",
        },
        "raw_snippet_summary": (
            "Apex Motors Abuja - Premium pre-owned luxury cars. "
            "Showroom at Maitama, Abuja. Call/WhatsApp 08012345678 for price inquiries."
        ),
    }

    result = analyze_business_gaps(demo_profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
