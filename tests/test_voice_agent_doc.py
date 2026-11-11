#!/usr/bin/env python3
"""Checks that docs/voice-agent-cost-per-minute.md cannot drift from its data file.

    python3 tests/test_voice_agent_doc.py             # verify
    python3 tests/test_voice_agent_doc.py --selftest  # mutations that must be caught

Every figure on the page is recomputed here from docs/voice-agent-cost-per-minute.json. The doc's central
claim is that a per-minute voice-agent price does not include the LLM, and that the LLM is a few percent of
the call while telephony is three times as large; those two claims are recomputed, not quoted.
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "voice-agent-cost-per-minute.md")
DATA = os.path.join(ROOT, "docs", "voice-agent-cost-per-minute.json")


def money(v, places=5):
    return ("%%.%df" % places) % v


def checks(data, doc):
    bad = []
    call, tok, pr = data["call"], data["tokens"], data["prices_per_mtok"]
    lines, tot = data["lines_per_call"], data["totals_per_call"]
    vendor = data["vendor_rates"]

    # --- call shape -------------------------------------------------------
    secs = call["speech_seconds"] + call["turns"] * call["pause_seconds_per_turn"]
    if abs(secs - call["call_seconds"]) > 0.01:
        bad.append("call_seconds %s != speech + pauses = %.2f" % (call["call_seconds"], secs))
    mins = secs / 60.0
    if abs(mins - call["call_minutes"]) > 0.002:
        bad.append("call_minutes %s != %.4f" % (call["call_minutes"], mins))
    spoken_min = call["speech_seconds"] / 60.0
    cpm = call["chars_spoken"] / spoken_min
    if abs(cpm - call["chars_per_spoken_minute"]) > 0.2:
        bad.append("chars_per_spoken_minute %s != %.1f" % (call["chars_per_spoken_minute"], cpm))
    if abs(tok["input"] + tok["output"] - 4569) > 0:
        bad.append("token totals changed: %s + %s" % (tok["input"], tok["output"]))
    if abs(100.0 * tok["cacheable_prefix"] / tok["input"] - tok["cacheable_share_pct"]) > 0.1:
        bad.append("cacheable_share_pct is not cacheable_prefix / input")

    # --- the LLM line, both prices ---------------------------------------
    nov = pr["novita_deepseek_v4_1_flash"]
    pas = pr["elevenlabs_pass_through_row"]
    cache, new, out = tok["cacheable_prefix"], tok["new"], tok["output"]
    if cache + new != tok["input"]:
        bad.append("cacheable_prefix + new != input")
    llm_list = (cache * nov["cache_read"] + new * nov["input"] + out * nov["output"]) / 1e6
    llm_pass = (cache * pas["cache_read"] + new * pas["input"] + out * pas["output"]) / 1e6
    for label, want, got in (("llm list", data["llm_per_call"]["novita_usd"], llm_list),
                             ("llm pass", data["llm_per_call"]["elevenlabs_pass_usd"], llm_pass)):
        if abs(want - got) > 2e-6:
            bad.append("%s %s != recomputed %.7f" % (label, want, got))
    ratio = llm_pass / llm_list
    if abs(ratio - data["llm_per_call"]["ratio"]) > 0.02:
        bad.append("ratio %s != %.2f" % (data["llm_per_call"]["ratio"], ratio))
    out_share = 100.0 * out * pas["output"] / 1e6 / llm_pass
    if abs(out_share - data["llm_per_call"]["output_share_of_pass_bill_pct"]) > 0.15:
        bad.append("output_share_of_pass_bill_pct %s != %.1f" % (
            data["llm_per_call"]["output_share_of_pass_bill_pct"], out_share))

    # --- lines and totals -------------------------------------------------
    platform = mins * vendor["elevenlabs_platform_usd_per_minute"]
    telephony = mins * vendor["telephony_us_assumed_usd_per_minute"]
    if abs(platform - lines["platform_usd"]) > 5e-4:
        bad.append("platform_usd %s != %.5f" % (lines["platform_usd"], platform))
    if abs(telephony - lines["telephony_usd"]) > 5e-4:
        bad.append("telephony_usd %s != %.5f" % (lines["telephony_usd"], telephony))
    managed = platform + telephony + llm_pass
    if abs(managed - tot["managed_elevenlabs_usd"]) > 5e-4:
        bad.append("managed total %s != %.5f" % (tot["managed_elevenlabs_usd"], managed))
    if abs(100.0 * llm_pass / managed - tot["llm_share_managed_pct"]) > 0.05:
        bad.append("llm_share_managed_pct disagrees with the lines")
    allin = managed / mins
    dg = mins * vendor["deepgram_voice_agent_standard_usd_per_minute"] + telephony
    assembled = (lines["stt_usd"] + lines["tts_usd"] + lines["llm_novita_usd"] + lines["telephony_usd"])
    if abs(assembled - tot["assembled_novita_usd"]) > 5e-4:
        bad.append("assembled total %s != %.5f" % (tot["assembled_novita_usd"], assembled))
    if abs(managed / assembled - tot["managed_over_assembled"]) > 0.02:
        bad.append("managed_over_assembled disagrees with the totals")

    # --- the two "if everything stayed the same" figures the page prints ---
    zero_llm_min = (managed - llm_pass) / mins
    if abs(zero_llm_min - 0.0885) > 5e-5:
        bad.append("zero-LLM minute is %.5f, page says $0.0885" % zero_llm_min)
    if abs(1000.0 * allin - 91.32) > 0.02:
        bad.append("per-1,000-minutes figure is %.2f, page says $91.32" % (1000.0 * allin))
    if abs(1000.0 * managed - 197.71) > 0.02:
        bad.append("per-1,000-calls figure is %.2f, page says $197.71" % (1000.0 * managed))

    # --- growth table -----------------------------------------------------
    rows = data["growth"]
    if len(rows) != 4:
        bad.append("growth table must have four rows")
    for g in rows:
        total = g["minutes"] * vendor["elevenlabs_platform_usd_per_minute"] + \
            g["minutes"] * vendor["telephony_us_assumed_usd_per_minute"] + g["llm_pass_usd"]
        if abs(total - g["managed_total_usd"]) > 5e-4:
            bad.append("growth x%d total %s != %.5f" % (g["exchanges"], g["managed_total_usd"], total))
        share = 100.0 * g["llm_pass_usd"] / g["managed_total_usd"]
        if abs(share - g["llm_share_pct"]) > 0.05:
            bad.append("growth x%d share %s != %.2f" % (g["exchanges"], g["llm_share_pct"], share))
        per_min = g["llm_pass_usd"] / g["minutes"]
        if abs(per_min - g["llm_pass_per_minute"]) > 1e-5:
            bad.append("growth x%d llm per minute drifted" % g["exchanges"])
    if abs(rows[3]["input_tokens"] / rows[0]["input_tokens"] - 38.5) > 0.2:
        bad.append("input-token growth is no longer 38x")
    if abs(rows[3]["llm_pass_per_minute"] / rows[0]["llm_pass_per_minute"] - 1.71) > 0.02:
        bad.append("LLM per-minute growth is no longer 1.71x")

    # --- crossover: input alone priced to match the platform minute -------
    solve = (vendor["elevenlabs_platform_usd_per_minute"]
             - tok["output_tokens_per_minute"] * pas["output"] / 1e6) * 1e6 / tok["input_tokens_per_minute"]
    if abs(solve - 39.66) > 0.05:
        bad.append("crossover input price solved %.2f, page says $39.66" % solve)
    if abs(solve / nov["input"] - 132.0) > 1.0:
        bad.append("crossover multiple %.1fx, page says 132x" % (solve / nov["input"]))
    out_only = tok["output_tokens_per_minute"] * pas["output"] / 1e6
    if abs(out_only - 0.00226) > 5e-5:
        bad.append("output tokens alone are %.5f of the minute, page says $0.00226" % out_only)

    # --- the page must actually print what was recomputed ----------------
    must = [
        "**$0.17317**", "**$0.01840**", "**$0.00614**", "**$0.19771**", "$0.00048",
        "87.59%", "9.31%", "3.10%", "0.24%", "14.2%", "**12.75×**", "79.7%",
        "**$0.00061**", "$0.000048", "$0.0885", "1,063.8", "2,019", "4,243", "4,023",
        "94.8%", "1,960 input", "151 output", "2.165", "9.24",
        "3.07%", "5.14%", "**38×**", "**1.71×**", "2.0%", "**$39.66", "**132×**", "$0.00226",
        "$0.18078", "**$0.09612**", "$0.10178", "**2.06×**", "**$197.71**", "$91.32",
    ]
    for token in must:
        if token not in doc:
            bad.append("page no longer prints %r" % token)
    for banned in ("$0.0886", "12.4%", "1,064 characters", "$0.075 a minute all-in"):
        if banned in doc:
            bad.append("page prints a retired figure %r" % banned)
    return bad


def run():
    data = json.load(open(DATA))
    doc = open(DOC).read()
    bad = checks(data, doc)
    if bad:
        print("FAIL (%d problems)" % len(bad))
        for b in bad:
            print("  -", b)
        return 1
    print("OK: voice-agent cost page agrees with its data file")
    return 0


def selftest():
    data = json.load(open(DATA))
    doc = open(DOC).read()
    mutations = []
    d = copy.deepcopy(data); d["call"]["call_minutes"] = 2.5
    mutations.append(("minutes", d, doc))
    d = copy.deepcopy(data); d["llm_per_call"]["ratio"] = 10.0
    mutations.append(("ratio", d, doc))
    d = copy.deepcopy(data); d["vendor_rates"]["telephony_us_assumed_usd_per_minute"] = 0.014
    mutations.append(("telephony", d, doc))
    d = copy.deepcopy(data); d["growth"][3]["llm_share_pct"] = 9.9
    mutations.append(("growth-share", d, doc))
    mutations.append(("doc-number", data, doc.replace("$0.17317", "$0.17318")))
    mutations.append(("doc-claim", data, doc.replace("3.10%", "3.20%")))
    caught = 0
    for name, md, mdoc in mutations:
        if checks(md, mdoc):
            print("  caught:", name)
            caught += 1
        else:
            print("  MISSED:", name)
    print("%d/%d mutations caught" % (caught, len(mutations)))
    return 0 if caught == len(mutations) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(run())
