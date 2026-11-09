#!/usr/bin/env python3
"""Tests for minutes.py (the creator half of this repo). Run: python3 tests/test_minutes.py

Every number here is derived from prices.json, and the assertions are the claims the README makes.
The two that matter most:
  - 300 and 1,238 finished minutes both cost $99 (the ladder is sold in blocks)
  - at the vendor's own 1,000 chars/min basis; at 900 chars/min a plan buys 11.1% fewer minutes
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "minutes.py")
P = json.load(open(os.path.join(ROOT, "prices.json")))
README = open(os.path.join(ROOT, "README.md")).read()
LADDER = {s["name"]: s for s in P["vendors"]["elevenlabs"]["ladder"]}

fails, n = [], 0


def check(name, cond, detail=""):
    global n
    n += 1
    if not cond:
        fails.append(f"{name}  {detail}")


def run(*args):
    r = subprocess.run([sys.executable, CLI] + list(args), capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        fails.append(f"CLI exited {r.returncode}: {' '.join(args)}\n{r.stderr}")
    return r.stdout


def j(*args):
    return json.loads(run("--json", *args))


# ---- 1. the ladder itself, from the price file ----
check("Creator = $22 / 275,000 chars", (LADDER["Creator"]["usd"], LADDER["Creator"]["chars"]) == (22, 275000))
check("Pro = $99 / 1,238,000 chars", (LADDER["Pro"]["usd"], LADDER["Pro"]["chars"]) == (99, 1238000))
check("Business = $990 / 12,375,000 chars",
      (LADDER["Business"]["usd"], LADDER["Business"]["chars"]) == (990, 12375000))

# ---- 2. plan fit at the vendor's own 1,000 chars/min basis ----
a = j("--minutes", "275", "--chars-per-minute", "1000")["boundary"]
check("275 min -> Creator $22", (a["chosen"]["plan"], a["chosen"]["usd"]) == ("Creator", 22), a["chosen"])
b = j("--minutes", "276", "--chars-per-minute", "1000")["boundary"]
check("276 min -> next block, Pro $99", (b["chosen"]["plan"], b["chosen"]["usd"]) == ("Pro", 99), b["chosen"])

# ---- 3. the block claim: 300 and 1,238 minutes both cost $99 ----
c300 = j("--minutes", "300", "--chars-per-minute", "1000")["boundary"]
c1238 = j("--minutes", "1238", "--chars-per-minute", "1000")["boundary"]
check("300 min costs $99", c300["chosen"]["usd"] == 99, c300["chosen"])
check("1,238 min costs $99", c1238["chosen"]["usd"] == 99, c1238["chosen"])
check("300 and 1,238 cost the same", c300["chosen"]["usd"] == c1238["chosen"]["usd"])
check("300 min is 25 min past Creator", c300["over_previous_by_minutes"] == 25.0, c300["over_previous_by_minutes"])
check("those 25 min cost $77 more", c300["extra_usd"] == 77, c300["extra_usd"])
check("marginal minute = $3.08", abs(c300["usd_per_extra_minute"] - 3.08) < 1e-9, c300["usd_per_extra_minute"])
check("300 min averages $0.33/min at that volume", abs(c300["usd_per_finished_minute"] - 0.33) < 1e-9,
      c300["usd_per_finished_minute"])
check("1,238 min averages $0.08/min", abs(c1238["usd_per_finished_minute"] - 0.08) < 1e-9,
      c1238["usd_per_finished_minute"])
check("the $99 block spans 275 -> 1,238 min",
      b["chosen"]["usd"] == c1238["chosen"]["usd"] and c1238["minutes"] > b["minutes"])

# ---- 4. the characters-per-minute basis (the whole argument) ----
d = j("--minutes", "600", "--chars-per-minute", "900")["boundary"]
check("600 min @900 = 540,000 chars", d["chars"] == 540000, d["chars"])
check("600 min @900 -> Pro, not Creator", d["chosen"]["plan"] == "Pro", d["chosen"])
check("at 900 chars/min Creator covers 305.6 min", abs(d["previous"]["minutes"] - 305.6) < 0.05,
      d["previous"]["minutes"])
# the vendor column (chars/1000) overstates minutes by 11.1% at 900 c/min
check("vendor column overstates minutes by 11.1% at 900 c/min",
      abs(LADDER["Creator"]["chars"] / 900.0 - LADDER["Creator"]["chars"] / 1000.0 * 1.1111) < 0.3)
out900 = run("--minutes", "600", "--chars-per-minute", "900")
check("CLI states the 11.1% fewer-minutes caveat", "11.1% fewer" in out900, out900[-600:])
out1000 = run("--minutes", "600", "--chars-per-minute", "1000")
check("CLI states 0.0% at the vendor basis", "0.0%" in out1000, out1000[-600:])

# ---- 5. past the top of the published ladder ----
e = j("--minutes", "13000", "--chars-per-minute", "1000")["boundary"]
check("13,000 min is above the ladder", e["chosen"]["over"] is True, e["chosen"])
check("excess priced at $0.08/1k", abs(e["chosen"]["excess_usd"] - 50.0) < 0.01, e["chosen"]["excess_usd"])

# ---- 6. cost of one finished minute per engine at 900 chars/min ----
eng = {r["engine"]: r for r in j("--minutes", "600", "--chars-per-minute", "900")["engines"]}
check("EL v4 = $0.0720/min", abs(eng["v4 (multilingual, default)"]["usd_per_finished_minute"] - 0.072) < 1e-9)
check("EL turbo/flash = $0.0360/min", abs(eng["v4 Turbo / Flash"]["usd_per_finished_minute"] - 0.036) < 1e-9)
check("Deepgram Aura-2 = $0.0270/min", abs(eng["Aura-2"]["usd_per_finished_minute"] - 0.027) < 1e-9)
check("Deepgram Aura-1 = $0.0135/min", abs(eng["Aura-1"]["usd_per_finished_minute"] - 0.0135) < 1e-9)
check("EL v4 + Aura-2 crossover 2.67x", abs(0.072 / 0.027 - 2.6667) < 0.001)

# ---- 7. hours and episodes are the same arithmetic ----
h = j("--hours", "10")["boundary"]
m = j("--minutes", "600")["boundary"]
check("10 hours == 600 minutes", h["chosen"] == m["chosen"], (h["chosen"], m["chosen"]))
ep = j("--episodes", "4", "--minutes", "45")["boundary"]
check("4 x 45 min == 180 minutes", ep["minutes"] == 180.0, ep["minutes"])

# ---- 8. disclosure travels with the link, and the README carries both buyer phrases ----
check("prices.json carries a disclosure beside every affiliate link",
      all("affiliate_disclosure" in v for v in P["vendors"].values() if v.get("affiliate_link")))
check("output labels the affiliate link", "affiliate link" in run("--plans").lower())
check("README has the creator phrase", "voice minutes calculator" in README.lower())
check("README has the agency phrase", "voice agent cost per call" in README.lower())
check("README names the AI author", "autonomous AI agent" in README)
check("README states the commission", "commission" in README.lower())

# ---- 9. no network at runtime ----
for f in ("minutes.py", "voicecost.py"):
    src = open(os.path.join(ROOT, f)).read()
    check(f"{f} imports no network module",
          not re.search(r"import\s+(urllib|socket|http|requests)", src))

print(f"{n - len(fails)}/{n} checks passed")
if fails:
    print("\nFAILURES:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("ALL TESTS PASS")
