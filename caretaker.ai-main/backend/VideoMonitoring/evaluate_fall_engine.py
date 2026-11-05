"""
evaluate_fall_engine.py — Run the fall engine over the synthetic test bench.

    python evaluate_fall_engine.py                 # summary table
    python evaluate_fall_engine.py --verbose       # every run
    python evaluate_fall_engine.py --export-fixtures ../../frontend/tests/fixtures/fall_scenarios.json

Each scenario is rendered at several frame-rates, camera distances and noise
seeds. A run passes when the engine's events match the expectation:
    none            → no fall_confirmed event
    fall            → a fall_confirmed event with severity "high"
    check_in        → a fall_confirmed event (any severity) — gentle check-in
    fall+recovered  → fall_confirmed then recovered
    fall+long_lie   → fall_confirmed then long_lie
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

from fall_inference import FallInferenceEngine, EV_FALL, EV_RECOVERED, EV_LONG_LIE  # noqa: E402
from fall_scenarios import build_scenarios, render  # noqa: E402

FPS_SET = (10.0, 15.0, 30.0)
DIST_SET = (3.0, 4.5, 6.5)
SEEDS = (1, 2)


def run_one(scn, fps, dist, seed, sensitivity="medium"):
    eng = FallInferenceEngine(sensitivity=sensitivity, bed_zones=scn.bed_zones)
    events = []
    for t, xy, conf, size in render(scn, fps=fps, distance=dist, seed=seed):
        r = eng.update(t, xy, conf, frame_size=size)
        events.extend(r["events"])
    return events


def judge(scn, events):
    falls = [e for e in events if e["type"] == EV_FALL]
    rec = [e for e in events if e["type"] == EV_RECOVERED]
    ll = [e for e in events if e["type"] == EV_LONG_LIE]
    exp = scn.expect
    if exp == "none":
        ok = not falls
    elif exp == "fall":
        ok = len(falls) == 1 and falls[0]["severity"] == "high"
    elif exp == "check_in":
        ok = len(falls) == 1
    elif exp == "fall+recovered":
        ok = len(falls) == 1 and len(rec) == 1
    elif exp == "fall+long_lie":
        ok = len(falls) == 1 and len(ll) >= 1
    else:
        ok = False
    latency = None
    if falls and scn.impact_t is not None:
        latency = falls[0]["t"] - scn.impact_t
    return ok, falls, latency


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--sensitivity", default="medium")
    ap.add_argument("--export-fixtures", default=None,
                    help="write rendered sequences + Python results as JSON for the JS parity test")
    args = ap.parse_args()

    scns = build_scenarios()
    totals = defaultdict(lambda: [0, 0])
    lat = defaultdict(list)
    fixtures = []
    tp = fp = fn = tn = 0
    for scn in scns:
        for fps in FPS_SET:
            for dist in DIST_SET:
                for seed in SEEDS:
                    events = run_one(scn, fps, dist, seed, args.sensitivity)
                    ok, falls, latency = judge(scn, events)
                    totals[scn.name][0] += int(ok)
                    totals[scn.name][1] += 1
                    positive = scn.expect != "none"
                    if positive and falls: tp += 1
                    elif positive: fn += 1
                    elif falls: fp += 1
                    else: tn += 1
                    if latency is not None:
                        lat[scn.name].append(latency)
                    if args.verbose and not ok:
                        print(f"  FAIL {scn.name:30s} fps={fps:4.0f} dist={dist} seed={seed} events="
                              f"{[(e['type'], e.get('fall_type'), e.get('severity'), e['t']) for e in events if e['type'] != 'candidate_rejected']}")
                    if args.export_fixtures and fps == 15.0 and dist == 4.5 and seed == 1:
                        frames = []
                        for t, xy, conf, size in render(scn, fps=fps, distance=dist, seed=seed):
                            frames.append({"t": round(t, 4),
                                           "xy": [[round(a, 1), round(b, 1)] for a, b in xy] if xy else None,
                                           "conf": [round(c, 2) for c in conf] if conf else None,
                                           "size": list(size)})
                        # reference decisions computed on exactly the exported (rounded) frames
                        ref = FallInferenceEngine(sensitivity="medium", bed_zones=scn.bed_zones)
                        py_events = []
                        for f in frames:
                            py_events.extend(ref.update(f["t"], f["xy"], f["conf"], frame_size=tuple(f["size"]))["events"])
                        fixtures.append({"name": scn.name, "expect": scn.expect, "bed_zones": scn.bed_zones,
                                         "frames": frames,
                                         "python_events": [{"type": e["type"], "t": e["t"],
                                                            "fall_type": e.get("fall_type"),
                                                            "severity": e.get("severity")} for e in py_events]})

    print(f"\nFall engine — synthetic test bench (sensitivity={args.sensitivity})")
    print(f"{'scenario':32s} {'expect':16s} {'pass':>9s} {'latency (s)':>12s}")
    print("-" * 74)
    for scn in scns:
        ok, n = totals[scn.name]
        l = lat.get(scn.name)
        ls = f"{sum(l)/len(l):.2f}" if l else "-"
        print(f"{scn.name:32s} {scn.expect:16s} {ok:>4d}/{n:<4d} {ls:>12s}")
    all_ok = sum(v[0] for v in totals.values())
    all_n = sum(v[1] for v in totals.values())
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    print("-" * 74)
    print(f"runs passing expectation: {all_ok}/{all_n}   detection precision={prec:.3f} recall={rec:.3f} "
          f"(TP={tp} FP={fp} FN={fn} TN={tn})")

    if args.export_fixtures:
        os.makedirs(os.path.dirname(os.path.abspath(args.export_fixtures)), exist_ok=True)
        with open(args.export_fixtures, "w") as fh:
            json.dump(fixtures, fh, separators=(",", ":"))
        print(f"wrote {len(fixtures)} fixtures → {args.export_fixtures}")
    return 0 if all_ok == all_n else 1


if __name__ == "__main__":
    sys.exit(main())
