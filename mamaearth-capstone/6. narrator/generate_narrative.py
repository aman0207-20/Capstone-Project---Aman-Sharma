"""
Part 3 - GenAI-powered insight narrator (SCR: Situation - Complication - Resolution)

Run from the repo root, AFTER analysis/clean_and_eda.py has written narrator/findings.json:

    python narrator/generate_narrative.py                 # uses Gemini if a key is set, else offline
    python narrator/generate_narrative.py --offline       # force the keyless offline path
    python narrator/generate_narrative.py --save-sample   # also save output to narrator/sample_output.txt
    python narrator/generate_narrative.py --check-file narrator/sample_output.txt   # re-check a saved file

API key (free key from Google AI Studio) is read from the environment:
    GEMINI_API_KEY   (or GOOGLE_API_KEY)
Optional: GEMINI_MODEL to override the default model name.
With NO key the script still works - it uses the deterministic offline template.
"""
import argparse
import calendar
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_PATH = ROOT / "narrator" / "findings.json"
SAMPLE_PATH = ROOT / "narrator" / "sample_output.txt"

# NOTE: Gemini 2.5 models are scheduled for shutdown on 16 Oct 2026, so the default is a Gemini 3 model.
# If your AI Studio key does not list this model, set GEMINI_MODEL to one that it does.
DEFAULT_MODEL = "gemini-3.1-flash-lite"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_findings(path=FINDINGS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def month_name(yyyy_mm):
    """'2026-03' -> 'March'"""
    return calendar.month_name[int(yyyy_mm.split("-")[1])]


def get_api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


# ---------------------------------------------------------------------------
# Task 2 - prompts (system instruction is separate from the user prompt)
# ---------------------------------------------------------------------------
def build_system_instruction():
    return (
        "You are a senior data analyst writing for Mamaearth's regional ops and finance heads. "
        "Write a business narrative using the SCR structure with exactly three labeled sections, "
        "in this order: 'Situation:', 'Complication:', 'Resolution:'. "
        "Keep it to roughly 250 words, in plain business English that a non-technical reader can act on. "
        "STRICT RULE: every number you write must come from the findings supplied by the user and must "
        "appear with exactly the same value (you may add thousands separators and the rupee symbol). "
        "Do not invent, estimate, round differently, or derive any new statistic."
    )


def build_user_prompt(findings: dict):
    """Built entirely from the `findings` argument - nothing numeric is hardcoded here."""
    return (
        "Here are the verified findings from our returns and growth analysis. "
        "All currency values are in Indian Rupees (INR); return rates are percentages.\n\n"
        f"{json.dumps(findings, indent=2)}\n\n"
        "Write the Situation / Complication / Resolution narrative. Make sure it mentions: the cleaned total "
        "revenue, the return rate for each payment method, the highest-risk segment and its return rate, the "
        "reconciliation delta between raw and cleaned revenue (caused by duplicate orders), and the true peak "
        "month with its revenue (and explain that the outlier-inflated month only looked like the peak because "
        "of bulk orders). End with concrete recommended actions."
    )


# ---------------------------------------------------------------------------
# Task 2 + 3 + 4 - online path (Gemini) with locked parameters, error handling and offline fallback
# ---------------------------------------------------------------------------
def generate_scr_narrative(findings: dict, allow_fallback: bool = True) -> dict:
    """
    Returns {"status": "success", "narrative": str, "tokens": int, "source": ...}
         or {"status": "error",   "narrative": None, "message": str}   (only when allow_fallback=False)

    With allow_fallback=True (default) a missing key / failed API call falls back to the fully
    deterministic generate_scr_narrative_offline(), so the caller always gets a usable narrative.
    The caller never receives a raw exception.
    """
    try:
        api_key = get_api_key()
        if not api_key:
            raise RuntimeError("No Gemini API key configured (set GEMINI_API_KEY).")

        from google import genai
        from google.genai import types

        model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        client = genai.Client(
            api_key=api_key,
            # timeout is in MILLISECONDS in google-genai -> 30_000 ms = 30 s (brief requires >= 10 s)
            http_options=types.HttpOptions(timeout=30_000),
        )

        response = client.models.generate_content(
            model=model,
            contents=build_user_prompt(findings),
            config=types.GenerateContentConfig(
                system_instruction=build_system_instruction(),
                # temperature=0.0: this is a factual business report, not creative writing. We want the same
                # findings to give the same wording and, above all, no "creative" numbers.
                temperature=0.0,
                # 1500 (>= 300 required): a ~250-word 3-section narrative needs ~400 tokens, the rest is
                # headroom because Gemini 3 models may spend part of this budget on internal thinking.
                max_output_tokens=1500,
            ),
        )

        text = (response.text or "").strip()
        if not text:
            raise ValueError("Gemini returned an empty response (possibly blocked or truncated).")

        usage = getattr(response, "usage_metadata", None)
        tokens = getattr(usage, "total_token_count", None)
        return {"status": "success", "narrative": text, "tokens": tokens, "source": f"gemini:{model}"}

    except Exception as err:  # noqa: BLE001 - intentionally broad: the caller must never see a raw exception
        error_result = {"status": "error", "narrative": None, "message": str(err)}
        if not allow_fallback:
            return error_result
        fallback = generate_scr_narrative_offline(findings)
        fallback["fallback_reason"] = error_result["message"]
        return fallback


# ---------------------------------------------------------------------------
# Task 4 - offline path (no network, no key, deterministic)
# ---------------------------------------------------------------------------
def generate_scr_narrative_offline(findings: dict) -> dict:
    f = findings
    rr = f["return_rate_by_payment"]
    seg = f["highest_risk_segment"]
    peak = f["true_peak_month"]
    infl = f["outlier_inflated_month"]

    peak_m = month_name(peak["month"])
    infl_m = month_name(infl["month"])
    best_other = min((k for k in rr if k != "COD"), key=lambda k: rr[k])

    narrative = (
        "Situation:\n"
        f"After cleaning the order data (removing duplicate double-submitted orders and standardising payment "
        f"methods), Mamaearth's verified revenue is Rs {f['cleaned_total_revenue_inr']:,.2f}. This is "
        f"Rs {f['duplicate_reconciliation_delta_inr']:,.2f} lower than the raw figure of "
        f"Rs {f['raw_total_revenue_inr']:,.2f}; the whole gap comes from duplicate orders, not from "
        f"missing-value handling.\n\n"
        "Complication:\n"
        f"Returns are concentrated, not spread evenly. Cash-on-Delivery orders are returned at "
        f"{rr['COD']}%, against {rr['CARD']}% for Card and {rr['UPI']}% for UPI. The highest-risk segment is "
        f"{seg['payment_method']} orders from Tier-{seg['city_tier']} cities, where {seg['return_rate_pct']}% "
        f"of orders come back. Revenue also needs careful reading: {infl_m} looked like the best month "
        f"(Rs {infl['apparent_revenue_inr']:,.2f}) only because of two bulk orders; without them {infl_m} falls "
        f"to Rs {infl['corrected_revenue_inr']:,.2f}.\n\n"
        "Resolution:\n"
        f"{peak_m} is the genuine peak month at Rs {peak['revenue_inr']:,.2f}, so planning and inventory should "
        f"be benchmarked against {peak_m}, not {infl_m}. Ops should prioritise "
        f"{seg['payment_method']} in Tier-{seg['city_tier']} cities with address/phone verification and "
        f"order-confirmation calls, and finance should nudge buyers toward prepaid options such as "
        f"{best_other}, which has the lowest return rate ({rr[best_other]}%). Bulk orders should be flagged "
        f"separately in revenue reporting so they do not distort monthly trends."
    )
    return {"status": "success", "narrative": narrative, "tokens": 0, "source": "offline"}


# ---------------------------------------------------------------------------
# Task 5 - numeric accuracy checker
# ---------------------------------------------------------------------------
def _num(v):
    """97358.3 -> '97358.3', 44.4 -> '44.4' (no trailing zeros, no commas)."""
    return f"{v:f}".rstrip("0").rstrip(".")


def check_narrative(narrative: str, findings: dict, verbose: bool = True) -> bool:
    """Asserts the five required figures appear as substrings (after removing thousands commas)."""
    text = narrative.replace(",", "")
    peak = findings["true_peak_month"]
    required = [
        ("cleaned total revenue", _num(findings["cleaned_total_revenue_inr"])),
        ("COD return rate", _num(findings["return_rate_by_payment"]["COD"])),
        ("highest-risk segment return rate", _num(findings["highest_risk_segment"]["return_rate_pct"])),
        ("duplicate reconciliation delta", _num(findings["duplicate_reconciliation_delta_inr"])),
        ("true peak month name", month_name(peak["month"])),
        ("true peak month revenue", _num(peak["revenue_inr"])),
    ]
    all_ok = True
    for label, needle in required:
        ok = needle in text
        all_ok &= ok
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}: looking for '{needle}'")
    if verbose:
        print("  => ALL FIGURES PRESENT" if all_ok else "  => SOME FIGURES MISSING")
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate the SCR narrative from narrator/findings.json")
    ap.add_argument("--offline", action="store_true", help="force the offline (no API) path")
    ap.add_argument("--save-sample", action="store_true", help="write the narrative to narrator/sample_output.txt")
    ap.add_argument("--check-file", help="only run the numeric checker against an existing text file")
    args = ap.parse_args()

    findings = load_findings()

    if args.check_file:
        text = Path(args.check_file).read_text(encoding="utf-8")
        print(f"Checking {args.check_file}:")
        sys.exit(0 if check_narrative(text, findings) else 1)

    result = generate_scr_narrative_offline(findings) if args.offline else generate_scr_narrative(findings)

    print(f"Path used: {result['source']}")
    if result.get("fallback_reason"):
        print(f"(Gemini not used - reason: {result['fallback_reason']})")
    print(f"Tokens: {result['tokens']}\n")
    print(result["narrative"])
    print("\nNumeric accuracy check:")
    ok = check_narrative(result["narrative"], findings)

    if args.save_sample:
        SAMPLE_PATH.write_text(f"[source: {result['source']}]\n\n{result['narrative']}\n", encoding="utf-8")
        print(f"\nSaved {SAMPLE_PATH.relative_to(ROOT)}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
