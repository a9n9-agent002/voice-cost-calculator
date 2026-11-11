#!/usr/bin/env python3
"""piper_bench — what a CPU-only text-to-speech engine costs per audio minute.

Measures Piper's speed relative to real time for three voice quality tiers, the peak memory of the
synthesis process, and derives the cost of 1,000 audio minutes at the hourly rate of a rented server.

    python3 tools/piper_bench/bench.py                      # 3 runs per tier, writes a local JSON
    python3 tools/piper_bench/bench.py --out my-run.json
    python3 tools/piper_bench/bench.py --repeats 5

Prerequisites (the script checks and tells you):
    python3 -m venv .venv
    .venv/bin/pip install piper-tts==1.8.0
    .venv/bin/python -m piper.download_voices en_US-lessac-medium   # likewise -low, -high

Nothing here is estimated. A ratio you did not measure on your own core is somebody else's core.
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import wave

DROPLET_USD_PER_MONTH = 6.00
HOURS_PER_MONTH = 730.0
USD_PER_CPU_HOUR = DROPLET_USD_PER_MONTH / HOURS_PER_MONTH
ELL_USD_PER_1K_CHARS = 0.08          # the vendor's flat per-character rate, stated for comparison
TIERS = [("en_US-lessac-low", "low"), ("en_US-lessac-medium", "medium"), ("en_US-lessac-high", "high")]

TEXT = (
    "Self hosting a text to speech engine is a capacity decision before it is a quality decision. "
    "A neural voice model runs on the processor you already rent, and the only number that matters "
    "is how many seconds of audio the machine produces for every second of processor time it spends. "
    "Once you know that ratio, the monthly bill for a thousand minutes of speech is arithmetic: "
    "an hour of audio needs sixty divided by the ratio, and a server costs a fixed amount per hour. "
    "This paragraph is the measurement input. It is read aloud in full, from the first word to the "
    "last one, so that the audio duration and the character count describe the same piece of text. "
    "A lower quality tier runs faster on the same core and uses less memory, and a higher tier sounds "
    "better and costs more processor time, which is the whole trade. Measure it on your own hardware "
    "before you pick a tier, because the ratio depends on the core you rent and not on the voice alone."
)

RSS_WRAPPER = r'''
import resource, subprocess, sys
model, wav = sys.argv[1], sys.argv[2]
p = subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", wav],
                   input=sys.stdin.buffer.read(), capture_output=True)
if p.returncode != 0:
    sys.exit(p.stderr.decode()[-400:])
print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
'''


def cpu_model():
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def audio_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="measurements-local.json")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter that has piper-tts installed (default: this one)")
    args = ap.parse_args()

    if not shutil.which(args.python) and not os.path.exists(args.python):
        sys.exit("interpreter not found: " + args.python)
    probe = subprocess.run([args.python, "-m", "piper", "--help"], capture_output=True)
    if probe.returncode not in (0, 2):          # piper --help exits 0; argparse errors exit 2
        sys.exit("piper is not installed for %s — see the module docstring" % args.python)

    here = os.path.dirname(os.path.abspath(__file__))
    audio_dir = os.path.join(here, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    wrapper = os.path.join(audio_dir, "_rss_wrapper.py")
    open(wrapper, "w").write(RSS_WRAPPER)

    chars = len(TEXT)
    rows, cpm_samples = [], []
    for voice, quality in TIERS:
        model = os.path.join(here, voice + ".onnx")
        if not os.path.exists(model):
            sys.exit("missing voice model %s — run: %s -m piper.download_voices %s"
                     % (model, args.python, voice))
        runs = []
        for i in range(args.repeats):
            wav = os.path.join(audio_dir, "%s_%d.wav" % (voice, i))
            t0 = time.perf_counter()
            p = subprocess.run([args.python, "-m", "piper", "-m", model, "-f", wav],
                               input=TEXT.encode(), capture_output=True)
            wall = time.perf_counter() - t0
            if p.returncode != 0:
                sys.exit("piper failed: " + p.stderr.decode()[-400:])
            dur = audio_seconds(wav)
            runs.append({"wall_s": round(wall, 3), "audio_s": round(dur, 3),
                         "speedup": round(dur / wall, 3)})
            cpm_samples.append(chars / (dur / 60.0))

        r = subprocess.run([args.python, wrapper, model, os.path.join(audio_dir, voice + "_rss.wav")],
                           input=TEXT.encode(), capture_output=True)
        rss_mb = round(int(r.stdout.decode().strip()) / 1024.0, 1) if r.returncode == 0 else None

        speedups = [x["speedup"] for x in runs]
        med = statistics.median(speedups)
        audio_min_per_h = med * 60.0
        cpu_h = 1000.0 / audio_min_per_h
        rows.append({
            "voice": voice, "quality": quality, "runs": runs,
            "speedup_median": round(med, 3),
            "speedup_min": round(min(speedups), 3),
            "speedup_max": round(max(speedups), 3),
            "audio_s_median": round(statistics.median([x["audio_s"] for x in runs]), 3),
            "audio_minutes_per_cpu_hour": round(audio_min_per_h, 1),
            "cpu_hours_per_1000_audio_minutes": round(cpu_h, 3),
            "usd_per_1000_audio_minutes": round(cpu_h * USD_PER_CPU_HOUR, 4),
            "usd_per_audio_minute": round(cpu_h * USD_PER_CPU_HOUR / 1000.0, 6),
            "audio_hours_per_core_month": round(med * HOURS_PER_MONTH, 0),
            "peak_rss_mb": rss_mb,
        })
        print("%-22s %7.3fx  %6.1f audio-min/CPU-h  $%.4f per 1000 min  %s MB"
              % (voice, med, audio_min_per_h, rows[-1]["usd_per_1000_audio_minutes"], rss_mb))

    cpm = statistics.median(cpm_samples)
    hosted_per_min = ELL_USD_PER_1K_CHARS * cpm / 1000.0
    data = {
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
        "what": "cost of 1,000 minutes of synthesized speech on a CPU-only server, measured",
        "engine": "piper-tts (onnxruntime CPU build), one process at a time, no concurrency",
        "host_cpu": cpu_model(), "host_cores": os.cpu_count(),
        "text": {"chars": chars, "note": "the same %d-character paragraph in every run" % chars},
        "pricing_basis": {"droplet_usd_per_month": DROPLET_USD_PER_MONTH,
                          "hours_per_month": HOURS_PER_MONTH,
                          "usd_per_cpu_hour": round(USD_PER_CPU_HOUR, 6),
                          "note": "marginal cost of CPU time on a server already rented"},
        "tiers": rows,
        "chars_per_audio_minute": round(cpm, 1),
        "hosted_reference": {"usd_per_1000_chars": ELL_USD_PER_1K_CHARS,
                             "usd_per_audio_minute": round(hosted_per_min, 5),
                             "usd_per_1000_audio_minutes": round(hosted_per_min * 1000.0, 2),
                             "note": "rate x the measured %.1f characters per audio minute" % cpm},
        "ratio_medium_vs_hosted": round(hosted_per_min * 1000.0 / rows[1]["usd_per_1000_audio_minutes"], 1),
        "ratio_high_vs_hosted": round(hosted_per_min * 1000.0 / rows[2]["usd_per_1000_audio_minutes"], 1),
    }
    json.dump(data, open(args.out, "w"), indent=2)
    print("\nchars per audio minute %.1f -> hosted $%.2f per 1000 minutes"
          % (cpm, hosted_per_min * 1000.0))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
