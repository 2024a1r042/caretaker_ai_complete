"""
Analyze a recorded video file for falls using the YOLO + LSTM pipeline.

Usage:
    python run_video_monitor.py <path_to_video>
    python run_video_monitor.py        (prompts for path)
"""
import cv2
import os
import sys
import argparse

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

from united_monitor import UnitedMonitor, draw_united_interface

_YOLO_PATH = os.path.join(_here, "..", "yolov8n-pose.pt")
_LSTM_PATH = os.path.join(_here, "fall_lstm.pth")
_OUT_DIR   = os.path.join(_here, "..", "processed_videos")


def main():
    print("=== VIDEO FALL ANALYZER (YOLO + LSTM) ===")

    # Accept path as CLI arg or prompt
    if len(sys.argv) > 1:
        video_path = sys.argv[1].strip().strip('"').strip("'")
    else:
        video_path = input("Enter path to video file: ").strip().strip('"').strip("'")

    if not os.path.isfile(video_path):
        # Try relative to cwd
        alt = os.path.join(os.getcwd(), video_path)
        if os.path.isfile(alt):
            video_path = alt
        else:
            print(f"[Error] File not found: {video_path}")
            return

    os.makedirs(_OUT_DIR, exist_ok=True)
    out_name = "analyzed_" + os.path.basename(video_path)
    out_path = os.path.join(_OUT_DIR, out_name)

    print(f"Input : {video_path}")
    print(f"Output: {out_path}")

    # Initialize monitor (video mode: no frame skipping)
    monitor = UnitedMonitor(
        sensitivity="medium",
        inactivity_threshold=30,
        is_live=False,
        process_every_n_frames=1,
    )

    cap   = cv2.VideoCapture(video_path)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    fall_timestamps = []
    fall_event_count = 0
    frame_num        = 0
    _debug_printed   = False  # print first LSTM prob for diagnostics

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_num += 1

        results   = monitor.process_frame(frame)
        annotated = draw_united_interface(frame, results, draw_skeleton=True)
        writer.write(annotated)

        gs       = results["global_state"]
        fall_res = results["fall"]

        # Print the first LSTM probability we get for debugging
        if not _debug_printed and fall_res.get("confidence", 0) > 0:
            lstm_conf = fall_res["confidence"]
            bbox_h    = fall_res.get("bbox_is_horizontal", False)
            print(f"  [Debug] First LSTM output: prob={lstm_conf:.4f}  bbox_horizontal={bbox_h}")
            _debug_printed = True

        # Only log/count when a NEW fall event fires (not every frame of the fall)
        if fall_res.get("fall_event_fired", False):
            fall_event_count += 1
            ts = frame_num / fps
            fall_timestamps.append(ts)
            bbox_h = fall_res.get("bbox_is_horizontal", False)
            conf   = fall_res.get("confidence", 0)
            print(f"  [FALL EVENT #{fall_event_count}] at {ts:.1f}s  "
                  f"(frame {frame_num}/{total})  conf={conf:.3f}  horizontal={bbox_h}")

        if frame_num % 100 == 0:
            pct = int(100 * frame_num / max(1, total))
            print(f"  Progress: {frame_num}/{total} frames ({pct}%)")

    cap.release()
    writer.release()

    print(f"\n=== Done ===")
    print(f"Fall EVENTS detected : {fall_event_count}  (unique falls, not per-frame count)")
    if fall_timestamps:
        print(f"Event timestamps     : {[f'{t:.1f}s' for t in fall_timestamps]}") 
    print(f"Output saved         : {out_path}")


if __name__ == "__main__":
    main()
