"""
evaluate_on_videos.py — event-level evaluation of the full pipeline on REAL videos.

This is the number to present, not the synthetic bench and not frame-level
classifier accuracy. It answers: "of the falls that happened, how many did we
alert on, how fast, and how many false alarms did we raise?"

Labels CSV (one row per video):
    video,fall_start_s,notes
    ur_fall_01.mp4,3.2,forward fall
    adl_sit_04.mp4,,sitting down (no fall)

Usage (from backend/VideoMonitoring, needs ultralytics + yolov8n-pose.pt):
    python evaluate_on_videos.py --videos /data/urfall --labels labels.csv [--sensitivity medium] [--bed-zones zones.json]

Good public sources: UR Fall Detection Dataset (falls + ADL clips), Le2i Fall
Dataset (home/office/coffee-room with annotated fall frames), plus 10-20 of
your own recordings in the actual demo room — elderly-style slow movements,
sitting on the bed, bending to the floor.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import cv2

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

MATCH_BEFORE_S = 1.0     # an alert may come slightly before the labelled start (labels are fuzzy)
MATCH_AFTER_S = 8.0      # ...and must come within 8 s after it


def run_video(path, sensitivity, bed_zones, max_width=640):
    from united_monitor import UnitedMonitor
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0 or fps > 120:
        fps = 30.0
    mon = UnitedMonitor(sensitivity=sensitivity, is_live=False, video_fps=fps, bed_zones=bed_zones)
    events, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if w > max_width:
            frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
        r = mon.process_frame(frame, timestamp=i / fps)
        events += [e for e in r["fall"]["events"] if e["type"] in ("fall_confirmed", "long_lie", "recovered")]
        i += 1
    cap.release()
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--sensitivity", default="medium")
    ap.add_argument("--bed-zones", default=None, help="JSON file: {video_name: [[ [x,y],... ]]}")
    ap.add_argument("--out", default="video_eval_report.json")
    args = ap.parse_args()

    zones = json.load(open(args.bed_zones)) if args.bed_zones else {}
    rows = list(csv.DictReader(open(args.labels)))
    tp = fn = fp = tn = 0
    latencies, report = [], []
    for row in rows:
        name = row["video"]
        start = float(row["fall_start_s"]) if row.get("fall_start_s") else None
        events = run_video(os.path.join(args.videos, name), args.sensitivity, zones.get(name))
        falls = [e for e in events if e["type"] == "fall_confirmed"]
        matched = None
        if start is not None:
            matched = next((e for e in falls if start - MATCH_BEFORE_S <= e["t"] <= start + MATCH_AFTER_S), None)
            if matched:
                tp += 1
                latencies.append(matched["t"] - start)
            else:
                fn += 1
            fp += len([e for e in falls if e is not matched])
        else:
            if falls:
                fp += len(falls)
            else:
                tn += 1
        verdict = ("TP" if matched else "FN") if start is not None else ("FP" if falls else "TN")
        print(f"{verdict:3s} {name:40s} label={start}  alerts={[(e['fall_type'], round(e['t'], 1)) for e in falls]}")
        if falls:
            print(f"     ↳ {falls[0]['explanation']}")
        report.append({"video": name, "label_fall_start_s": start, "verdict": verdict, "events": events})

    n_fall = tp + fn
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / n_fall if n_fall else 0.0
    print("\n── Event-level results ──")
    print(f"falls detected (recall):  {tp}/{n_fall} = {rec:.3f}")
    print(f"alert precision:          {prec:.3f}   (false alarms: {fp})")
    print(f"non-fall videos clean:    {tn}/{tn + len([r for r in report if r['verdict'] == 'FP'])}")
    if latencies:
        latencies.sort()
        print(f"alert latency after fall: median {latencies[len(latencies)//2]:.2f} s, max {latencies[-1]:.2f} s")
    json.dump({"tp": tp, "fn": fn, "fp": fp, "tn": tn, "precision": prec, "recall": rec,
               "latencies": latencies, "videos": report}, open(args.out, "w"), indent=2, default=str)
    print(f"report → {args.out}")


if __name__ == "__main__":
    main()
