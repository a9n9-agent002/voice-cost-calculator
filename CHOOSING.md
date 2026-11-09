# Before you quote a voice agent: a five-minute checklist

For agencies and freelancers pricing a client's voice agent. Every number below was read from a vendor
pricing page on 2026-11-08; `python3 voicecost.py` reproduces the arithmetic.

**1. Get four numbers from the client, not three.** Call volume per month, finished minutes per call,
roughly how many words the agent will speak per minute, and how many LLM turns per call. Missing any one
of them changes the answer by more than the vendor choice does — characters per spoken minute alone
swings 600–1,000, which is a 67% move on the whole bill.

**2. Price the speech line first, and price it per character.** In the cheapest stack measured here, the
TTS line is 77% of a call and the LLM is 0.7%. Anyone who quotes from token prices is off by ~135x.
Ask for the script length in characters, not "minutes of audio".

**3. Decide managed vs assembled on labour, not on price alone.** Managed stacks came out 2.1–2.3x the
assembled one ($0.2250–$0.2400 vs $0.1049 per 3-minute call). If you can operate three services, the
assembled stack halves the bill; if you cannot, the multiplier is your ops cost and belongs in the quote
as a line, not buried in margin.

**4. Check whether the ladder covers the month before you promise a plan price.** 10,000 calls at 3
minutes and 900 characters per minute is 27,000,000 characters/month. ElevenLabs' top self-serve plan is
12,375,000 characters for $990/month; above it the published ladder ends. A proposal that quotes "$990
covers it" is wrong by about $1,170/month at that volume.

**5. Do not read a vendor's agent-minute price as a speech-recognition price.** Deepgram's $0.075 headline
is its Voice Agent (STT + managed LLM + TTS); STT alone is $0.0043–$0.0092/minute. ElevenLabs prints
$0.08 twice on one page for two different billing bases (per agent minute and per 1,000 characters of
v4 speech). Both mistakes inflate or deflate a quote by several times.

**6. Know where the two ElevenLabs prices meet.** Its managed agent minute equals its TTS bought alone at
about 901 characters per spoken minute. Below that the TTS-only build is cheaper; above it the managed
minute is, because the managed price does not move with script length. Choose deliberately, per client.

**7. Add telephony as its own line, with your carrier's number.** The tool's $0.0085/minute is a
placeholder. Inbound, outbound, number rental and per-minute termination are four different charges.

**8. Write down the characters-per-minute and the model id in the proposal.** Both are assumptions that
will be argued about when the invoice arrives, and both can be verified against the pages named in
`prices.json`.

**9. Re-check prices on the day you send the quote.** Every number in this repository is one dated
snapshot. It is not a monitor, and vendor promos (ElevenLabs Starter $1 / Creator $11 in the first month)
are not prices.

**10. Quote a range, not a point.** Two calls to the same vendor page with a different assumption give a
range wider than the difference between two vendors. A range with the assumptions printed is the version
a client can sign.

## What this does not cover

Audio quality, latency, concurrency limits, per-turn latency budget, and whether the model holds a
conversation. A cheaper voice that sounds wrong costs the client more than it saves.
