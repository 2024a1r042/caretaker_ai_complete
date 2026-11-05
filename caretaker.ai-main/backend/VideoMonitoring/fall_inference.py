"""
fall_inference.py — Explainable, multi-signal fall inference engine.

This is the decision layer that sits on top of any pose estimator
(YOLOv8-pose on the backend, MoveNet in the browser — see the JS twin in
frontend/static/js/fall-inference-engine.js, which mirrors this file 1:1).

WHY THIS EXISTS
---------------
The previous pipeline fired a fall only if one number (the BiGRU score) was
above 0.90 for N frames. If the model was unsure, nothing happened; if it
fired, nobody could say *why*. Real falls in elderly people are also often
slow (sliding off a chair) or end out of view, which a single classifier
trained on fast falls misses.

This engine instead measures what physically happens in a fall and reasons
over time with a state machine:

    NORMAL ──fast drop──▶ DESCENT ──ends low──▶ ON_GROUND_CHECK ──stays low──▶ FALL_CONFIRMED
       │                     │ (not low → rejected: sat down / bent over)         │      │
       │                     └─person vanished mid-drop──▶ (out-of-view fall)     │      │
       └─on floor after being upright (slow) ─────────────▶ ON_GROUND_CHECK       │      │
                                                                                  ▼      ▼
                                                         RECOVERED (got up)   LONG_LIE (still on floor)

Signals (all scale-free — normalised by the person's own standing height,
so they work near or far from the camera and at any frame-rate):
    • head / hip height above the floor (fraction of standing height)
    • peak downward speed            (standing-heights per second)
    • total drop within the descent  (fraction of standing height)
    • torso rotation                 (degrees from vertical, and change)
    • body extent collapse           (current height / standing height)
    • time spent on the ground and stillness (keypoint motion)
    • optional learned score (BiGRU) — one input, not a gate
    • bed / sofa zones               (lying there is normal)

Every confirmed event carries an `evidence` list and a plain-language
`explanation`, so the caregiver (and the reviewer) can see the inference,
not just a "HIGH / MEDIUM / LOW" label.

The engine is pure Python + math (no numpy/torch requirement) so it can be
unit-tested with synthetic skeletons and reused anywhere.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Sequence, Tuple

# ── COCO keypoint indices (YOLOv8-pose and MoveNet use the same order) ───────
NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHO, R_SHO = 5, 6
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANK, R_ANK = 15, 16
HEAD_IDX = (NOSE, L_EYE, R_EYE, L_EAR, R_EAR)

# ── States ───────────────────────────────────────────────────────────────────
NO_PERSON = "no_person"
NORMAL = "normal"
DESCENT = "descent"
ON_GROUND_CHECK = "on_ground_check"
FALL_CONFIRMED = "fall_confirmed"
LONG_LIE = "long_lie"
LYING_IN_BED = "lying_in_bed"

# ── Event types emitted ──────────────────────────────────────────────────────
EV_FALL = "fall_confirmed"
EV_RECOVERED = "recovered"
EV_LONG_LIE = "long_lie"
EV_REJECTED = "candidate_rejected"   # informational (debug / transparency)


# ── Sensitivity presets ──────────────────────────────────────────────────────
# v_fast      : peak downward head speed (standing-heights/s) that starts a DESCENT
# drop_fast   : minimum head drop (fraction of standing height) for a DESCENT
# confirm_s   : how long the person must stay on the ground before we confirm
# slow_floor_s: how long someone must be on the floor (no fast drop seen) before a
#               "possible fall" check-in is raised
# long_lie_s  : motionless on the floor this long after a fall → critical
PRESETS: Dict[str, Dict[str, float]] = {
    "low":    {"v_fast": 1.10, "drop_fast": 0.35, "confirm_s": 2.5, "slow_floor_s": 15.0, "long_lie_s": 45.0, "min_score": 0.45},
    "medium": {"v_fast": 0.85, "drop_fast": 0.28, "confirm_s": 1.5, "slow_floor_s": 8.0,  "long_lie_s": 25.0, "min_score": 0.35},
    "high":   {"v_fast": 0.65, "drop_fast": 0.22, "confirm_s": 1.0, "slow_floor_s": 5.0,  "long_lie_s": 15.0, "min_score": 0.25},
}

# Geometry thresholds (fractions of standing keypoint height) — documented so
# they can be defended in a review:
#   standing: head ≈ 1.0, hips ≈ 0.55-0.6
#   chair:    head ≈ 0.75-0.8, hips ≈ 0.25-0.3
#   squat:    hips ≈ 0.2-0.25, kneel: hips ≈ 0.3
#   on floor: hips ≈ 0.0-0.1, head ≈ 0.0-0.35 (sitting up on floor)
HIP_ON_FLOOR = 0.15
HEAD_LOW = 0.35
HEAD_LOWISH = 0.45
HIP_LYING_MAX = 0.25
EXTENT_COLLAPSED = 0.45
UPRIGHT_HEAD = 0.72
UPRIGHT_ANGLE = 35.0
LYING_ANGLE = 55.0

KP_MIN_CONF = 0.3
DESCENT_WINDOW_S = 1.5
SLOW_WINDOW_S = 6.0
DESCENT_TIMEOUT_S = 2.5
LOST_DURING_DESCENT_S = 1.0
LOST_RESET_S = 2.0
RECOVER_HOLD_S = 2.0
COOLDOWN_S = 5.0
STILL_MOTION = 0.12          # mean keypoint motion over 1 s, in torso lengths
VEL_MIN_DT = 0.2             # seconds; velocity measured over at least this gap


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _mean_pt(pts: Sequence[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def point_in_polygon(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    """Ray-casting point-in-polygon. `poly` is a list of (x, y) in the same units."""
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


@dataclass
class _Sample:
    t: float
    head_h: float
    hip_h: float
    angle: float
    extent: float
    on_ground: bool
    on_floor: bool
    upright: bool
    kps: List[Optional[Tuple[float, float]]]
    hip_xy: Tuple[float, float]


@dataclass
class _Candidate:
    kind: str                 # "fast" | "slow"
    t_start: float
    t_low: Optional[float] = None
    peak_v: float = 0.0
    head_drop: float = 0.0
    hip_drop: float = 0.0
    angle_before: float = 0.0
    angle_after: float = 0.0
    descent_s: float = 0.0
    ground_frames: int = 0
    floor_frames: int = 0
    total_frames: int = 0
    lstm_max: float = 0.0
    start_head_h: float = 1.0


class FallInferenceEngine:
    """
    Feed one pose per frame with `update(...)`; read `state`, the returned
    dict, and any `events` emitted on that frame.
    """

    def __init__(self, sensitivity: str = "medium",
                 bed_zones: Optional[List[List[Tuple[float, float]]]] = None,
                 long_lie_s: Optional[float] = None,
                 confirm_s: Optional[float] = None):
        self.cfg = dict(PRESETS.get(sensitivity, PRESETS["medium"]))
        if long_lie_s is not None:
            self.cfg["long_lie_s"] = float(long_lie_s)
        if confirm_s is not None:
            self.cfg["confirm_s"] = float(confirm_s)
        self.sensitivity = sensitivity if sensitivity in PRESETS else "medium"
        self.bed_zones: List[List[Tuple[float, float]]] = list(bed_zones or [])
        self.reset()

    # ── public helpers ──────────────────────────────────────────────────────
    def reset(self):
        self.state = NO_PERSON
        self.h_ref: Optional[float] = None       # standing keypoint height (px)
        self.torso_ref: Optional[float] = None    # torso length when upright (px)
        self.floor_y: Optional[float] = None      # image y of the floor under the feet
        self.history: Deque[_Sample] = deque()
        self.candidate: Optional[_Candidate] = None
        self.last_seen_t: Optional[float] = None
        self.last_t: Optional[float] = None
        self.cooldown_until = -1e9
        self.upright_since: Optional[float] = None
        self.still_since: Optional[float] = None
        self.fall_t: Optional[float] = None
        self.fall_event: Optional[dict] = None
        self.long_lie_fired = False
        self.event_counter = 0
        self._smooth: List[Optional[Tuple[float, float]]] = [None] * 17
        self._pair_off: Dict[str, Tuple[float, float]] = {}
        self._last_obs: Optional[dict] = None
        self.floor_since: Optional[float] = None
        self._last_floor_t: Optional[float] = None
        self._lost_checked = False

    def set_bed_zones(self, zones: List[List[Tuple[float, float]]]):
        """Zones are polygons in normalised image coords (0..1)."""
        self.bed_zones = [list(map(tuple, z)) for z in (zones or [])]

    def flush(self, t: Optional[float] = None) -> List[dict]:
        """
        Called at end of offline video processing to finalize any pending candidate.
        If a fall candidate was in ON_GROUND_CHECK or DESCENT when the video ended,
        and met the drop speed or on-ground requirements, confirm the fall!
        """
        events: List[dict] = []
        c = self.candidate
        if c is not None and self.state in (ON_GROUND_CHECK, DESCENT):
            t_now = t if t is not None else (self.last_t or 0.0)
            sample = self.history[-1] if self.history else None
            if sample is not None:
                is_fast = c.peak_v >= 0.7 * self.cfg["v_fast"]
                has_ground = c.ground_frames > 0 or c.floor_frames > 0 or sample.on_ground or sample.on_floor
                if is_fast and has_ground:
                    self._confirm(t_now, sample, events, fall_type="impact_at_video_end")
                    self.candidate = None
                    self.state = FALL_CONFIRMED
        return events

    # ── core ────────────────────────────────────────────────────────────────
    def update(self, t: float,
               kps_xy: Optional[Sequence[Sequence[float]]],
               kps_conf: Optional[Sequence[float]] = None,
               frame_size: Optional[Tuple[float, float]] = None,
               lstm_prob: Optional[float] = None) -> dict:
        """
        t          : timestamp in seconds (video time for files, wall time live)
        kps_xy     : 17×2 pixel coords, or None when no person is visible
        kps_conf   : 17 confidences (None → all treated as visible)
        frame_size : (width, height) — needed only for bed zones
        lstm_prob  : optional learned fall probability for this frame
        """
        events: List[dict] = []
        dt = 0.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t

        obs = self._observe(t, dt, kps_xy, kps_conf)
        if obs is None:
            self._on_lost(t, events)
            return self._result(t, None, events, lstm_prob)

        self.last_seen_t = t
        self._lost_checked = False
        sample = obs["sample"]
        if sample.on_floor:
            if self.floor_since is None:
                self.floor_since = t
            self._last_floor_t = t
        elif self.floor_since is not None and self._last_floor_t is not None and t - self._last_floor_t > 1.0:
            self.floor_since = None
        self.history.append(sample)
        while self.history and t - self.history[0].t > SLOW_WINDOW_S + 0.5:
            self.history.popleft()

        in_bed = self._in_bed(sample.hip_xy, frame_size)
        obs["in_bed"] = in_bed

        if self.state == NO_PERSON:
            self.state = NORMAL

        # upright / still trackers
        if sample.upright:
            self.upright_since = self.upright_since if self.upright_since is not None else t
        else:
            self.upright_since = None
        motion = self._motion(t)
        obs["motion"] = motion
        if motion is not None and motion < STILL_MOTION:
            self.still_since = self.still_since if self.still_since is not None else t
        else:
            self.still_since = None

        if lstm_prob is not None and self.candidate is not None:
            self.candidate.lstm_max = max(self.candidate.lstm_max, float(lstm_prob))

        # ── state machine ──
        if self.state == NORMAL:
            self._step_normal(t, sample, in_bed, lstm_prob, events)
        elif self.state == DESCENT:
            self._step_descent(t, sample, events)
        elif self.state == ON_GROUND_CHECK:
            self._step_ground_check(t, sample, in_bed, events)
        elif self.state in (FALL_CONFIRMED, LONG_LIE):
            self._step_fallen(t, sample, events)
        elif self.state == LYING_IN_BED:
            if sample.upright or not sample.on_ground and sample.head_h > HEAD_LOWISH:
                self.state = NORMAL

        self._last_obs = obs
        return self._result(t, obs, events, lstm_prob)

    # ── observation / geometry ──────────────────────────────────────────────
    def _observe(self, t, dt, kps_xy, kps_conf) -> Optional[dict]:
        if kps_xy is None:
            return None
        pts: List[Optional[Tuple[float, float]]] = []
        for i in range(17):
            x, y = float(kps_xy[i][0]), float(kps_xy[i][1])
            c = 1.0 if kps_conf is None else float(kps_conf[i])
            if c < KP_MIN_CONF or (x == 0.0 and y == 0.0):
                pts.append(None)
            else:
                pts.append((x, y))

        # light temporal smoothing (exponential, frame-rate aware) to kill jitter
        alpha = 1.0 if dt <= 0 else 1.0 - math.exp(-dt / 0.05)
        sm: List[Optional[Tuple[float, float]]] = []
        for i, p in enumerate(pts):
            prev = self._smooth[i]
            if p is None:
                sm.append(None)
                continue
            if prev is None or dt > 0.5:
                q = p
            else:
                q = (prev[0] + alpha * (p[0] - prev[0]), prev[1] + alpha * (p[1] - prev[1]))
            sm.append(q)
        self._smooth = sm

        # Mid-points of left/right pairs. When the pose model drops one side
        # (very common when lying sideways), naive averaging jumps by half a
        # hip-width — which looks like a fast drop. Impute the missing side
        # from the last seen left→right offset instead.
        sho = self._pair_mid("sho", sm[L_SHO], sm[R_SHO])
        hip = self._pair_mid("hip", sm[L_HIP], sm[R_HIP])
        if sho is None or hip is None:
            return None
        valid = [p for p in sm if p is not None]
        if len(valid) < 5:
            return None

        head = _mean_pt([sm[i] for i in HEAD_IDX if sm[i]]) or sho
        ank = self._pair_mid("ank", sm[L_ANK], sm[R_ANK])
        ys = [p[1] for p in valid]
        xs = [p[0] for p in valid]
        ext_h = max(ys) - min(ys)
        ext_w = max(xs) - min(xs)

        dx, dy = sho[0] - hip[0], sho[1] - hip[1]
        torso = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(abs(dx), -dy))  # 0 upright, 90 horizontal, 180 inverted

        # Calibrate standing references only while clearly STANDING: torso
        # vertical, body tall and narrow, feet visible and legs extended
        # (hip→ankle is a large share of the body — false when seated).
        standing_geom = (angle < 25 and ank is not None and ext_h > 1.3 * max(ext_w, 1e-6)
                         and (ank[1] - hip[1]) > 0.45 * ext_h)
        if standing_geom:
            if self.h_ref is None:
                self.h_ref, self.torso_ref, self.floor_y = ext_h, torso, ank[1]
            else:
                ddt = max(dt, 1e-3)
                # grow fast (walked closer), shrink slowly (robust to the start of a fall)
                tau = 0.5 if ext_h > self.h_ref else 5.0
                a = 1.0 - math.exp(-ddt / tau)
                self.h_ref += a * (ext_h - self.h_ref)
                self.torso_ref += a * (torso - self.torso_ref)
                af = 1.0 - math.exp(-ddt / 0.4)
                self.floor_y += af * (ank[1] - self.floor_y)

        h_ref = self.h_ref
        if h_ref is None:
            # never seen standing: estimate from torso (torso ≈ 0.3 of keypoint height)
            h_ref = max(torso * 3.2, ext_h, 1.0)
        floor_y = self.floor_y if self.floor_y is not None else max(ys)

        head_h = (floor_y - head[1]) / h_ref
        hip_h = (floor_y - hip[1]) / h_ref
        extent = ext_h / h_ref

        if self.h_ref is not None:
            # strict: physically at floor level (hips on the floor, or lying with
            # hips low — a bed/sofa keeps the hips well above HIP_LYING_MAX)
            on_floor = (hip_h < HIP_ON_FLOOR or
                        (head_h < HEAD_LOW and angle > LYING_ANGLE and hip_h < HIP_LYING_MAX))
            # loose: also accept a collapsed body (lying along the camera axis
            # foreshortens the body, so angle alone is unreliable)
            on_ground = on_floor or (extent < EXTENT_COLLAPSED and head_h < HEAD_LOWISH)
        else:
            # uncalibrated (person first seen already low): rely on body shape
            on_floor = on_ground = angle > 60 and ext_w > 1.2 * ext_h
        upright = angle < UPRIGHT_ANGLE and head_h > UPRIGHT_HEAD and not on_ground

        sample = _Sample(t=t, head_h=head_h, hip_h=hip_h, angle=angle, extent=extent,
                         on_ground=on_ground, on_floor=on_floor, upright=upright, kps=sm, hip_xy=hip)
        return {"sample": sample, "head": head, "hip": hip, "torso": torso,
                "calibrated": self.h_ref is not None}

    def _pair_mid(self, key, a, b):
        if a and b:
            self._pair_off[key] = (b[0] - a[0], b[1] - a[1])
            return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        off = self._pair_off.get(key)
        if a and off:
            return (a[0] + off[0] / 2, a[1] + off[1] / 2)
        if b and off:
            return (b[0] - off[0] / 2, b[1] - off[1] / 2)
        return a or b

    def _in_bed(self, hip_xy, frame_size) -> bool:
        if not self.bed_zones or not frame_size:
            return False
        w, h = frame_size
        if not w or not h:
            return False
        nx, ny = hip_xy[0] / w, hip_xy[1] / h
        return any(point_in_polygon(nx, ny, z) for z in self.bed_zones)

    def _motion(self, t) -> Optional[float]:
        """
        Body motion in torso-lengths per second: compare the AVERAGE pose of
        the last 0.5 s with the average pose 1.0-1.5 s ago. Averaging first
        suppresses pose-estimator jitter, so a motionless person reads ~0
        even with noisy keypoints.
        """
        if not self.history or t - self.history[0].t < 1.4:
            return None
        recent = [s for s in self.history if t - s.t <= 0.5]
        past = [s for s in self.history if 1.0 <= t - s.t <= 1.5]
        if len(recent) < 2 or len(past) < 2:
            return None

        def avg(group, i):
            pts = [g.kps[i] for g in group if g.kps[i] is not None]
            return _mean_pt(pts) if len(pts) >= max(1, len(group) // 2) else None

        ref = self.torso_ref or 1.0
        d = []
        for i in range(17):
            a, b = avg(recent, i), avg(past, i)
            if a and b:
                d.append(math.hypot(a[0] - b[0], a[1] - b[1]))
        if len(d) < 4:
            return None
        return (sum(d) / len(d)) / ref

    def _window(self, t, span) -> List[_Sample]:
        return [s for s in self.history if t - s.t <= span]

    def _peak_down_speed(self, samples: List[_Sample], attr: str) -> float:
        """Max downward speed (heights/s) using pairs at least VEL_MIN_DT apart."""
        best = 0.0
        for i in range(len(samples)):
            # find the nearest earlier sample that is >= VEL_MIN_DT away
            k = i - 1
            while k >= 0 and samples[i].t - samples[k].t < VEL_MIN_DT:
                k -= 1
            if k < 0:
                continue
            gap = samples[i].t - samples[k].t
            if gap <= 0 or gap > 0.6:
                continue
            v = (getattr(samples[k], attr) - getattr(samples[i], attr)) / gap
            best = max(best, v)
        return best

    # ── state handlers ──────────────────────────────────────────────────────
    def _step_normal(self, t, s: _Sample, in_bed, lstm_prob, events):
        if t < self.cooldown_until:
            return
        win = self._window(t, DESCENT_WINDOW_S)
        if len(win) >= 3:
            peak_head = max(win, key=lambda x: x.head_h)
            head_drop = peak_head.head_h - s.head_h
            v_head = self._peak_down_speed([x for x in win if x.t >= peak_head.t], "head_h")
            v_hip = self._peak_down_speed([x for x in win if x.t >= peak_head.t], "hip_h")
            v = max(v_head, v_hip)
            if v >= self.cfg["v_fast"] and head_drop >= self.cfg["drop_fast"]:
                # the drop really began at the last moment the head was still near its peak
                t0 = max(x.t for x in win if x.head_h >= peak_head.head_h - 0.05)
                self.candidate = _Candidate(
                    kind="fast", t_start=t0, peak_v=v, head_drop=head_drop,
                    hip_drop=max(0.0, peak_head.hip_h - s.hip_h),
                    angle_before=min(x.angle for x in win if x.t <= peak_head.t + 1e-9),
                    start_head_h=peak_head.head_h,
                    lstm_max=float(lstm_prob or 0.0))
                self.state = DESCENT
                self._step_descent(t, s, events)
                return

        # Lying down inside a marked bed / sofa zone is rest
        if in_bed and (s.on_ground or s.angle > LYING_ANGLE):
            self.state = LYING_IN_BED
            return

        # Slow path: on the floor now (for at least 0.5 s, so a single noisy
        # frame can't start it), but was standing/sitting recently
        if s.on_floor and not in_bed and self.floor_since is not None and t - self.floor_since >= 0.5:
            slow = self._window(t, SLOW_WINDOW_S)
            prior = [x for x in slow if not x.on_ground and x.head_h >= 0.55]
            if prior:
                top = max(prior, key=lambda x: x.head_h)
                self.candidate = _Candidate(
                    kind="slow", t_start=top.t, t_low=t,
                    peak_v=self._peak_down_speed([x for x in slow if x.t >= top.t], "head_h"),
                    head_drop=top.head_h - s.head_h,
                    hip_drop=max(0.0, top.hip_h - s.hip_h),
                    angle_before=top.angle, start_head_h=top.head_h,
                    lstm_max=float(lstm_prob or 0.0))
                self.candidate.descent_s = t - top.t
                self.state = ON_GROUND_CHECK
                self._step_ground_check(t, s, in_bed, events)
                return
            # On the floor with no history of being up (came into view / camera started)
            if self.floor_since is not None and t - self.floor_since >= self.cfg["slow_floor_s"]:
                self.candidate = _Candidate(kind="found", t_start=self.floor_since, t_low=self.floor_since,
                                            angle_before=s.angle, start_head_h=s.head_h,
                                            lstm_max=float(lstm_prob or 0.0))
                self._confirm(t, s, events, fall_type="found_on_floor")

    def _step_descent(self, t, s: _Sample, events):
        c = self.candidate
        if c is None:
            self.state = NORMAL
            return
        # keep the strongest kinematics seen during the descent
        win = [x for x in self.history if x.t >= c.t_start]
        c.peak_v = max(c.peak_v, self._peak_down_speed(win, "head_h"), self._peak_down_speed(win, "hip_h"))
        c.head_drop = max(c.head_drop, c.start_head_h - s.head_h)
        if s.on_ground:
            c.t_low = t
            c.descent_s = max(0.05, t - c.t_start)
            self.state = ON_GROUND_CHECK
            return
        if t - c.t_start > DESCENT_TIMEOUT_S:
            reason = "sat down / bent over (did not end on the floor)"
            events.append(self._event(EV_REJECTED, t, s, extra={"reason": reason}))
            self.candidate = None
            self.state = NORMAL

    def _step_ground_check(self, t, s: _Sample, in_bed, events):
        c = self.candidate
        if c is None:
            self.state = NORMAL
            return
        c.total_frames += 1
        if s.on_ground:
            c.ground_frames += 1
        if s.on_floor:
            c.floor_frames += 1
        c.angle_after = max(c.angle_after, s.angle)
        c.head_drop = max(c.head_drop, c.start_head_h - s.head_h)

        if in_bed and c.peak_v < 1.6:
            events.append(self._event(EV_REJECTED, t, s, extra={"reason": "lying down in a bed / sofa zone"}))
            self.candidate = None
            self.state = LYING_IN_BED
            return

        if s.upright and self.upright_since is not None and t - self.upright_since >= 0.5:
            events.append(self._event(EV_REJECTED, t, s, extra={"reason": "got straight back up (squat / bend / kneel)"}))
            self.candidate = None
            self.state = NORMAL
            return

        t_low = c.t_low if c.t_low is not None else t
        need = self.cfg["confirm_s"] * (2.0 if c.kind == "slow" else 1.0)
        if t - t_low >= need:
            frac = c.ground_frames / max(1, c.total_frames)
            # A collapsed-looking body that never reaches floor level (e.g. lying
            # down on a bed) needs a genuinely violent descent to count.
            if c.kind == "slow":
                # slow descents must be genuinely at floor level most of the time
                floor_ok = c.floor_frames / max(1, c.total_frames) >= 0.6
            else:
                floor_ok = c.floor_frames > 0 or c.peak_v >= 1.3 * self.cfg["v_fast"]
            if frac >= 0.6 and floor_ok:
                self._confirm(t, s, events, fall_type=None)
            else:
                why = "not consistently on the ground" if frac < 0.6 else "lying down above floor level (bed / sofa?)"
                events.append(self._event(EV_REJECTED, t, s, extra={"reason": why}))
                self.candidate = None
                self.state = NORMAL

    def _step_fallen(self, t, s: _Sample, events):
        if s.upright and self.upright_since is not None and t - self.upright_since >= RECOVER_HOLD_S:
            on_ground = (t - RECOVER_HOLD_S) - (self.fall_t if self.fall_t is not None else t)
            ev = self._event(EV_RECOVERED, t, s, extra={
                "time_on_ground_s": round(max(0.0, on_ground), 1),
                "related_event_id": (self.fall_event or {}).get("event_id"),
                "explanation": f"Person got back up after about {max(0.0, on_ground):.0f} s on the ground.",
            })
            events.append(ev)
            self.state = NORMAL
            self.candidate = None
            self.fall_event = None
            self.cooldown_until = t + COOLDOWN_S
            return
        if (self.state == FALL_CONFIRMED and not self.long_lie_fired and self.still_since is not None
                and t - self.still_since >= self.cfg["long_lie_s"]):
            self.long_lie_fired = True
            self.state = LONG_LIE
            still_for = t - self.still_since
            events.append(self._event(EV_LONG_LIE, t, s, extra={
                "severity": "critical",
                "still_for_s": round(still_for, 1),
                "time_on_ground_s": round(t - (self.fall_t if self.fall_t is not None else t), 1),
                "related_event_id": (self.fall_event or {}).get("event_id"),
                "explanation": f"Still on the floor and barely moving for {still_for:.0f} s after the fall.",
            }))
        elif self.state == LONG_LIE and self.still_since is None:
            # moving again but still down — keep monitoring, allow re-fire later
            self.state = FALL_CONFIRMED
            self.long_lie_fired = False

    def _on_lost(self, t, events):
        if self.last_seen_t is None:
            self.state = NO_PERSON
            return
        gone = t - self.last_seen_t
        if self.state == DESCENT and gone >= LOST_DURING_DESCENT_S and self.candidate is not None:
            s = self.history[-1] if self.history else None
            if s is not None and self.candidate.peak_v >= self.cfg["v_fast"]:
                self.candidate.t_low = self.last_seen_t
                self._confirm(t, s, events, fall_type="out_of_view")
            else:
                self.candidate = None
                self.state = NO_PERSON
            return
        # Vanished while dropping fast (e.g. behind a bed or sofa) — before the
        # drop was large enough to start a DESCENT. Walking out of view keeps
        # the head level, so it never matches this.
        if (self.state == NORMAL and gone >= LOST_DURING_DESCENT_S and not self._lost_checked
                and self.history and t >= self.cooldown_until):
            self._lost_checked = True
            last = self.history[-1]
            win = [x for x in self.history if last.t - x.t <= 1.0]
            if len(win) >= 3:
                top = max(win, key=lambda x: x.head_h)
                after = [x for x in win if x.t >= top.t]
                v = max(self._peak_down_speed(after, "head_h"), self._peak_down_speed(after, "hip_h"))
                drop = top.head_h - last.head_h
                if v >= self.cfg["v_fast"] and drop >= 0.12 and top.upright:
                    t0 = max(x.t for x in win if x.head_h >= top.head_h - 0.05)
                    self.candidate = _Candidate(kind="fast", t_start=t0, t_low=self.last_seen_t,
                                                peak_v=v, head_drop=drop, angle_before=top.angle,
                                                angle_after=last.angle, start_head_h=top.head_h,
                                                descent_s=last.t - t0)
                    self._confirm(t, last, events, fall_type="out_of_view")
                    return
        if self.state in (FALL_CONFIRMED, LONG_LIE):
            return  # occluded while down — keep the alarm state
        # Went down, was seen on the ground, then slid / rolled out of view (or got
        # hidden by furniture) before the confirmation time ran out. Found on real
        # footage: a person lying at the edge of the frame drops out of the pose
        # model. Not seeing them get up is exactly when we must alert.
        c = self.candidate
        if (self.state == ON_GROUND_CHECK and c is not None and c.ground_frames > 0 and c.t_low is not None
                and t - c.t_low >= self.cfg["confirm_s"] and gone >= LOST_DURING_DESCENT_S):
            s = self.history[-1] if self.history else None
            if s is not None:
                self._confirm(t, s, events, fall_type="out_of_view" if c.kind == "fast" else "slow_collapse")
                return
        if gone >= LOST_RESET_S and self.state in (NORMAL, ON_GROUND_CHECK, LYING_IN_BED):
            self.state = NO_PERSON
            self.candidate = None
            self.history.clear()

    # ── confirmation & scoring ──────────────────────────────────────────────
    def _score(self, c: _Candidate, s: _Sample, ground_frac: float) -> Tuple[float, List[dict]]:
        rot = max(0.0, max(c.angle_after, s.angle) - c.angle_before)
        comps = [
            ("speed",    0.25, _clip01((c.peak_v - 0.4) / 1.0)),
            ("drop",     0.25, _clip01((c.head_drop - 0.2) / 0.5)),
            ("rotation", 0.15, _clip01((rot - 15.0) / 60.0)),
            ("ground",   0.25, _clip01(ground_frac)),
        ]
        if c.lstm_max > 0:
            comps.append(("learned_model", 0.10, _clip01(c.lstm_max)))
        tot_w = sum(w for _, w, _ in comps)
        score = sum(w * v for _, w, v in comps) / tot_w
        return score, [{"signal": n, "weight": round(w / tot_w, 2), "score": round(v, 2)} for n, w, v in comps]

    def _confirm(self, t, s: _Sample, events, fall_type: Optional[str]):
        c = self.candidate
        ground_frac = (c.ground_frames / c.total_frames) if c and c.total_frames else (1.0 if s.on_ground else 0.0)
        if fall_type == "out_of_view":
            ground_frac = 0.5   # unknown: hidden from the camera after a fast drop
        score, comps = self._score(c, s, ground_frac)
        if fall_type is None:
            if c.kind == "fast":
                fall_type = "hard_fall" if (c.peak_v >= 1.2 and c.descent_s <= 1.2) else "fall"
            else:
                fall_type = "slow_collapse"
        if fall_type == "out_of_view":
            severity = "high"   # we can no longer see them after a fast drop — treat as serious
        else:
            severity = "high" if fall_type in ("hard_fall", "fall") and score >= self.cfg["min_score"] else "medium"
        rot = max(0.0, max(c.angle_after, s.angle) - c.angle_before)

        evidence = []
        if c.kind != "found":
            evidence.append({"signal": "head_drop", "value": round(c.head_drop, 2), "unit": "of standing height",
                             "threshold": self.cfg["drop_fast"], "passed": c.head_drop >= self.cfg["drop_fast"],
                             "text": f"Head dropped {c.head_drop*100:.0f}% of standing height"
                                     + (f" in {c.descent_s:.1f} s" if c.descent_s else "")})
            evidence.append({"signal": "peak_speed", "value": round(c.peak_v, 2), "unit": "standing-heights/s",
                             "threshold": self.cfg["v_fast"], "passed": c.peak_v >= self.cfg["v_fast"],
                             "text": f"Peak downward speed {c.peak_v:.2f} body-heights/s"
                                     + (" (fast, uncontrolled)" if c.peak_v >= self.cfg["v_fast"] else " (slow)")})
            evidence.append({"signal": "torso_rotation", "value": round(rot, 1), "unit": "degrees",
                             "threshold": 30, "passed": rot >= 30,
                             "text": f"Torso rotated {rot:.0f}° (now {s.angle:.0f}° from vertical)"})
        if fall_type == "out_of_view":
            evidence.append({"signal": "lost_from_view", "value": round(t - (c.t_low if c.t_low is not None else t), 1), "unit": "s",
                             "threshold": LOST_DURING_DESCENT_S, "passed": True,
                             "text": ("Reached the floor, then left the camera's view without getting up"
                                      if c.ground_frames > 0 else
                                      "Person disappeared from view mid-fall and has not reappeared")})
        evidence.append({"signal": "on_ground", "value": round(s.hip_h, 2), "unit": "hip height / standing height",
                         "threshold": HIP_ON_FLOOR, "passed": s.on_ground,
                         "text": (f"Body is at floor level (hips at {max(0.0, s.hip_h)*100:.0f}% of standing height)"
                                  if s.on_floor else
                                  f"Body is low and collapsed (head at {max(0.0, s.head_h)*100:.0f}% of standing height)")})
        held = t - (c.t_low if c.t_low is not None else t)
        evidence.append({"signal": "stayed_down", "value": round(held, 1), "unit": "s",
                         "threshold": self.cfg["confirm_s"], "passed": held >= self.cfg["confirm_s"] or c.kind == "found",
                         "text": f"Stayed on the ground for {held:.1f} s (did not get straight back up)"})
        if c.lstm_max > 0:
            evidence.append({"signal": "learned_model", "value": round(c.lstm_max, 2), "unit": "probability",
                             "threshold": 0.5, "passed": c.lstm_max >= 0.5,
                             "text": f"Pose-sequence model (BiGRU) fall probability {c.lstm_max:.2f}"})

        phrases = {
            "hard_fall": "Hard fall",
            "fall": "Fall",
            "slow_collapse": "Slow collapse / slid to the floor",
            "out_of_view": "Fall that continued out of the camera's view",
            "found_on_floor": "Person found lying on the floor",
        }
        main = [e["text"] for e in evidence if e["passed"]][:4]
        explanation = f"{phrases.get(fall_type, 'Fall')}: " + "; ".join(main) + "."

        ev = self._event(EV_FALL, t, s, extra={
            "fall_type": fall_type,
            "severity": severity,
            "confidence": round(score, 2),
            "score_breakdown": comps,
            "evidence": evidence,
            "explanation": explanation,
            "descent_s": round(c.descent_s, 2),
        })
        events.append(ev)
        self.fall_event = ev
        self.fall_t = c.t_low if c.t_low is not None else t
        self.long_lie_fired = False
        self.state = FALL_CONFIRMED
        self.candidate = None

    def _event(self, etype, t, s: _Sample, extra=None) -> dict:
        self.event_counter += 1
        ev = {"event_id": self.event_counter, "type": etype, "t": round(t, 3),
              "state": self.state, "position": [round(s.hip_xy[0], 1), round(s.hip_xy[1], 1)]}
        if extra:
            ev.update(extra)
        return ev

    # ── output ──────────────────────────────────────────────────────────────
    def _result(self, t, obs, events, lstm_prob) -> dict:
        s: Optional[_Sample] = obs["sample"] if obs else None
        fallen = self.state in (FALL_CONFIRMED, LONG_LIE)
        live = {}
        if s is not None:
            live = {
                "head_height": round(s.head_h, 2),
                "hip_height": round(s.hip_h, 2),
                "torso_angle": round(s.angle, 1),
                "extent": round(s.extent, 2),
                "on_ground": s.on_ground,
                "upright": s.upright,
                "motion": None if obs.get("motion") is None else round(obs["motion"], 3),
                "in_bed_zone": bool(obs.get("in_bed")),
                "calibrated": bool(obs.get("calibrated")),
            }
            if lstm_prob is not None:
                live["lstm_prob"] = round(float(lstm_prob), 3)
        return {
            "state": self.state,
            "fall_active": fallen,
            "events": events,
            "fall_event": self.fall_event if fallen else None,
            "time_on_ground_s": round(t - self.fall_t, 1) if fallen and self.fall_t is not None else 0.0,
            "live": live,
        }
