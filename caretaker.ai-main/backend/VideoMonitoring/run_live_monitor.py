"""
Live webcam / IP-camera fall monitor using YOLO + LSTM pipeline.

Usage:
    # Local webcam
    python run_live_monitor.py
    python run_live_monitor.py --camera 0

    # IP / network camera via URL (RTSP, HTTP stream)
    python run_live_monitor.py --url rtsp://user:pass@192.168.1.10:554/stream
    python run_live_monitor.py --url http://192.168.1.10:8080/video

Options:
    --session-id  Active monitoring session ID (for API alerts)
    --token       JWT auth token
    --camera      Camera index (default: 0)  [ignored if --url is given]
    --url         IP camera / RTSP / HTTP stream URL
    --sensitivity low | medium | high  (default: medium)
    --threshold   Inactivity threshold seconds (default: 30)
"""
import cv2
import os
import sys
import argparse
import threading
import time
from datetime import datetime

_here       = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(_here)
sys.path.insert(0, _here)
sys.path.insert(0, backend_dir)

from united_monitor import UnitedMonitor, draw_united_interface

API_URL = "http://127.0.0.1:8000/api"


class LiveMonitorSession:
    """Live webcam monitoring session with optional backend alert integration."""

    def __init__(self, session_id=None, token=None,
                 camera_source=0, sensitivity="medium", threshold=30):
        self.session_id    = session_id
        self.token         = token
        self.camera_source = camera_source   # int index OR string URL

        self.monitor = UnitedMonitor(
            sensitivity=sensitivity,
            inactivity_threshold=threshold,
            is_live=True,
            process_every_n_frames=2,
        )

        self.running                  = False
        self.last_fall_alert_time     = 0
        self.last_inactivity_alert_time = 0
        self.alert_cooldown           = 30   # seconds between same-type alerts

    def send_alert(self, alert_type: str, data: dict):
        """POST alert to backend (non-blocking)."""
        if not self.session_id:
            print(f"[Local] {alert_type.upper()} ALERT: {data}")
            return

        import requests

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload  = {"alert_type": alert_type, "alert_data": data}
        endpoint = f"{API_URL}/video-monitoring/alert/{self.session_id}"

        def _send():
            try:
                r = requests.post(endpoint, json=payload, headers=headers, timeout=5)
                status = "OK" if r.status_code == 200 else f"HTTP {r.status_code}"
                print(f"[Alert sent] {alert_type} → {status}")
            except Exception as e:
                print(f"[Alert failed] {e}")

        threading.Thread(target=_send, daemon=True).start()

    def run(self):
        src_label = self.camera_source if isinstance(self.camera_source, int) \
                    else f"URL: {self.camera_source}"
        print(f"=== Live Monitor Started  "
              f"(session={self.session_id or 'local'}  source={src_label}) ===")
        print("Press 'q' to quit.\n")

        # Support both integer device index and URL strings (RTSP, HTTP, etc.)
        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            print(f"[Error] Cannot open source: {self.camera_source}")
            if isinstance(self.camera_source, str):
                print("  Tip: check the URL is reachable and OpenCV was built with FFMPEG.")
            return

        self.running = True

        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    print("[Warn] Failed to read frame, retrying…")
                    time.sleep(0.05)
                    continue

                results = self.monitor.process_frame(frame)
                gs      = results["global_state"]
                now     = time.time()

                # Fall alert
                if gs["fall_detected"]:
                    if now - self.last_fall_alert_time > self.alert_cooldown:
                        self.last_fall_alert_time = now
                        self.send_alert("fall", {
                            "timestamp": datetime.now().isoformat(),
                            "message":   "Fall detected by live monitor",
                            "confidence": results["fall"].get("confidence", 0),
                        })
                        # Force fresh 30-frame evidence before next alert
                        self.monitor.reset_fall()

                # Inactivity alert
                if gs["inactivity_alert"]:
                    if now - self.last_inactivity_alert_time > self.alert_cooldown:
                        self.last_inactivity_alert_time = now
                        inactive_sec = results["inactivity"].get("time_inactive_seconds", 0)
                        self.send_alert("inactivity", {
                            "timestamp": datetime.now().isoformat(),
                            "message":   f"Inactivity detected ({inactive_sec}s)",
                            "duration":  inactive_sec,
                        })

                display_frame = draw_united_interface(frame, results)

                if self.session_id:
                    cv2.putText(display_frame,
                                f"Session: {self.session_id[:8]}…",
                                (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                (200, 200, 200), 1)

                try:
                    cv2.imshow("Caretaker.ai — Live Monitor", display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        self.running = False
                except cv2.error:
                    # Headless environment — no display, use sleep for rate control
                    time.sleep(0.04)

        except KeyboardInterrupt:
            print("\nStopping…")
        finally:
            cap.release()
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
            print("Monitor stopped.")


def main():
    parser = argparse.ArgumentParser(description="Caretaker.ai Live Monitor")
    parser.add_argument("--session-id",  type=str, default=None)
    parser.add_argument("--token",       type=str, default=None)
    parser.add_argument("--camera",      type=int, default=0,
                        help="Local webcam index (default 0). Ignored if --url is set.")
    parser.add_argument("--url",         type=str, default=None,
                        help="IP camera / RTSP / HTTP stream URL, e.g. rtsp://user:pass@ip/stream")
    parser.add_argument("--sensitivity", type=str, default="medium",
                        choices=["low", "medium", "high"])
    parser.add_argument("--threshold",   type=int, default=30)
    args = parser.parse_args()

    # URL takes priority over camera index
    camera_source = args.url if args.url else args.camera

    session = LiveMonitorSession(
        session_id    = args.session_id,
        token         = args.token,
        camera_source = camera_source,
        sensitivity   = args.sensitivity,
        threshold     = args.threshold,
    )
    session.run()


if __name__ == "__main__":
    main()
