"""
Zureon Fetch Framework — main.py
=================================
CLI Orchestrator: End-to-End Pipeline Runner

Ties Frameworks 1, 2, 3, and 4 into a unified, robust pipeline.

Usage:
    python main.py --category "Car Dealers" --location "Abuja, Nigeria" --count 3
    python main.py --mock                              # Offline test with mock data
    python main.py --category "Restaurants" --location "Lagos, Nigeria" --count 5
"""

from __future__ import annotations

import argparse
import json
import sys
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Framework Imports
# ---------------------------------------------------------------------------
# Support both package import and direct script execution
try:
    from fetcher import fetch_business_data
    from analyzer import analyze_business_gaps
    from generator import generate_pitch_assets
    from deliver import dispatch_pitch_package
except ImportError:
    from zureon.fetcher import fetch_business_data
    from zureon.analyzer import analyze_business_gaps
    from zureon.generator import generate_pitch_assets
    from zureon.deliver import dispatch_pitch_package

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("zureon.main")

# ---------------------------------------------------------------------------
# Visual Helpers
# ---------------------------------------------------------------------------

WIDTH = 64


def _header(text: str) -> str:
    return f"\n{'━' * WIDTH}\n  {text}\n{'━' * WIDTH}"


def _separator() -> str:
    return "─" * WIDTH


def _success(text: str) -> str:
    return f"  ✓ {text}"


def _warn(text: str) -> str:
    return f"  ⚠ {text}"


def _info(text: str) -> str:
    return f"  → {text}"


# ---------------------------------------------------------------------------
# Pipeline Runner
# ---------------------------------------------------------------------------

def run_pipeline(
    category: str,
    location: str,
    target_count: int,
    use_mock: bool = False,
) -> List[Dict[str, Any]]:
    """
    Execute the full Zureon pipeline end-to-end.

    Returns a list of enriched dispatch result dicts — one per processed business.
    """
    start_time = datetime.now(timezone.utc)
    enriched_results: List[Dict[str, Any]] = []

    print(_header(f"PROJECT ZUREON  |  {start_time.strftime('%Y-%m-%d %H:%M UTC')}"))
    print(_info(f"Category: {category}"))
    print(_info(f"Location: {location}"))
    print(_info(f"Target Count: {target_count}"))
    print(_info(f"Mode: {'MOCK (offline)' if use_mock else 'LIVE (network)'}"))
    print(_separator())

    # =====================================================================
    # STEP 1: DISCOVERY (Framework 1)
    # =====================================================================
    print(_header("STEP 1: DISCOVERY & AGGREGATION (Framework 1)"))

    try:
        profiles = fetch_business_data(
            category=category,
            location=location,
            target_count=target_count,
            use_mock=use_mock,
        )
    except Exception as exc:
        logger.error(f"Discovery phase failed: {exc}")
        print(_warn(f"Discovery failed: {exc}"))
        return []

    if not profiles:
        print(_warn("No business profiles discovered. Exiting."))
        return []

    print(_success(f"Discovered {len(profiles)} business profile(s)."))
    for p in profiles:
        name = p.get("business_name", "Unknown")
        print(_info(f"  • {name}"))
    print(_separator())

    # =====================================================================
    # STEP 2-4: PER-BUSINESS PIPELINE
    # =====================================================================
    print(_header("STEP 2-4: AUDIT → GENERATE → DELIVER (Frameworks 2-4)"))

    for idx, profile in enumerate(profiles, start=1):
        biz_name = profile.get("business_name", f"Business-{idx}")
        biz_id = profile.get("business_id", f"unknown_{idx}")

        print(f"\n  [{idx}/{len(profiles)}] Processing: {biz_name}")
        print(f"  {_separator()}")

        try:
            # Framework 2: Audit
            print(_info("Running marketing & operations audit..."))
            audit = analyze_business_gaps(profile)
            current_score = audit.get("current_score", 0)
            potential_score = audit.get("potential_score", 0)
            primary_fix = audit.get("primary_fix_type", "N/A")
            print(_success(f"Audit complete. Score: {current_score}/100 → Potential: {potential_score}/100"))
            print(_info(f"  Primary fix: {primary_fix}"))

            # Framework 3: Creative
            print(_info("Generating creative assets..."))
            creative = generate_pitch_assets(audit)
            print(_success("Praise narrative + AI video prompt generated."))

            # Framework 4: Delivery
            print(_info("Drafting outreach & dispatching to Telegram..."))
            dispatch = dispatch_pitch_package(profile, audit, creative)
            telegram_ok = dispatch.get("telegram_dispatched", False)
            channel = dispatch.get("outreach_channel", "Unknown")
            print(_success(f"Dispatched via {channel}. Telegram: {'SENT' if telegram_ok else 'FALLBACK (printed)'}"))

            # Store combined result for summary + JSON output
            enriched_results.append({
                **dispatch,
                "current_score": current_score,
                "potential_score": potential_score,
                "primary_fix_type": primary_fix,
            })

        except Exception as exc:
            logger.error(f"Processing failed for '{biz_name}': {exc}")
            print(_warn(f"SKIPPED '{biz_name}' due to error: {exc}"))
            # Append a minimal failure record so the summary still accounts for it
            enriched_results.append({
                "business_id": biz_id,
                "business_name": biz_name,
                "outreach_channel": profile.get("contact_metadata", {}).get("preferred_outreach_channel", "Unknown"),
                "outreach_copy": "[ERROR: Processing failed]",
                "ai_video_prompt": "[ERROR: Processing failed]",
                "telegram_dispatched": False,
                "current_score": None,
                "potential_score": None,
                "error": str(exc),
            })
            continue

    # =====================================================================
    # STEP 5: SUMMARY REPORT
    # =====================================================================
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

    print(_header("EXECUTION SUMMARY"))
    print(_info(f"Total targets processed: {len(enriched_results)}"))
    print(_info(f"Successful deliveries: {sum(1 for r in enriched_results if not r.get('error'))}"))
    print(_info(f"Failures: {sum(1 for r in enriched_results if r.get('error'))}"))
    print(_info(f"Elapsed time: {elapsed:.1f}s"))
    print(_separator())

    # Summary table
    print(f"\n  {'Business':<28} {'Score':<12} {'Potential':<12} {'Channel':<14} {'Telegram':<10}")
    print(f"  {'─' * 28} {'─' * 12} {'─' * 12} {'─' * 14} {'─' * 10}")

    for r in enriched_results:
        name = r.get("business_name", "?")[:26]
        channel = r.get("outreach_channel", "?")[:12]
        telegram = "SENT" if r.get("telegram_dispatched") else "FALLBACK"

        if r.get("error"):
            score_str = "ERR"
            pot_str = "ERR"
        else:
            score_str = f"{r.get('current_score', 0)}/100"
            pot_str = f"{r.get('potential_score', 0)}/100"

        print(f"  {name:<28} {score_str:<12} {pot_str:<12} {channel:<14} {telegram:<10}")

    print(_separator())
    print(_success("Pipeline complete. Check Telegram or terminal output for full payloads."))
    print(f"{'━' * WIDTH}\n")

    return enriched_results


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="zureon",
        description="Project Zureon — End-to-End B2B Outreach Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Default: Car Dealers in Abuja
  python main.py --mock                       # Offline test with mock data
  python main.py --category "Restaurants" --location "Lagos, Nigeria" --count 5
        """,
    )

    parser.add_argument(
        "--category",
        type=str,
        default="Car Dealers",
        help="Business category to search (default: 'Car Dealers')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Abuja, Nigeria",
        help="Search target location (default: 'Abuja, Nigeria')",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Target count for candidate discovery (default: 3)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force fetcher to use local mock data for zero-network testing",
    )

    args = parser.parse_args()

    results = run_pipeline(
        category=args.category,
        location=args.location,
        target_count=args.count,
        use_mock=args.mock,
    )

    # Optional: dump full JSON to stdout for piping
    if results:
        print("\n📦 FULL JSON OUTPUT (pipe to file with > results.json):")
        print(json.dumps(results, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
