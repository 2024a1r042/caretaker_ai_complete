"""
UnitedMonitor — YOLOv8-pose tracking + explainable fall inference.

Pipeline per frame:
    YOLOv8-pose  →  humanity filter  →  sticky tracking of the monitored person
                 →  BiGRU sequence model (optional learned cue)
                 →  FallInferenceEngine (kinematics + posture + time state machine)
                 →  InactivityMonitor

The decision is made by FallInferenceEngine (fall_inference.py). The BiGRU
probability is fed to it as ONE weighted signal instead of being a hard gate,
so a fall is still caught when the learned model is unsure, and every alert
carries human-readable evidence.

process_frame(frame, timestamp=None) → {
    "fall": {
        "fall_detected", "fall_event_fired", "state", "events", "fall_event",
        "all_persons", "features", "keypoints", "boxes", "fall_anchor_box", "live"
    },
    "inactivity": {...},
    "global_state": {"fall_detected", "inactivity_alert", "fall_state", "fps", "timestamp"}
}
(The original keys are unchanged so existing callers keep working.)
"""

import os
import sys
import time
import math
import cv2
import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.join(_here, "BodyMovementDetection"))

try:
    from ultralytics import YOLO
except ImportError:
    raise RuntimeError("ultralytics not installed. Run: pip install ultralytics")

from fall_inference import (FallInferenceEngine, EV_FALL, EV_RECOVERED, EV_LONG_LIE,
                            FALL_CONFIRMED, LONG_LIE, DESCENT, ON_GROUND_CHECK, LYING_IN_BED, NORMAL, NO_PERSON)
from inactivity_monitor import InactivityMonitor

try:
    import torch
    from fall_lstm_model import FallSequenceBuffer, load_model, DEFAULT_SEQ_LEN
    _TORCH_OK = True
except Exception as _e:  # torch missing → engine still runs on kinematics alone
    print(f"[UnitedMonitor] Learned model unavailable ({_e}); running kinematic inference only.")
    _TORCH_OK = False

# Pose model. Tested on real overhead footage: yolov8n-pose at the default size
# found a person LYING on the floor in 1/11 frames; yolov8s-pose found 9/11.
# Override in .env: POSE_MODEL=yolov8n-pose.pt (faster, weaker), POSE_IMGSZ=960 (small/far people).
def _pose_model_path():
    name = os.getenv("POSE_MODEL", "").strip()
    if name:
        cand = name if os.path.isabs(name) else os.path.join(_here, "..", name)
        return cand if os.path.exists(cand) else name      # bare name → ultralytics downloads it
    for n in ("yolov8s-pose.pt", "yolov8n-pose.pt"):
        cand = os.path.join(_here, "..", n)
        if os.path.exists(cand):
            return cand
    return "yolov8s-pose.pt"


_YOLO_MODEL_PATH = _pose_model_path()
POSE_IMGSZ = int(os.getenv("POSE_IMGSZ", "640"))
POSE_CONF = float(os.getenv("POSE_CONF", "0.15"))
_LSTM_MODEL_PATH = os.path.join(_here, "fall_lstm.pth")

STATE_LABELS = {
    NO_PERSON: ("Scanning...", (120, 120, 120)),
    NORMAL: ("Monitoring", (0, 200, 0)),
    DESCENT: ("Rapid drop detected...", (0, 165, 255)),
    ON_GROUND_CHECK: ("On the ground - verifying", (0, 140, 255)),
    FALL_CONFIRMED: ("FALL DETECTED", (0, 0, 255)),
    LONG_LIE: ("FALL - NOT MOVING", (0, 0, 200)),
    LYING_IN_BED: ("Resting in bed", (200, 160, 0)),
}


class UnitedMonitor:
    def __init__(self, sensitivity="medium", inactivity_threshold=30, stable_percentage=0.10, is_live=False,
                 process_every_n_frames=2, video_fps: float = 0.0, bed_zones=None, long_lie_s=None,
                 confirm_s: float = None):
        print(f"[UnitedMonitor] Initializing... live={is_live} sensitivity={sensitivity}")
        self.sensitivity = sensitivity
        self.is_live = is_live
        self.process_every_n_frames = process_every_n_frames if is_live else 1

        self._frame_counter = 0
        self._inactivity_alert = False
        self._last_result = None
        self._fall_anchor_box = None
        self._t0 = time.time()

        # Tracking state — once the monitored_id is locked it never auto-switches
        self._monitored_id = None
        self._monitored_id_locked = False
        self._monitored_centroid = None

        self._fps_start = time.time()
        self._fps_frames = 0
        self._video_fps = video_fps
        self._current_fps = video_fps if (not is_live and video_fps > 0) else 0.0

        self._yolo = YOLO(_YOLO_MODEL_PATH)
        print(f"[UnitedMonitor] pose model {os.path.basename(str(_YOLO_MODEL_PATH))} imgsz={POSE_IMGSZ} conf={POSE_CONF}")

        # Optional learned cue
        self._lstm = None
        self._seq_buf = None
        if _TORCH_OK:
            try:
                self._lstm, self._device = load_model(_LSTM_MODEL_PATH)
                seq_len = DEFAULT_SEQ_LEN if is_live else 15
                mode = "enhanced" if getattr(self._lstm, "input_size", 34) == 72 else "coords"
                self._seq_buf = FallSequenceBuffer(seq_len=seq_len, feature_mode=mode)
            except Exception as e:
                print(f"[UnitedMonitor] BiGRU not loaded ({e}); kinematic inference only.")

        self.engine = FallInferenceEngine(sensitivity=sensitivity, bed_zones=bed_zones,
                                           long_lie_s=long_lie_s, confirm_s=confirm_s)
        self._inactivity = InactivityMonitor(safety_threshold_seconds=inactivity_threshold,
                                             stability_percentage=stable_percentage)
        # alias used by stream_manager.update_threshold
        self.inactivity_monitor = self._inactivity

    # ── configuration ───────────────────────────────────────────────────────
    def set_bed_zones(self, zones):
        """zones: list of polygons in normalised (0..1) image coordinates."""
        self.engine.set_bed_zones(zones)

    def flush(self, t: float = None) -> list:
        """Flush and finalize any pending fall candidate at end of offline video."""
        return self.engine.flush(t)

    # ── humanity filter (unchanged from the original pipeline) ──────────────
    def _is_human_pose(self, kps_xy, kps_conf, box):
        if kps_xy is None or kps_conf is None or box is None:
            return False
        bbox_w = box[2] - box[0]
        bbox_h = box[3] - box[1]
        if bbox_w * bbox_h < 2000:
            return False
        is_horizontal_bbox = (bbox_w > bbox_h * 1.2) if bbox_h > 0 else False
        if is_horizontal_bbox:
            core_joints = [5, 6, 11, 12]
            core_conf = sum(1 for idx in core_joints if idx < len(kps_conf) and kps_conf[idx] > 0.3)
            return core_conf >= 3
        neck = (kps_xy[5] + kps_xy[6]) / 2.0
        hip = (kps_xy[11] + kps_xy[12]) / 2.0
        spine_len = math.sqrt((neck[0] - hip[0]) ** 2 + (neck[1] - hip[1]) ** 2)
        if spine_len < 0.15 * bbox_h:
            return False
        head_conf_count = sum(1 for idx in [0, 1, 2, 3, 4] if idx < len(kps_conf) and kps_conf[idx] > 0.5)
        if head_conf_count < 2:
            return False
        major_joints = [5, 6, 11, 12, 13, 14, 15, 16]
        conf_count = sum(1 for idx in major_joints if idx < len(kps_conf) and kps_conf[idx] > 0.45)
        return conf_count >= 5

    def _timestamp(self, timestamp):
        if timestamp is not None:
            return float(timestamp)
        if not self.is_live and self._video_fps > 0:
            return self._frame_counter / self._video_fps
        return time.time() - self._t0

    # ── main ────────────────────────────────────────────────────────────────
    def process_frame(self, frame: np.ndarray, timestamp: float = None) -> dict:
        self._frame_counter += 1
        now = time.time()

        if self.is_live and (self._frame_counter % self.process_every_n_frames != 0) and self._last_result:
            # reuse the last result but never re-emit its events
            reused = dict(self._last_result)
            reused["fall"] = dict(self._last_result["fall"], fall_event_fired=False, events=[])
            return reused

        t = self._timestamp(timestamp)
        h_img, w_img = frame.shape[:2]

        if self.is_live:
            yolo_res = self._yolo.track(frame, persist=True, verbose=False, classes=[0], conf=POSE_CONF, imgsz=POSE_IMGSZ)[0]
        else:
            yolo_res = self._yolo.predict(frame, verbose=False, classes=[0], conf=POSE_CONF, imgsz=POSE_IMGSZ)[0]
        boxes_raw = yolo_res.boxes
        kps_data = yolo_res.keypoints

        all_persons, possible_humans = [], []
        monitored_idx = -1

        if boxes_raw is not None and len(boxes_raw.xyxy) > 0:
            boxes = boxes_raw.xyxy.cpu().numpy()
            yolo_ids = boxes_raw.id.cpu().numpy().astype(int) if boxes_raw.id is not None else None
            for i in range(len(boxes)):
                kp_xy = kps_data.xy[i].cpu().numpy()
                kp_conf = kps_data.conf[i].cpu().numpy()
                y_id = yolo_ids[i] if yolo_ids is not None else i
                if self._is_human_pose(kp_xy, kp_conf, boxes[i]):
                    box = boxes[i]
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    h_score = sum(kp_conf[idx] for idx in [5, 6, 11, 12, 13, 14, 15, 16] if idx < len(kp_conf))
                    possible_humans.append({"id": y_id, "box": box, "xy": kp_xy, "conf": kp_conf,
                                            "cx": cx, "cy": cy, "h_score": h_score})

            if possible_humans:
                target = None
                if self._monitored_id is not None:
                    matches = [p for p in possible_humans if p["id"] == self._monitored_id]
                    if matches:
                        target = matches[0]
                if target is None and self._monitored_centroid is not None:
                    best = 1e9
                    for p in possible_humans:
                        d = math.hypot(p["cx"] - self._monitored_centroid[0], p["cy"] - self._monitored_centroid[1])
                        if d < best and d < 250:
                            best, target = d, p
                if target is None and len(possible_humans) == 1:
                    target = possible_humans[0]
                    self._monitored_id_locked = True
                if target is None and not self._monitored_id_locked:
                    target = max(possible_humans, key=lambda p: p["h_score"])
                    self._monitored_id_locked = True

                if target is not None:
                    monitored_idx = target["id"]
                    self._monitored_id = monitored_idx
                    self._monitored_centroid = (target["cx"], target["cy"])

                for p in possible_humans:
                    is_mon = (p["id"] == monitored_idx)
                    all_persons.append({"box": p["box"], "xy": p["xy"], "is_monitored": is_mon,
                                        "label": "MONITORED" if is_mon else "VISITOR"})
            else:
                self._monitored_centroid = None
        else:
            self._monitored_centroid = None

        # ── inference on the monitored person ──
        monitored_xy = monitored_box = conf_kps = None
        lstm_prob = None
        if monitored_idx != -1:
            p = [p for p in possible_humans if p["id"] == monitored_idx][0]
            monitored_xy, monitored_box, conf_kps = p["xy"], p["box"], p["conf"]
            if self._lstm is not None and self._seq_buf is not None:
                self._seq_buf.push(monitored_xy, conf_kps)
                if self._seq_buf.ready:
                    with torch.no_grad():
                        logits = self._lstm(self._seq_buf.get_tensor(device=self._device))
                        lstm_prob = float(torch.softmax(logits, dim=1)[0, 1])

        r = self.engine.update(t, monitored_xy, conf_kps, frame_size=(w_img, h_img), lstm_prob=lstm_prob)

        fall_fired = any(e["type"] == EV_FALL for e in r["events"])
        if fall_fired and monitored_box is not None:
            self._fall_anchor_box = monitored_box.copy()
        if not r["fall_active"]:
            self._fall_anchor_box = None

        live = r["live"]
        features = {
            "lstm_prob": lstm_prob or 0.0,
            "is_upright": bool(live.get("upright", False)),
            "torso_angle": live.get("torso_angle"),
            "head_height": live.get("head_height"),
            "hip_height": live.get("hip_height"),
            "on_ground": live.get("on_ground"),
            "motion": live.get("motion"),
        }

        inactivity_res = self._inactivity.update([monitored_box.tolist()] if monitored_box is not None else [], now)
        self._inactivity_alert = inactivity_res.get("alert", False)

        result = {
            "fall": {
                "fall_detected": r["fall_active"],
                "fall_event_fired": fall_fired,
                "state": r["state"],
                "events": r["events"],
                "fall_event": r["fall_event"],
                "time_on_ground_s": r["time_on_ground_s"],
                "live": live,
                "all_persons": all_persons,
                "features": features,
                "keypoints": monitored_xy,
                "boxes": monitored_box,
                "fall_anchor_box": self._fall_anchor_box,
            },
            "inactivity": inactivity_res,
            "global_state": {
                "fall_detected": r["fall_active"],
                "fall_state": r["state"],
                "inactivity_alert": self._inactivity_alert,
                "fps": self._current_fps,
                "timestamp": t,
            },
        }

        self._fps_frames += 1
        if now - self._fps_start > 1.0:
            self._current_fps = self._fps_frames / (now - self._fps_start)
            self._fps_start, self._fps_frames = now, 0
        self._last_result = result
        return result

    def reset_fall(self):
        self.engine.reset()
        self._fall_anchor_box = None
        if self._seq_buf is not None:
            self._seq_buf.reset()


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def draw_united_interface(frame, results, draw_skeleton=True):
    out = frame.copy()
    fall_res = results["fall"]
    gs = results["global_state"]
    persons = fall_res.get("all_persons", [])
    state = fall_res.get("state", NORMAL)
    fall_active = gs["fall_detected"]
    h, w = out.shape[:2]
    k = max(0.32, min(0.6, w / 1100.0))          # text scale follows frame size
    lh = int(34 * k + 6)                          # line height

    for p in persons:
        is_main = p["is_monitored"]
        if is_main and fall_active:
            color, label = (0, 0, 255), "! FALL"
        elif is_main and gs.get("inactivity_alert"):
            color, label = (0, 128, 255), ">> INACTIVE"
        elif is_main:
            color, label = (0, 200, 0), ">> MONITORED"
        else:
            color, label = (0, 200, 255), "VISITOR"
        x1, y1, x2, y2 = map(int, p["box"])
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3 if is_main else 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, k, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(out, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, k, (255, 255, 255), 1, cv2.LINE_AA)
        if draw_skeleton and is_main and p["xy"] is not None:
            kps = p["xy"]
            conn = [(0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
                    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
            for s, e in conn:
                if (kps[s][0] > 0 or kps[s][1] > 0) and (kps[e][0] > 0 or kps[e][1] > 0):
                    cv2.line(out, (int(kps[s][0]), int(kps[s][1])), (int(kps[e][0]), int(kps[e][1])), color, 2)

    # top status bar
    label, color = STATE_LABELS.get(state, ("Monitoring", (0, 200, 0)))
    if gs.get("inactivity_alert") and not fall_active:
        label, color = "INACTIVITY ALERT", (0, 128, 255)
    if fall_active and fall_res.get("time_on_ground_s"):
        label += f"  ({fall_res['time_on_ground_s']:.0f}s on floor)"
    cv2.rectangle(out, (0, 0), (w, lh + 6), (20, 20, 20), -1)
    cv2.putText(out, label, (8, lh - 2), cv2.FONT_HERSHEY_SIMPLEX, k, color, 2 if k > 0.45 else 1, cv2.LINE_AA)
    if w >= 480:
        fps_txt = f"FPS:{gs.get('fps', 0.0):.1f}"
        (fw, _), _ = cv2.getTextSize(fps_txt, cv2.FONT_HERSHEY_SIMPLEX, k * 0.8, 1)
        cv2.putText(out, fps_txt, (w - fw - 8, lh - 2), cv2.FONT_HERSHEY_SIMPLEX, k * 0.8, (200, 200, 200), 1, cv2.LINE_AA)

    # bottom panel: the inference itself (evidence when fallen, live signals otherwise)
    lines = []
    ev = fall_res.get("fall_event")
    if fall_active and ev:
        lines.append(f"{ev.get('fall_type', 'fall').replace('_', ' ').upper()}  conf {ev.get('confidence', 0):.2f}  "
                     f"severity {ev.get('severity', '')}")
        for item in ev.get("evidence", [])[:4]:
            lines.append(("+ " if item.get("passed") else "- ") + item.get("text", ""))
    else:
        lv = fall_res.get("live") or {}
        if lv:
            lines.append(f"head {lv.get('head_height', 0)*100:.0f}%  hips {lv.get('hip_height', 0)*100:.0f}%  "
                         f"torso {lv.get('torso_angle', 0):.0f} deg  "
                         + ("ON GROUND" if lv.get("on_ground") else "upright" if lv.get("upright") else "")
                         + ("  [bed zone]" if lv.get("in_bed_zone") else ""))
            if lv.get("lstm_prob") is not None:
                lines.append(f"BiGRU fall prob {lv['lstm_prob']:.2f}  (one input of the fusion)")
    wrapped = []
    for ln in lines:
        wrapped.extend(_wrap(ln, max(24, int(w / (19 * k)))))
    if wrapped:
        wrapped = wrapped[: max(2, int(h * 0.45 / lh))]     # never cover more than ~45% of the picture
        panel_h = 8 + lh * len(wrapped)
        overlay = out.copy()
        cv2.rectangle(overlay, (0, h - panel_h), (w, h), (15, 15, 15), -1)
        out = cv2.addWeighted(overlay, 0.65, out, 0.35, 0)
        for i, ln in enumerate(wrapped):
            cv2.putText(out, ln, (8, h - panel_h + lh + lh * i - 4), cv2.FONT_HERSHEY_SIMPLEX, k * 0.85,
                        (255, 255, 255) if i else (80, 200, 255) if fall_active else (220, 220, 220), 1, cv2.LINE_AA)
    return out
