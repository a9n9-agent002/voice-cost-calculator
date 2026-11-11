#!/usr/bin/env python3
"""Checks that docs/self-hosted-tts-cost-per-minute.md cannot drift from the measurement file.

    python3 tests/test_tts_doc.py             # verify
    python3 tests/test_tts_doc.py --selftest  # 5 mutations that must be caught

Every figure on the page is recomputed here from docs/self-hosted-tts-measurements.json. If a number is
re-measured, regenerate the JSON and the page together; this file is the reason the two cannot disagree.
"""
import copy
import json
import re
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "self-hosted-tts-cost-per-minute.md")
DATA = os.path.join(ROOT, "docs", "self-hosted-tts-measurements.json")
USD_PER_CPU_HOUR = 6.00 / 730.0
TOL_USD = 0.0002


def commas(v):
    return "{:,}".format(v)


def violations(data, doc):
    """Return a list of problems; empty means the page agrees with the measurement file."""
    bad = []
    tiers = {t["quality"]: t for t in data["tiers"]}
    for quality, t in tiers.items():
        audio_min = t["speedup_median"] * 60.0
        if abs(audio_min - t["audio_minutes_per_cpu_hour"]) > 0.06:
            bad.append("%s: audio_minutes_per_cpu_hour %s != median speedup x 60 = %.2f"
                       % (quality, t["audio_minutes_per_cpu_hour"], audio_min))
        cpu_h = 1000.0 / t["audio_minutes_per_cpu_hour"]
        if abs(cpu_h - t["cpu_hours_per_1000_audio_minutes"]) > 0.002:
            bad.append("%s: cpu_hours_per_1000 %s != 1000/audio_min = %.3f"
                       % (quality, t["cpu_hours_per_1000_audio_minutes"], cpu_h))
        usd = t["cpu_hours_per_1000_audio_minutes"] * USD_PER_CPU_HOUR
        if abs(usd - t["usd_per_1000_audio_minutes"]) > TOL_USD:
            bad.append("%s: usd_per_1000 %s != cpu_hours x %.6f = %.4f"
                       % (quality, t["usd_per_1000_audio_minutes"], USD_PER_CPU_HOUR, usd))
        hours = t["speedup_median"] * 730.0
        if abs(hours - t["audio_hours_per_core_month"]) > 1.0:
            bad.append("%s: audio_hours_per_core_month %s != speedup x 730 = %.0f"
                       % (quality, t["audio_hours_per_core_month"], hours))
        if not t.get("runs") or len(t["runs"]) < 3:
            bad.append("%s: fewer than three timed runs recorded" % quality)
        if not t.get("peak_rss_mb"):
            bad.append("%s: no peak memory measurement" % quality)

    cpm = data["chars_per_audio_minute"]
    hosted_min = data["hosted_reference"]["usd_per_1000_chars"] * cpm / 1000.0
    if abs(hosted_min - data["hosted_reference"]["usd_per_audio_minute"]) > 1e-4:
        bad.append("hosted usd_per_audio_minute %s != rate x chars/min = %.5f"
                   % (data["hosted_reference"]["usd_per_audio_minute"], hosted_min))
    if abs(hosted_min * 1000.0 - data["hosted_reference"]["usd_per_1000_audio_minutes"]) > 0.02:
        bad.append("hosted usd_per_1000 %s != %.2f"
                   % (data["hosted_reference"]["usd_per_1000_audio_minutes"], hosted_min * 1000.0))
    for key, quality in (("ratio_medium_vs_hosted", "medium"), ("ratio_high_vs_hosted", "high")):
        want = hosted_min * 1000.0 / tiers[quality]["usd_per_1000_audio_minutes"]
        if abs(want - data[key]) / want > 0.01:
            bad.append("%s %s != %.1f" % (key, data[key], want))

    # --- the page must print those numbers, formatted the way a reader reads them ---
    low, med, high = tiers["low"], tiers["medium"], tiers["high"]
    must = [
        ("low speedup", "%.2f\u00d7" % low["speedup_median"]),
        ("medium speedup", "%.2f\u00d7" % med["speedup_median"]),
        ("high speedup", "%.3f\u00d7" % high["speedup_median"]),
        ("medium audio-min per CPU-hour", "%.1f minutes of audio per CPU-hour" % med["audio_minutes_per_cpu_hour"]),
        ("medium CPU-hours", "%.3f CPU-hours" % med["cpu_hours_per_1000_audio_minutes"]),
        ("medium cost", "$%.4f" % med["usd_per_1000_audio_minutes"]),
        ("low cost", "$%.4f" % low["usd_per_1000_audio_minutes"]),
        ("high cost", "$%.4f" % high["usd_per_1000_audio_minutes"]),
        ("low RAM", "%.1f MB" % low["peak_rss_mb"]),
        ("medium RAM", "%.1f MB" % med["peak_rss_mb"]),
        ("high RAM", "%.1f MB" % high["peak_rss_mb"]),
        ("chars per audio minute", "%s characters per audio minute" % "{:,.1f}".format(cpm)),
        ("hosted per 1,000", "$%.2f per 1,000" % data["hosted_reference"]["usd_per_1000_audio_minutes"]),
        ("hosted per 1,000 (table)", "$%.2f" % data["hosted_reference"]["usd_per_1000_audio_minutes"]),
        ("ratio medium", "%s\u00d7" % commas(int(round(data["ratio_medium_vs_hosted"])))),
        ("audio hours per core-month", "%s hours" % commas(int(med["audio_hours_per_core_month"]))),
    ]
    doc_norm = doc.replace("**", "")
    for label, needle in must:
        if needle not in doc_norm:
            bad.append("page does not print %s (%r)" % (label, needle))

    # arithmetic sentence of its own: 100,000 audio minutes at the medium rate
    want = 100000.0 / med["audio_minutes_per_cpu_hour"] * USD_PER_CPU_HOUR
    if ("$%.2f" % want) not in doc_norm:
        bad.append("page does not print the 100,000-minute cost $%.2f" % want)
    # tier ratio (high vs low processor time)
    want_ratio = low["speedup_median"] / high["speedup_median"]
    if ("%.1f\u00d7" % want_ratio) not in doc_norm:
        bad.append("page does not print the high-vs-low ratio %.1f" % want_ratio)

    # --- hygiene the publishing guards care about ---
    urls = re.findall(r"https?://\S+", doc)
    foreign = [u for u in urls if "a9n9.net" not in u]
    if foreign:
        bad.append("page carries %d URL(s) besides the author credit: %s" % (len(foreign), foreign[:3]))
    for token in ("utm_", "ref=", "?ref", "dub_id"):
        if token in doc:
            bad.append("tracking token in page: %s" % token)
    words = len(doc.split())
    if words < 600:
        bad.append("page is only %d words" % words)
    return bad


def main():
    data = json.load(open(DATA))
    doc = open(DOC).read()

    if "--selftest" in sys.argv:
        base = violations(copy.deepcopy(data), doc)
        if base:
            print("baseline already failing:")
            for b in base:
                print("  -", b)
            sys.exit(1)
        cases = []
        d1 = copy.deepcopy(data); d1["tiers"][1]["usd_per_1000_audio_minutes"] = 0.02; cases.append(("price inflated", d1, doc))
        d2 = copy.deepcopy(data); d2["tiers"][0]["speedup_median"] = 6.0; cases.append(("speedup lowered", d2, doc))
        d3 = copy.deepcopy(data); d3["chars_per_audio_minute"] = 900.0; cases.append(("chars/min changed", d3, doc))
        d4 = copy.deepcopy(data); cases.append(("page loses the costs", d4, doc.replace("$0.0146", "$0.0150")))
        d5 = copy.deepcopy(data); cases.append(("page loses the hosted number", d5, doc.replace("$88.31", "$90.00")))
        caught = 0
        for name, dd, dd_doc in cases:
            v = violations(dd, dd_doc)
            print("%-32s %s" % (name, "caught" if v else "MISSED"))
            caught += 1 if v else 0
        print("%d/%d mutations caught" % (caught, len(cases)))
        sys.exit(0 if caught == len(cases) else 1)

    bad = violations(data, doc)
    for b in bad:
        print("FAIL:", b)
    print("test_tts_doc: %s" % ("FAIL %d problem(s)" % len(bad) if bad else "OK (all figures recompute)"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
