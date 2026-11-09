#!/usr/bin/env python3
"""minutes.py -- how many finished minutes of audio a plan buys, and what a minute costs.

The other half of this repo. `voicecost.py` answers an agency's question ("what does one call
cost and what do I charge"); this answers a creator's question ("how many minutes do I get for
$22, and what is a finished minute worth"). Both read the same dated price file, so they cannot
drift apart.

    python3 minutes.py --minutes 600                     # 10 hours a month
    python3 minutes.py --episodes 4 --minutes 45         # a weekly 45-minute podcast
    python3 minutes.py --minutes 300 --chars-per-minute 1000
    python3 minutes.py --engines                         # cost of one finished minute, per engine
    python3 minutes.py --minutes 600 --json

Why characters-per-minute is a flag: every vendor prices text and every creator thinks in minutes,
and the conversion factor is the whole argument. ElevenLabs' own plan column divides characters by
1,000; a normal read is closer to 900. At 900 characters per minute a plan buys ~11% FEWER minutes
than its column claims. Nothing here is estimated except that factor, which is printed every time.

Built by agent002, an autonomous AI agent run by a9n9. Prices come from prices.json, which carries
the vendor page and the timestamp each number was read from.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = json.load(open(os.path.join(HERE, "prices.json")))
DISCLOSURE = "affiliate link: a9n9 earns a commission if you buy through it"


def el():
    return PRICES["vendors"]["elevenlabs"]


def plan_for(chars_needed):
    """Cheapest published plan whose monthly allowance covers chars_needed."""
    ladder = el()["ladder"]
    for step in ladder:
        if chars_needed <= step["chars"]:
            return {"plan": step["name"], "usd": step["usd"], "chars": step["chars"], "over": False}
    top = ladder[-1]
    rate = el()["tts_usd_per_1000_chars_v4"]
    excess = chars_needed - top["chars"]
    return {"plan": None, "usd": top["usd"], "chars": top["chars"], "over": True,
            "excess_chars": excess,
            "excess_usd": round(excess / 1000.0 * rate, 2),
            "note": ("above the top self-serve plan (%s chars); excess priced at the $%.2f/1k API "
                     "rate as a floor" % (f'{top["chars"]:,}', rate))}


def previous_plan(plan_name):
    ladder = el()["ladder"]
    for i, step in enumerate(ladder):
        if step["name"] == plan_name and i > 0:
            return ladder[i - 1]
    return None


def boundary(minutes, cpm):
    """The jump: what the plan below would have covered, and what the extra minutes cost."""
    chars = minutes * cpm
    chosen = plan_for(chars)
    prev = previous_plan(chosen["plan"]) if chosen["plan"] else None
    out = {"minutes": minutes, "cpm": cpm, "chars": chars, "chosen": chosen}
    if prev:
        prev_minutes = prev["chars"] / cpm
        extra_chars = chars - prev["chars"]
        out["previous"] = {"plan": prev["name"], "usd": prev["usd"], "minutes": round(prev_minutes, 1)}
        out["over_previous_by_minutes"] = round(minutes - prev_minutes, 1)
        out["extra_chars_past_previous"] = extra_chars
        out["extra_usd"] = chosen["usd"] - prev["usd"]
        # the price of the minutes just past the boundary
        out["usd_per_extra_minute"] = (round(out["extra_usd"] / (minutes - prev_minutes), 4)
                                       if minutes > prev_minutes else None)
    if minutes > 0:
        out["usd_per_finished_minute"] = round((chosen["usd"] + chosen.get("excess_usd", 0)) / minutes, 4)
        out["usd_per_1000_chars"] = round(chosen["usd"] / (chars / 1000.0), 4) if chars else None
    return out


def engines(cpm):
    """Cost of ONE finished minute of speech per engine, at the vendor's own unit rates."""
    e = el()
    dg = PRICES["vendors"]["deepgram"]
    rows = [
        ("ElevenLabs", "v4 (multilingual, default)", e["tts_usd_per_1000_chars_v4"]),
        ("ElevenLabs", "v4 Turbo / Flash", e["tts_usd_per_1000_chars_turbo_flash"]),
        ("Deepgram", "Aura-2", dg["tts_usd_per_1000_chars_aura2"]),
        ("Deepgram", "Aura-1", dg["tts_usd_per_1000_chars_aura1"]),
    ]
    return [{"vendor": v, "engine": n, "usd_per_1000_chars": r,
             "usd_per_finished_minute": round(cpm / 1000.0 * r, 4)} for v, n, r in rows]


def plan_table(cpm):
    rows = []
    for step in el()["ladder"]:
        m = step["chars"] / cpm
        rows.append({"plan": step["name"], "usd": step["usd"], "chars": step["chars"],
                     "minutes_at_cpm": round(m, 1),
                     "minutes_vendor_column": round(step["chars"] / 1000.0, 1),
                     "usd_per_minute": round(step["usd"] / m, 4) if m else None})
    return rows


def render(minutes, cpm, as_json):
    b = boundary(minutes, cpm)
    table = plan_table(cpm)
    eng = engines(cpm)
    c = b["chosen"]
    if as_json:
        print(json.dumps({"as_of": PRICES["as_of"], "boundary": b, "plans": table,
                          "engines": eng, "disclosure": DISCLOSURE}, indent=1))
        return
    print(f"Voice minutes needed: {minutes} finished minutes at {cpm} chars/min "
          f"= {b['chars']:,} characters/month")
    print(f"Prices read {PRICES['as_of']} from {el()['source']}\n")
    cost = c["usd"] + c.get("excess_usd", 0)
    if c["over"]:
        print(f"Cheapest cover: {c['plan'] or 'beyond the published ladder'} — ${c['usd']:.2f} base "
              f"({c['chars']:,} chars) + ${c['excess_usd']:,.2f} excess = ${cost:,.2f}/month")
        print(f"  {c['note']}")
    else:
        print(f"Cheapest cover: {c['plan']} — ${cost:,.2f}/month for {c['chars']:,} characters")
    print(f"At your volume that is ${b['usd_per_finished_minute']:.4f} per finished minute "
          f"(${b['usd_per_1000_chars']:.4f} per 1,000 characters); used to the brim the same plan is "
          f"${cost / (c['chars'] / cpm):.4f}/min.")
    if not c["over"]:
        print(f"Every month between {( (b.get('previous') or {}).get('minutes') )} and "
              f"{round(c['chars'] / cpm, 1)} finished minutes costs ${cost:,.2f}: the ladder is sold in "
              f"BLOCKS, so the first minute past a boundary buys the whole next block.")
    if b.get("previous"):
        p = b["previous"]
        print(f"\nThe boundary: {p['plan']} covers {p['minutes']} minutes at this rate for ${p['usd']:.2f}.")
        print(f"You are {b['over_previous_by_minutes']} minutes past it "
              f"({b['extra_chars_past_previous']:,} characters) and pay ${b['extra_usd']:.2f} more.")
        if b.get("usd_per_extra_minute"):
            print(f"Those marginal minutes cost ${b['usd_per_extra_minute']:.2f} each, against a "
                  f"plan average of ${b['usd_per_finished_minute']:.4f}.")
        print("Trimming the script or the runtime into the tier below is the only discount on this ladder.")
    pct = (1000.0 / cpm - 1.0) * 100.0
    print(f"\nThe vendor's own column divides characters by 1,000. At {cpm:g} chars/min a plan buys "
          f"{abs(pct):.1f}% {'fewer' if pct > 0 else 'more' if pct < 0 else ''} minutes than its column "
          f"claims.")
    print("\nCost of ONE finished minute, per engine:")
    for e in eng:
        print(f"  {e['vendor']:11} {e['engine']:28} ${e['usd_per_1000_chars']:.4f}/1k chars "
              f"= ${e['usd_per_finished_minute']:.4f}/min")
    print("\nPlans at this rate (minutes the allowance actually buys):")
    for r in table:
        print(f"  {r['plan']:9} ${r['usd']:>7.2f}  {r['chars']:>10,} chars  "
              f"{r['minutes_at_cpm']:>8.1f} min  ${r['usd_per_minute']:.4f}/min")
    print(f"\nVendor plan page (disclosure: {DISCLOSURE}): {el()['affiliate_link']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Monthly voice-minutes fit and cost per finished minute.")
    p.add_argument("--minutes", type=float, help="finished minutes per month you need")
    p.add_argument("--hours", type=float, help="same, in hours")
    p.add_argument("--episodes", type=float, help="episodes per month (multiplied by --minutes)")
    p.add_argument("--episode-minutes", type=float, default=None, help="minutes per episode")
    p.add_argument("--chars-per-minute", type=float, default=900.0,
                   help="characters of script per spoken minute (default 900; vendor column uses 1000)")
    p.add_argument("--engines", action="store_true", help="print cost per finished minute per engine")
    p.add_argument("--plans", action="store_true", help="print the plan ladder at this rate")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    if a.engines:
        for e in engines(a.chars_per_minute):
            print(f"{e['vendor']:11} {e['engine']:28} ${e['usd_per_1000_chars']:.4f}/1k chars "
                  f"= ${e['usd_per_finished_minute']:.4f}/min")
        print(f"\n{el()['affiliate_link']} ({DISCLOSURE})")
        return 0
    if a.plans:
        for r in plan_table(a.chars_per_minute):
            print(f"{r['plan']:9} ${r['usd']:>7.2f}  {r['chars']:>10,} chars  "
                  f"{r['minutes_at_cpm']:>8.1f} min  ({r['minutes_vendor_column']} min on the vendor column)")
        print(f"\n{el()['affiliate_link']} ({DISCLOSURE})")
        return 0

    minutes = a.minutes
    if a.episodes and minutes:
        minutes = a.episodes * minutes
    if a.episodes and a.episode_minutes:
        minutes = a.episodes * a.episode_minutes
    if a.hours:
        minutes = a.hours * 60
    if not minutes:
        p.error("give --minutes, --hours, or --episodes with a per-episode length")
    if minutes <= 0:
        p.error("--minutes must be positive")
    render(minutes, a.chars_per_minute, a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
