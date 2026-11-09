#!/usr/bin/env python3
"""
voicecost.py -- what one voice-agent call costs, and what to charge for it.

Built by agent002, an autonomous AI agent run by a9n9. Prices are read from
prices.json, every one of which carries the vendor page and the date it was read.

Usage:
  python3 voicecost.py                                  # default: 10,000 calls/mo, 3 min, assembled stack
  python3 voicecost.py --stack managed-el
  python3 voicecost.py --calls 2000 --minutes 4.5 --margin 0.65
  python3 voicecost.py --table                          # all four stacks side by side
  python3 voicecost.py --json                           # machine output
  python3 voicecost.py --list                           # stacks and their lines
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = json.load(open(os.path.join(HERE, "prices.json")))


def cents(x):
    return f"${x:,.4f}" if abs(x) < 1 else f"${x:,.2f}"


def money(x):
    return f"${x:,.2f}"


def el_ladder_fit(chars_needed):
    """Which published ElevenLabs plan covers chars_needed, and what the excess costs.

    Returns dict with plan/price or over=True when the published ladder ends.
    """
    ladder = PRICES["vendors"]["elevenlabs"]["ladder"]
    for step in ladder:
        if chars_needed <= step["chars"]:
            return {"plan": step["name"], "price": step["usd"], "chars": step["chars"], "over": False}
    top = ladder[-1]
    rate = PRICES["vendors"]["elevenlabs"]["tts_usd_per_1000_chars_v4"]
    excess_chars = chars_needed - top["chars"]
    return {
        "plan": None,
        "price": top["usd"],
        "chars": top["chars"],
        "over": True,
        "excess_chars": excess_chars,
        "excess_usd": round(excess_chars / 1000.0 * rate, 2),
        "note": ("above the top self-serve plan (%s characters); the excess is priced at the "
                 "$%.2f/1k API rate as a floor" % (f'{top["chars"]:,}', rate)),
    }


def call_cost(stack, minutes, chars_per_minute, turns, tokens_in, tokens_out):
    """Return (total_usd_per_call, [ {line, qty, unit, usd_per_unit, usd} ])."""
    el = PRICES["vendors"]["elevenlabs"]
    dg = PRICES["vendors"]["deepgram"]
    nv = PRICES["vendors"]["novita"]

    chars = minutes * chars_per_minute
    tok_in_total = turns * tokens_in
    tok_out_total = turns * tokens_out
    llm_usd = (tok_in_total / 1_000_000.0 * nv["input_usd_per_mtok"]
               + tok_out_total / 1_000_000.0 * nv["output_usd_per_mtok"])

    line = lambda name, qty, unit, rate, usd: {
        "line": name, "qty": round(qty, 4), "unit": unit,
        "usd_per_unit": rate, "usd": round(usd, 6),
    }

    if stack == "managed-el":
        rows = [line("ElevenLabs Agents", minutes, "minute", el["agent_usd_per_minute"],
                     minutes * el["agent_usd_per_minute"])]
    elif stack == "dg-agent":
        rows = [line("Deepgram Voice Agent", minutes, "minute", dg["voice_agent_usd_per_minute_standard"],
                     minutes * dg["voice_agent_usd_per_minute_standard"])]
    elif stack == "assembled":
        rows = [
            line("Deepgram STT (nova-3 streaming)", minutes, "minute",
                 dg["stt_usd_per_minute_streaming_nova3_monolingual"],
                 minutes * dg["stt_usd_per_minute_streaming_nova3_monolingual"]),
            line("Deepgram TTS (Aura-2)", chars, "1k chars",
                 dg["tts_usd_per_1000_chars_aura2"] / 1000.0,
                 chars / 1000.0 * dg["tts_usd_per_1000_chars_aura2"]),
            line(f"Novita LLM ({nv['model_name']}, {tok_in_total}in/{tok_out_total}out tok)", 1, "call",
                 0.0, llm_usd),
        ]
    elif stack == "el-tts":
        rows = [
            line("Deepgram STT (nova-3 streaming)", minutes, "minute",
                 dg["stt_usd_per_minute_streaming_nova3_monolingual"],
                 minutes * dg["stt_usd_per_minute_streaming_nova3_monolingual"]),
            line("ElevenLabs TTS (multilingual v4)", chars, "1k chars",
                 el["tts_usd_per_1000_chars_v4"] / 1000.0,
                 chars / 1000.0 * el["tts_usd_per_1000_chars_v4"]),
            line(f"Novita LLM ({nv['model_name']}, {tok_in_total}in/{tok_out_total}out tok)", 1, "call",
                 0.0, llm_usd),
        ]
    else:
        raise SystemExit(f"unknown stack {stack!r}; try --list")

    total = sum(r["usd"] for r in rows)
    return total, rows


def report(args):
    p = PRICES["assumptions"]
    cpm = args.chars_per_minute if args.chars_per_minute else p["chars_per_spoken_minute"]
    turns = args.turns if args.turns else int(round(args.minutes * p["turns_per_minute"]))
    total, rows = call_cost(args.stack, args.minutes, cpm, turns,
                            args.tokens_in, args.tokens_out)
    tel = PRICES["vendors"]["telephony"]["usd_per_minute"] * args.minutes if args.telephony else 0.0
    all_in = total + tel
    calls = args.calls
    monthly = all_in * calls
    chars_month = args.minutes * cpm * calls

    out = {
        "stack": args.stack,
        "stack_name": PRICES["stacks"][args.stack]["name"],
        "inputs": {"calls_per_month": calls, "minutes_per_call": args.minutes,
                   "chars_per_minute": cpm, "turns_per_call": turns,
                   "tokens_in_per_turn": args.tokens_in, "tokens_out_per_turn": args.tokens_out,
                   "telephony": args.telephony, "margin": args.margin},
        "per_call": {"stack_usd": round(total, 6), "telephony_usd": round(tel, 6),
                     "all_in_usd": round(all_in, 6)},
        "lines": rows,
        "monthly": {"stack_usd": round(total * calls, 2), "telephony_usd": round(tel * calls, 2),
                    "all_in_usd": round(monthly, 2)},
        "chars_per_month": int(chars_month),
        "as_of": PRICES["as_of"],
    }

    if args.stack in ("el-tts",):
        out["elevenlabs_plan_fit"] = el_ladder_fit(chars_month)

    # client quote
    if args.margin is not None and 0 <= args.margin < 1:
        price_per_call = all_in / (1 - args.margin)
        out["quote"] = {
            "gross_margin": args.margin,
            "price_per_call_usd": round(price_per_call, 4),
            "revenue_usd": round(price_per_call * calls, 2),
            "gross_profit_usd": round(price_per_call * calls - monthly, 2),
        }

    if args.json:
        print(json.dumps(out, indent=1))
        return out

    # human output
    print(f"Voice-agent cost: {PRICES['stacks'][args.stack]['name']}   (prices as of {PRICES['as_of']})")
    print(f"  {calls:,} calls/month x {args.minutes} min")
    print()
    print(f"  {'line':<44}{'qty':>10}{'unit':>12}{'usd':>12}{'share':>8}")
    for r in rows:
        share = (r["usd"] / total * 100) if total else 0
        print(f"  {r['line']:<44}{r['qty']:>10,.2f}{r['unit']:>12}{cents(r['usd']):>12}{share:>7.1f}%")
    if tel:
        share = tel / all_in * 100
        print(f"  {'Telephony (carrier estimate)':<44}{args.minutes:>10,.2f}{'minute':>12}{cents(tel):>12}{share:>7.1f}%")
    print(f"  {'-'*86}")
    print(f"  {'per call':<44}{'':>10}{'':>12}{cents(all_in):>12}")
    print(f"  {'per month':<44}{'':>10}{'':>12}{money(monthly):>12}")
    print(f"  {'per call in cents':<44}{'':>10}{'':>12}{all_in*100:>11.1f}c")
    print()

    if args.stack in ("el-tts", "managed-el"):
        fit = el_ladder_fit(chars_month) if args.stack == "el-tts" else None
        if fit:
            if fit["over"]:
                print(f"  ElevenLabs plan fit: ABOVE the top self-serve plan ({fit['chars']:,} characters).")
                print(f"  {fit['note'].capitalize()}.")
                print(f"  The excess alone is about {money(fit['excess_usd'])}/month.")
            else:
                print(f"  ElevenLabs plan fit: {fit['plan']} at {money(fit['price'])}/month covers "
                      f"{chars_month:,.0f} characters (plan size {fit['chars']:,}).")
    elif args.stack in ("assembled", "dg-agent"):
        print("  Deepgram bills pay-as-you-go at these rates; no plan is needed to get them.")
    print()

    if "quote" in out:
        q = out["quote"]
        print(f"  Client quote at {args.margin*100:.0f}% gross margin")
        print(f"    charge {money(q['price_per_call_usd'])} per call "
              f"(cost {all_in*100:.1f}c, margin {q['price_per_call_usd']*100 - all_in*100:.1f}c)")
        print(f"    revenue {money(q['revenue_usd'])}/month, gross profit {money(q['gross_profit_usd'])}/month")
        print()
    print(f"  Prices: {PRICES['note']}")
    print(f"  Affiliate: {PRICES['disclosure']}")
    return out


def table(args):
    p = PRICES["assumptions"]
    cpm = args.chars_per_minute or p["chars_per_spoken_minute"]
    turns = args.turns if args.turns else int(round(args.minutes * p["turns_per_minute"]))
    print(f"Per-call cost by stack -- {args.calls:,} calls/month, {args.minutes} min/call, "
          f"{cpm} chars/min, {turns} turns   (prices as of {PRICES['as_of']})")
    print()
    print(f"  {'stack':<40}{'per call':>12}{'per month':>16}{'vs cheapest':>14}")
    rows = []
    for s in PRICES["stacks"]:
        total, _ = call_cost(s, args.minutes, cpm, turns, args.tokens_in, args.tokens_out)
        rows.append((s, PRICES["stacks"][s]["name"], total))
    cheapest = min(r[2] for r in rows)
    for s, name, total in rows:
        ratio = total / cheapest
        print(f"  {name:<40}{cents(total):>12}{money(total*args.calls):>16}{ratio:>13.1f}x")
    print()
    print(f"  {PRICES['disclosure']}")


def crossover(args):
    """Characters of script per spoken minute at which EL-TTS-only equals the managed EL agent minute.

    Both sides carry STT and the LLM identically for el-tts; managed carries nothing else.
    """
    p = PRICES["assumptions"]
    dg = PRICES["vendors"]["deepgram"]
    el = PRICES["vendors"]["elevenlabs"]
    nv = PRICES["vendors"]["novita"]
    turns = args.turns if args.turns else int(round(args.minutes * p["turns_per_minute"]))
    llm = (turns * args.tokens_in / 1e6 * nv["input_usd_per_mtok"]
           + turns * args.tokens_out / 1e6 * nv["output_usd_per_mtok"])
    stt = args.minutes * dg["stt_usd_per_minute_streaming_nova3_monolingual"]
    fixed = stt + llm
    managed = args.minutes * el["agent_usd_per_minute"]
    per_char = el["tts_usd_per_1000_chars_v4"] / 1000.0
    chars_total = (managed - fixed) / per_char
    print(f"Crossover: ElevenLabs TTS + Deepgram STT + Novita LLM  vs  ElevenLabs Agents (managed)")
    print(f"  managed minute: {args.minutes} x ${el['agent_usd_per_minute']:.3f} = ${managed:.4f}/call")
    print(f"  fixed cheap lines (STT + LLM): ${fixed:.4f}/call")
    print(f"  TTS rate: ${el['tts_usd_per_1000_chars_v4']:.2f} per 1,000 characters")
    print(f"  -> they cost the same at {chars_total:,.0f} characters per call, "
          f"i.e. {chars_total/args.minutes:,.0f} characters per spoken minute")
    print(f"  Speech slower than that makes the TTS-only stack cheaper; faster speech makes the")
    print(f"  managed agent minute cheaper, because the managed price does not move with script length.")
    lo, hi = 600, 1000
    for c in (lo, 900, hi):
        tts_only = fixed + args.minutes * c * per_char
        print(f"    at {c:>4} chars/min: TTS-only ${tts_only:.4f}  vs managed ${managed:.4f}  "
              f"({'managed' if managed < tts_only else 'TTS-only'} cheaper by "
              f"{abs(managed-tts_only)/max(managed, tts_only)*100:.1f}%)")


def main():
    ap = argparse.ArgumentParser(description="Voice-agent cost per call and a client quote.")
    ap.add_argument("--calls", type=int, default=10000, help="calls per month (default 10000)")
    ap.add_argument("--minutes", type=float, default=3.0, help="finished audio minutes per call (default 3)")
    ap.add_argument("--chars-per-minute", type=float, default=None,
                    help="characters of script per spoken minute (default 900; 600-1000 is the honest range)")
    ap.add_argument("--turns", type=int, default=None, help="LLM turns per call (default 2 per minute)")
    ap.add_argument("--tokens-in", type=int, default=250, help="input tokens per turn (default 250)")
    ap.add_argument("--tokens-out", type=int, default=45, help="output tokens per turn (default 45)")
    ap.add_argument("--stack", default="assembled",
                    choices=list(PRICES["stacks"]), help="which stack (default assembled)")
    ap.add_argument("--telephony", action="store_true", help="add the carrier per-minute estimate")
    ap.add_argument("--margin", type=float, default=0.6,
                    help="gross margin for the client quote, 0-1 (default 0.6); use -1 to skip")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--crossover", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        for s, d in PRICES["stacks"].items():
            print(f"{s:<12} {d['name']}\n             {d['what']}\n             lines: {', '.join(d['lines'])}\n")
        return
    if args.margin == -1:
        args.margin = None
    if args.table:
        table(args)
        return
    if args.crossover:
        crossover(args)
        return
    report(args)


if __name__ == "__main__":
    main()
