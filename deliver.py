"""
Zureon Fetch Framework — deliver.py
====================================
Framework 4: Outreach & Telegram Dispatcher

Accepts outputs from Frameworks 1, 2, and 3, crafts a channel-specific
cold outreach message, formats the final payload, and dispatches it to a
Telegram channel/chat via the Telegram Bot API.

Usage:
    from deliver import dispatch_pitch_package
    result = dispatch_pitch_package(fetch_data, audit_data, gen_data)
"""

from __future__ import annotations

import os
import logging
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("zureon.deliver")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


# ---------------------------------------------------------------------------
# 1. Outreach Copy Generator
# ---------------------------------------------------------------------------

def draft_outreach_message(biz_data: dict, audit_data: dict, gen_data: dict) -> str:
    """
    Craft a channel-specific cold outreach message based on the business's
    preferred outreach channel.
    """
    business_name = biz_data.get("business_name", "there")
    preferred = biz_data.get("contact_metadata", {}).get("preferred_outreach_channel", "Unknown")
    praise = gen_data.get("praise_narrative", "")
    current_score = audit_data.get("current_score", 0)
    potential_score = audit_data.get("potential_score", 0)
    gaps = audit_data.get("critical_gaps", [])
    primary_fix = audit_data.get("primary_fix_type", "our solution")

    gap_1 = gaps[0] if len(gaps) > 0 else "missing automation"
    gap_2 = gaps[1] if len(gaps) > 1 else "slow response times"

    if preferred == "WhatsApp":
        return (
            f"Hi {business_name} team! {praise}\n\n"
            f"Noticed a small delay on response times during off-hours, which might be letting "
            f"ready buyers slip away. We put together a quick 30-second concept video showing how "
            f"an automated AI assistant could instantly send specs and book consultations for you 24/7.\n\n"
            f"Mind if I drop the quick demo video link here?"
        )

    elif preferred == "Email":
        return (
            f"Subject: Quick idea for {business_name} (Automating lead capture)\n\n"
            f"Hi {business_name} Team,\n\n"
            f"{praise}\n\n"
            f"While reviewing your digital footprint, we noticed your online presence score is currently "
            f"at {current_score}/100, primarily due to:\n"
            f"- {gap_1}\n"
            f"- {gap_2}\n\n"
            f"Implementing a {primary_fix} could boost your setup score to {potential_score}/100 and "
            f"capture lost inquiries. We have generated a custom 30-second video demo illustrating how "
            f"this fix operates. Reply to this email if you would like to view the concept video."
        )

    else:  # Instagram DM / Default
        return (
            f"Hey {business_name}! {praise} We made a quick 30-sec video showing how an automated "
            f"DM assistant can capture instant sales for you 24/7. Mind if we send it over?"
        )


# ---------------------------------------------------------------------------
# 2. Telegram Telemetry Dispatcher
# ---------------------------------------------------------------------------

def send_telegram_notification(
    payload_text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """
    Post payload_text to a Telegram chat via the Bot API.

    Falls back to printing the payload to the terminal if env vars are
    missing or the API call fails.
    """
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    cid = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not cid:
        logger.warning("Telegram credentials missing. Printing payload to terminal instead.")
        print("\n" + "=" * 60)
        print("📬 TELEGRAM PAYLOAD (credentials not configured)")
        print("=" * 60)
        print(payload_text)
        print("=" * 60 + "\n")
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": cid,
        "text": payload_text,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            logger.info("Telegram notification dispatched successfully.")
            return True
        else:
            logger.warning(f"Telegram API returned error: {data}")
            print("\n" + "=" * 60)
            print("📬 TELEGRAM PAYLOAD (API error)")
            print("=" * 60)
            print(payload_text)
            print("=" * 60 + "\n")
            return False
    except Exception as exc:
        logger.warning(f"Telegram dispatch failed: {exc}. Printing payload to terminal.")
        print("\n" + "=" * 60)
        print("📬 TELEGRAM PAYLOAD (dispatch failed)")
        print("=" * 60)
        print(payload_text)
        print("=" * 60 + "\n")
        return False


# ---------------------------------------------------------------------------
# 3. Output Payload Formatting
# ---------------------------------------------------------------------------

def _format_telegram_payload(
    biz_data: dict,
    audit_data: dict,
    gen_data: dict,
    outreach_copy: str,
) -> str:
    """Assemble the final Markdown payload for Telegram."""
    business_name = biz_data.get("business_name", "Unknown")
    location = biz_data.get("location", "Unknown")
    current_score = audit_data.get("current_score", 0)
    potential_score = audit_data.get("potential_score", 0)
    preferred = biz_data.get("contact_metadata", {}).get("preferred_outreach_channel", "Unknown")
    contact_endpoint = _get_contact_endpoint(biz_data)
    ai_video_prompt = gen_data.get("ai_video_prompt", "")

    return (
        f"🚀 *[PROJECT ZUREON] PITCH PACKAGE READY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 *Business:* {business_name}\n"
        f"📍 *Location:* {location}\n"
        f"📊 *Presence Score:* {current_score}/100 ➔ *Potential:* {potential_score}/100\n"
        f"📱 *Preferred Channel:* {preferred} ({contact_endpoint})\n\n"
        f"💬 *DRAFT OUTREACH MESSAGE:*\n"
        f"```\n{outreach_copy}\n```\n\n"
        f"🎬 *GENERATED AI VIDEO PROMPT (Copy to Sora/Runway):*\n"
        f"```\n{ai_video_prompt}\n```\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def _get_contact_endpoint(biz_data: dict) -> str:
    """Return the actual contact handle/number for display."""
    meta = biz_data.get("contact_metadata", {})
    preferred = meta.get("preferred_outreach_channel", "Unknown")

    if preferred == "WhatsApp":
        return meta.get("phone_whatsapp", "N/A") or "N/A"
    elif preferred == "Email":
        return meta.get("email", "N/A") or "N/A"
    elif preferred == "Instagram DM":
        ig = biz_data.get("digital_assets", {}).get("instagram", "N/A")
        return ig or "N/A"
    return "N/A"


# ---------------------------------------------------------------------------
# 4. Main Orchestrator
# ---------------------------------------------------------------------------

def dispatch_pitch_package(
    fetch_data: dict,
    audit_data: dict,
    gen_data: dict,
) -> dict:
    """
    Orchestrate the full delivery pipeline for a single business.

    Parameters
    ----------
    fetch_data : dict
        Framework 1 output (business profile from fetcher.py).
    audit_data : dict
        Framework 2 output (audit analysis from analyzer.py).
    gen_data : dict
        Framework 3 output (creative assets from generator.py).

    Returns
    -------
    dict
        {
            "business_id": str,
            "business_name": str,
            "outreach_channel": str,
            "outreach_copy": str,
            "ai_video_prompt": str,
            "telegram_dispatched": bool,
        }
    """
    business_id = fetch_data.get("business_id", "unknown")
    business_name = fetch_data.get("business_name", "Unknown")
    preferred = fetch_data.get("contact_metadata", {}).get("preferred_outreach_channel", "Unknown")

    logger.info(f"Dispatching pitch package for '{business_name}' via {preferred}...")

    # 1. Draft outreach copy
    outreach_copy = draft_outreach_message(fetch_data, audit_data, gen_data)

    # 2. Format Telegram payload
    telegram_text = _format_telegram_payload(fetch_data, audit_data, gen_data, outreach_copy)

    # 3. Dispatch to Telegram
    dispatched = send_telegram_notification(telegram_text)

    # 4. Return structured result
    result = {
        "business_id": business_id,
        "business_name": business_name,
        "outreach_channel": preferred,
        "outreach_copy": outreach_copy,
        "ai_video_prompt": gen_data.get("ai_video_prompt", ""),
        "telegram_dispatched": dispatched,
    }

    logger.info(f"Pitch package ready for '{business_name}'. Telegram sent={dispatched}")
    return result


# ---------------------------------------------------------------------------
# Batch API (convenience)
# ---------------------------------------------------------------------------

def dispatch_batch(
    fetch_list: list[dict],
    audit_list: list[dict],
    gen_list: list[dict],
) -> list[dict]:
    """
    Dispatch pitch packages for a batch of businesses.
    Assumes lists are ordered and aligned by business_id.
    """
    results = []
    for f, a, g in zip(fetch_list, audit_list, gen_list):
        results.append(dispatch_pitch_package(f, a, g))
    return results


# ---------------------------------------------------------------------------
# CLI / Quick Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Demo with mock data from all three frameworks
    demo_fetch = {
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

    demo_audit = {
        "business_id": "abj_car_001",
        "current_score": 35,
        "potential_score": 85,
        "praise_points": [
            "Multi-channel social presence builds brand awareness across platforms.",
        ],
        "critical_gaps": [
            "No functioning website found — the business is invisible to search-driven customers.",
            "No WhatsApp click-to-chat link — Nigeria's #1 conversion channel is untapped.",
        ],
        "primary_fix_type": "Single-Page Business Website with WhatsApp Integration",
    }

    demo_gen = {
        "business_id": "abj_car_001",
        "praise_narrative": (
            "Great work establishing a strong brand presence for Apex Motors Abuja. "
            "Your visual presentation builds immediate customer trust and sets you apart in the market."
        ),
        "ai_video_prompt": (
            "Cinematic 9:16 vertical video. SCENE 1 (BEFORE): A customer sends a DM on a smartphone "
            "asking 'Price and specs?'. A clock spins showing 24 HOURS LATER with no reply. "
            "SCENE 2 (AFTER): Same DM sent. Within 1 second, an automated AI assistant replies "
            "with full pricing, photos, and a direct link to book a consultation on WhatsApp. "
            "TEXT OVERLAY: 'Never Lose Another Lead. Zureon AI.'"
        ),
    }

    result = dispatch_pitch_package(demo_fetch, demo_audit, demo_gen)
    print("\n📦 DISPATCH RESULT:")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
