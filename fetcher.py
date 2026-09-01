"""
Zureon Fetch Framework — fetcher.py
====================================
Framework 1: Discovery & Aggregation

Discovers businesses by category + location, extracts digital assets
(website, social handles) and contact metadata, then returns a clean
JSON-ready payload.

Usage:
    from fetcher import fetch_business_data
    results = fetch_business_data("Car Dealers", "Abuja, Nigeria", target_count=3)
"""

from __future__ import annotations

import re
import json
import logging
import hashlib
from typing import Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
try:
    from ddgs import DDGS
except ImportError as _imp_err:  # pragma: no cover
    DDGS = None  # type: ignore
    logging.warning("ddgs not installed. Run: pip install ddgs")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("zureon.fetcher")

# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------
RE_WHATSAPP = re.compile(
    r"(?:https?://wa\.me/|api\.whatsapp\.com/send\?phone=|\+?234|0)[789][01]\d{8}",
    re.IGNORECASE,
)
RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
RE_INSTAGRAM = re.compile(
    r"https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.-]+)/?",
    re.IGNORECASE,
)
RE_FACEBOOK = re.compile(
    r"https?://(?:www\.)?facebook\.com/([a-zA-Z0-9_.-]+)/?",
    re.IGNORECASE,
)
RE_TWITTER = re.compile(
    r"https?://(?:www\.)?(?:twitter|x)\.com/([a-zA-Z0-9_.-]+)/?",
    re.IGNORECASE,
)
RE_PHONE_NG = re.compile(
    r"(?:\+?234|0)[789][01]\d{8}",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Fallback Mock Data
# ---------------------------------------------------------------------------
FALLBACK_MOCK_DATA = [
    {
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
    },
    {
        "business_id": "abj_car_002",
        "business_name": "Capital Auto Hub",
        "category": "Car Dealers",
        "location": "Abuja, Nigeria",
        "digital_assets": {
            "website": None,
            "instagram": "https://instagram.com/capitalautohub_ng",
            "facebook": None,
            "x_twitter": None,
        },
        "contact_metadata": {
            "phone_whatsapp": None,
            "email": "capitalautohub@gmail.com",
            "preferred_outreach_channel": "Email",
        },
        "raw_snippet_summary": (
            "Capital Auto Hub Abuja. Clean foreign used cars in Garki. "
            "Send email to capitalautohub@gmail.com for catalogue."
        ),
    },
]


# ---------------------------------------------------------------------------
# Internal Data Model
# ---------------------------------------------------------------------------
@dataclass
class _RawCandidate:
    """Intermediate representation before final schema assembly."""
    name: str
    category: str
    location: str
    snippet: str = ""
    website: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    x_twitter: Optional[str] = None
    phone_whatsapp: Optional[str] = None
    email: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slug_id(name: str, category: str, location: str) -> str:
    """Generate a deterministic business_id."""
    raw = f"{name}|{category}|{location}".lower().replace(" ", "_")
    h = hashlib.md5(raw.encode()).hexdigest()[:6]
    loc_prefix = location.lower().replace(",", "").replace(" ", "_")[:3]
    cat_prefix = category.lower().replace(" ", "_")[:3]
    safe_name = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))[:20]
    return f"{loc_prefix}_{cat_prefix}_{safe_name}_{h}"


def _extract_from_snippet(snippet: str) -> dict:
    """Run the regex cascade over a search snippet."""
    findings = {
        "phone_whatsapp": None,
        "email": None,
        "instagram": None,
        "facebook": None,
        "x_twitter": None,
    }

    # WhatsApp / phone
    m = RE_WHATSAPP.search(snippet)
    if m:
        findings["phone_whatsapp"] = m.group(0)
    else:
        m2 = RE_PHONE_NG.search(snippet)
        if m2:
            findings["phone_whatsapp"] = m2.group(0)

    # Email
    m = RE_EMAIL.search(snippet)
    if m:
        findings["email"] = m.group(0)

    # Instagram
    m = RE_INSTAGRAM.search(snippet)
    if m:
        findings["instagram"] = m.group(0)

    # Facebook
    m = RE_FACEBOOK.search(snippet)
    if m:
        findings["facebook"] = m.group(0)

    # Twitter / X
    m = RE_TWITTER.search(snippet)
    if m:
        findings["x_twitter"] = m.group(0)

    return findings


def _preferred_channel(phone: Optional[str], email: Optional[str], instagram: Optional[str]) -> str:
    """Hierarchy: WhatsApp > Email > Instagram DM > Unknown."""
    if phone:
        return "WhatsApp"
    if email:
        return "Email"
    if instagram:
        return "Instagram DM"
    return "Unknown"


def _clean_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _infer_business_name(title: str, snippet: str, category: str) -> str:
    """Heuristic: use title, stripped of trailing pipes/dashes."""
    name = title.split("|")[0].split("-")[0].split(":")[0].strip()
    # Remove common suffixes like " - Facebook", " | Instagram"
    name = re.sub(r"\s*[-|]\s*(Facebook|Instagram|Twitter|X|LinkedIn|Home|Official).*", "", name, flags=re.I)
    return name if name else "Unknown Business"


# ---------------------------------------------------------------------------
# Search Engine
# ---------------------------------------------------------------------------
def _run_ddgs_search(query: str, max_results: int = 10) -> list[dict]:
    """Execute a DuckDuckGo text search and return raw results."""
    if DDGS is None:
        logger.warning("DDGS unavailable — cannot run search.")
        return []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            logger.info(f"DDGS query '{query}' returned {len(results)} results.")
            return results
    except Exception as exc:
        logger.warning(f"DDGS search failed for query '{query}': {exc}")
        return []


def _social_fallback_search(business_name: str, location: str, platform: str) -> Optional[str]:
    """Targeted site-specific search for a social handle."""
    site = "instagram.com" if platform == "instagram" else "facebook.com"
    query = f'site:{site} "{business_name}" "{location}"'
    results = _run_ddgs_search(query, max_results=5)
    for r in results:
        url = r.get("href", "")
        if not url:
            url = r.get("link", "")
        if platform == "instagram" and "instagram.com" in url:
            return _clean_url(url)
        if platform == "facebook" and "facebook.com" in url:
            return _clean_url(url)
    return None


# ---------------------------------------------------------------------------
# Core Pipeline
# ---------------------------------------------------------------------------
def _discover_candidates(category: str, location: str, target_count: int) -> list[_RawCandidate]:
    """Run broad DDGS search, parse snippets, and build candidate list."""
    query = f"{category} in {location} address phone email"
    results = _run_ddgs_search(query, max_results=max(target_count * 4, 20))

    candidates: list[_RawCandidate] = []
    seen_names: set[str] = set()

    for r in results:
        title = r.get("title", "")
        snippet = r.get("body", "") or r.get("snippet", "")
        href = r.get("href", "") or r.get("link", "")

        if not title or not snippet:
            continue

        name = _infer_business_name(title, snippet, category)
        norm_name = name.lower()
        if norm_name in seen_names:
            continue
        seen_names.add(norm_name)

        extracted = _extract_from_snippet(snippet + " " + title + " " + href)

        # Derive website from result link if it looks like a business site
        website = None
        if href and not any(s in href.lower() for s in ("facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com")):
            website = _clean_url(href)

        cand = _RawCandidate(
            name=name,
            category=category,
            location=location,
            snippet=snippet,
            website=website,
            instagram=extracted.get("instagram"),
            facebook=extracted.get("facebook"),
            x_twitter=extracted.get("x_twitter"),
            phone_whatsapp=extracted.get("phone_whatsapp"),
            email=extracted.get("email"),
        )
        candidates.append(cand)

        if len(candidates) >= target_count:
            break

    return candidates


def _enrich_with_fallbacks(candidates: list[_RawCandidate], location: str) -> list[_RawCandidate]:
    """For candidates missing Instagram or Facebook, run targeted site searches."""
    for cand in candidates:
        if not cand.instagram:
            url = _social_fallback_search(cand.name, location, "instagram")
            if url:
                cand.instagram = url
                logger.info(f"[Fallback] Found Instagram for '{cand.name}': {url}")

        if not cand.facebook:
            url = _social_fallback_search(cand.name, location, "facebook")
            if url:
                cand.facebook = url
                logger.info(f"[Fallback] Found Facebook for '{cand.name}': {url}")
    return candidates


def _assemble_payload(candidates: list[_RawCandidate]) -> list[dict]:
    """Convert internal candidates to the public output schema."""
    payload: list[dict] = []
    for cand in candidates:
        preferred = _preferred_channel(cand.phone_whatsapp, cand.email, cand.instagram)
        entry = {
            "business_id": _slug_id(cand.name, cand.category, cand.location),
            "business_name": cand.name,
            "category": cand.category,
            "location": cand.location,
            "digital_assets": {
                "website": cand.website,
                "instagram": cand.instagram,
                "facebook": cand.facebook,
                "x_twitter": cand.x_twitter,
            },
            "contact_metadata": {
                "phone_whatsapp": cand.phone_whatsapp,
                "email": cand.email,
                "preferred_outreach_channel": preferred,
            },
            "raw_snippet_summary": cand.snippet,
        }
        payload.append(entry)
    return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_business_data(
    category: str,
    location: str,
    target_count: int = 3,
    use_mock: bool = False,
) -> list[dict]:
    """
    Discover businesses by category and location.

    Parameters
    ----------
    category : str
        Business category (e.g. "Car Dealers").
    location : str
        Geographic location (e.g. "Abuja, Nigeria").
    target_count : int, default 3
        Number of businesses to discover.
    use_mock : bool, default False
        If True, skip live search and return mock data immediately.

    Returns
    -------
    list[dict]
        Clean JSON-ready payload conforming to the Zureon schema.
    """
    if use_mock:
        logger.info("[Mock] Returning fallback dataset (use_mock=True).")
        return FALLBACK_MOCK_DATA

    try:
        # 1. Discovery
        candidates = _discover_candidates(category, location, target_count)

        # 2. Social fallback
        candidates = _enrich_with_fallbacks(candidates, location)

        # 3. Assembly
        payload = _assemble_payload(candidates)

        if not payload:
            logger.warning("[WARN] Fetcher returned 0 live results. Using local fallback mock dataset.")
            return FALLBACK_MOCK_DATA

        logger.info(f"Fetcher returned {len(payload)} business profile(s).")
        return payload

    except Exception as exc:
        logger.warning(f"[WARN] Fetcher network failed: {exc}. Using local fallback mock dataset.")
        return FALLBACK_MOCK_DATA


# ---------------------------------------------------------------------------
# CLI / Quick Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    cat = sys.argv[1] if len(sys.argv) > 1 else "Car Dealers"
    loc = sys.argv[2] if len(sys.argv) > 2 else "Abuja, Nigeria"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    data = fetch_business_data(cat, loc, target_count=count)
    print(json.dumps(data, indent=2, ensure_ascii=False))
