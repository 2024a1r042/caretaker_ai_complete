"""
fall_scenarios.py — Synthetic pose sequences for testing the fall engine.

Generates COCO-17 keypoints for scripted activities by posing a simple 3D
skeleton and projecting it through a pinhole camera, then adding pose-
estimator noise (pixel jitter, dropped keypoints, dropped frames).

This is a *test bench*, not a substitute for real-video evaluation: it lets
us check every branch of the state machine (falls vs. everyday look-alikes
like sitting, bending, squatting, lying in bed) at different frame-rates,
camera distances and noise levels, deterministically, in seconds.
For real-world numbers use evaluate_on_videos.py with a labelled dataset
(e.g. UR Fall Detection, Le2i, or your own recordings).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]

# Segment lengths (metres) for a ~1.6 m person
TORSO, NECK_HEAD, THIGH, SHIN, ANKLE_H = 0.50, 0.20, 0.42, 0.40, 0.07
HIP_W, SHO_W = 0.13, 0.18
UP: Vec = (0.0, 1.0, 0.0)


def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _norm(a): return math.sqrt(_dot(a, a))
def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else (0.0, 0.0, 0.0)


def _rotate(v: Vec, axis: Vec, ang: float) -> Vec:
    k = _unit(axis)
    if _norm(k) < 1e-9:
        return v
    c, s = math.cos(ang), math.sin(ang)
    return _add(_add(_mul(v, c), _mul(_cross(k, v), s)), _mul(k, _dot(k, v) * (1 - c)))


@dataclass
class Pose:
    pelvis: Vec                  # world position of mid-hip (x lateral, y up, z depth from person origin)
    theta: float = 0.0           # torso tilt from vertical, degrees
    fall_dir: Vec = (0, 0, 1)    # horizontal direction the torso tilts toward
    facing: Vec = (0, 0, -1)     # where the person faces (camera is at -z)
    ankles: Optional[Vec] = None # mid-ankle world position (None → directly below pelvis)
    legs_follow: bool = False    # True when lying: legs extend opposite the torso


def skeleton(p: Pose) -> List[Vec]:
    g = _unit((p.fall_dir[0], 0.0, p.fall_dir[2]))
    axis = _cross(UP, g) if _norm(g) > 0 else (1, 0, 0)
    th = math.radians(p.theta)
    u = _rotate(UP, axis, th)                       # torso direction
    face = _unit((p.facing[0], 0.0, p.facing[2]))
    lat0 = _cross(UP, face)                         # body's lateral axis when upright
    w = _unit(_rotate(lat0, axis, th))
    f = _unit(_rotate(face, axis, th))
    P = p.pelvis

    hips = [_add(P, _mul(w, HIP_W)), _add(P, _mul(w, -HIP_W))]
    sho_c = _add(P, _mul(u, TORSO))
    shos = [_add(sho_c, _mul(w, SHO_W)), _add(sho_c, _mul(w, -SHO_W))]
    nose = _add(_add(P, _mul(u, TORSO + NECK_HEAD)), _mul(f, 0.08))
    eyes = [_add(_add(nose, _mul(u, 0.03)), _mul(w, s * 0.03)) for s in (1, -1)]
    ears = [_add(_add(P, _mul(u, TORSO + NECK_HEAD - 0.02)), _mul(w, s * 0.07)) for s in (1, -1)]
    elbows = [_add(_add(s, _mul(u, -0.27)), _mul(f, 0.05)) for s in shos]
    wrists = [_add(_add(e, _mul(u, -0.25)), _mul(f, 0.08)) for e in elbows]

    # legs: two-link IK from each hip to its ankle, knees bend toward `face`
    leg_len = THIGH + SHIN
    if p.legs_follow:
        ankle_c = _add(P, _mul(u, -(leg_len)))
        ankle_c = (ankle_c[0], max(ankle_c[1], ANKLE_H), ankle_c[2])
    elif p.ankles is not None:
        ankle_c = p.ankles
    else:
        ankle_c = (P[0], ANKLE_H, P[2])
    knees, ankles = [], []
    for side, hip in zip((1, -1), hips):
        a = _add(ankle_c, _mul(w if p.legs_follow else lat0, side * HIP_W * 0.8))
        d = _sub(a, hip)
        dist = _norm(d)
        if dist >= leg_len - 1e-6:
            dirv = _unit(d)
            knee = _add(hip, _mul(dirv, THIGH))
            ank = _add(hip, _mul(dirv, leg_len))
        else:
            # knee height above the hip→ankle line (law of cosines)
            x = (THIGH ** 2 - SHIN ** 2 + dist ** 2) / (2 * dist)
            h = math.sqrt(max(0.0, THIGH ** 2 - x ** 2))
            dirv = _unit(d)
            bend = _sub(face, _mul(dirv, _dot(face, dirv)))
            bend = _unit(bend) if _norm(bend) > 1e-6 else _unit(_cross(dirv, lat0))
            knee = _add(_add(hip, _mul(dirv, x)), _mul(bend, h))
            ank = a
        knees.append(knee)
        ankles.append(ank)

    # COCO order
    return [nose, eyes[0], eyes[1], ears[0], ears[1],
            shos[0], shos[1], elbows[0], elbows[1], wrists[0], wrists[1],
            hips[0], hips[1], knees[0], knees[1], ankles[0], ankles[1]]


@dataclass
class Camera:
    distance: float = 4.0        # metres from person origin
    height: float = 1.3          # camera height
    focal: float = 520.0
    width: int = 640
    height_px: int = 480

    def project(self, pts: Sequence[Vec]) -> List[Tuple[float, float]]:
        out = []
        cx, cy = self.width / 2, self.height_px / 2
        for x, y, z in pts:
            depth = max(0.3, self.distance + z)
            out.append((cx + self.focal * x / depth, cy - self.focal * (y - self.height) / depth))
        return out


# ── easing helpers ───────────────────────────────────────────────────────────
def lerp(a, b, k): return a + (b - a) * k
def vlerp(a, b, k): return (lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k))
def smooth(k): k = min(1, max(0, k)); return k * k * (3 - 2 * k)
def gravity(k): k = min(1, max(0, k)); return k * k        # accelerating, like a real fall


STAND_H = THIGH + SHIN + ANKLE_H   # pelvis height when standing (≈0.89)


@dataclass
class Scenario:
    name: str
    expect: str                    # none | fall | fall+recovered | fall+long_lie | check_in
    duration: float
    pose_at: Callable[[float], Optional[Pose]]
    description: str = ""
    bed_zones: list = field(default_factory=list)
    impact_t: Optional[float] = None   # when the body reaches the floor (for latency)
    camera_side: bool = False          # True → camera looks at the person's side


def _standing(x=0.0, z=0.0, theta=3.0) -> Pose:
    return Pose(pelvis=(x, STAND_H, z), theta=theta)


def build_scenarios() -> List[Scenario]:
    S: List[Scenario] = []

    def walk(t):
        x = -1.2 + 0.8 * t
        bob = 0.015 * math.sin(t * 2 * math.pi * 1.8)
        return Pose(pelvis=(x, STAND_H + bob, 0.0), theta=4.0, facing=(1, 0, 0))
    S.append(Scenario("walk_across", "none", 3.0, walk, "Walks across the room"))

    def sit(dur):
        def f(t):
            if t < 2: return _standing()
            k = smooth((t - 2) / dur)
            return Pose(pelvis=(0, lerp(STAND_H, 0.47, k), lerp(0, 0.30, k)), theta=lerp(3, 12, k),
                        ankles=(0, ANKLE_H, 0))
        return f
    S.append(Scenario("sit_down_chair", "none", 8.0, sit(1.4), "Sits down on a chair normally"))
    S.append(Scenario("sit_down_fast", "none", 8.0, sit(0.45), "Drops quickly into a chair"))

    def low_sofa(t):
        if t < 2: return _standing()
        k = gravity((t - 2) / 0.5) if t < 2.5 else 1
        return Pose(pelvis=(0, lerp(STAND_H, 0.36, k), lerp(0, 0.35, k)), theta=lerp(3, 20, k),
                    ankles=(0, ANKLE_H, 0))
    S.append(Scenario("plop_low_sofa", "none", 8.0, low_sofa, "Flops onto a low sofa"))

    def bend(t):
        if t < 2: return _standing()
        if t < 2.8: k = smooth((t - 2) / 0.8)
        elif t < 4.8: k = 1
        else: k = 1 - smooth((t - 4.8) / 0.8)
        return Pose(pelvis=(0, lerp(STAND_H, 0.80, k), lerp(0, 0.12, k)), theta=lerp(3, 85, k),
                    fall_dir=(0, 0, -1), ankles=(0, ANKLE_H, 0))
    S.append(Scenario("bend_pick_up", "none", 7.0, bend, "Bends down to pick something up"))

    def squat(t):
        if t < 2: return _standing()
        if t < 2.7: k = smooth((t - 2) / 0.7)
        elif t < 3.7: k = 1
        else: k = 1 - smooth((t - 3.7) / 0.7)
        return Pose(pelvis=(0, lerp(STAND_H, 0.40, k), lerp(0, 0.18, k)), theta=lerp(3, 25, k),
                    fall_dir=(0, 0, -1), ankles=(0, ANKLE_H, 0))
    S.append(Scenario("squat", "none", 6.0, squat, "Squats and stands up"))

    def kneel(t):
        if t < 2: return _standing()
        k = smooth((t - 2) / 1.5)
        return Pose(pelvis=(0, lerp(STAND_H, 0.50, k), 0), theta=lerp(3, 8, k), ankles=(0, ANKLE_H, 0.3 * k))
    S.append(Scenario("kneel_to_pray", "none", 14.0, kneel, "Kneels on the floor (prayer)"))

    def lie_bed(t):
        if t < 2: return _standing(x=-0.3)
        if t < 3.5:
            k = smooth((t - 2) / 1.5)
            return Pose(pelvis=(lerp(-0.3, 0, k), lerp(STAND_H, 0.55, k), 0), theta=3, ankles=(-0.3, ANKLE_H, 0))
        k = smooth((t - 3.5) / 3.0)
        return Pose(pelvis=(0, 0.55, 0), theta=lerp(3, 88, k), fall_dir=(1, 0, 0),
                    legs_follow=k > 0.6, ankles=(-0.3, ANKLE_H, 0))
    bed = [[(0.35, 0.35), (1.0, 0.35), (1.0, 0.95), (0.35, 0.95)]]
    S.append(Scenario("lie_down_in_bed_zone", "none", 20.0, lie_bed, "Lies down on a bed marked as a bed zone", bed_zones=bed))
    S.append(Scenario("lie_down_in_bed_no_zone", "none", 20.0, lie_bed, "Lies down on a bed (no zone configured)"))

    def fall(direction=(0, 0, 1), dur=0.75, stay=8.0, recover_at=None, still=False, facing=(0, 0, -1)):
        def f(t):
            t0 = 2.0
            if t < t0: return Pose(pelvis=(0, STAND_H, 0), theta=3, facing=facing)
            g = _unit((direction[0], 0, direction[2]))
            end_p = (g[0] * 0.55, 0.12, g[2] * 0.55)
            if t < t0 + dur:
                k = gravity((t - t0) / dur)
                return Pose(pelvis=vlerp((0, STAND_H, 0), end_p, k), theta=lerp(3, 88, k), fall_dir=direction,
                            facing=facing, legs_follow=k > 0.7, ankles=(0, ANKLE_H, 0))
            if recover_at is not None and t >= recover_at:
                k = smooth((t - recover_at) / 3.0)
                return Pose(pelvis=vlerp(end_p, (0, STAND_H, 0), k), theta=lerp(88, 3, k), fall_dir=direction,
                            facing=facing, legs_follow=k < 0.3, ankles=(0, ANKLE_H, 0))
            wobble = 0.0 if still else 0.03 * math.sin(t * 3.1)
            return Pose(pelvis=(end_p[0] + wobble, end_p[1], end_p[2]), theta=88 + 4 * wobble * 10,
                        fall_dir=direction, facing=facing, legs_follow=True)
        return f
    S.append(Scenario("fall_sideways", "fall", 10.0, fall(direction=(1, 0, 0)), "Hard fall to the side", impact_t=2.75))
    S.append(Scenario("fall_forward_toward_camera", "fall", 10.0, fall(direction=(0, 0, -1)),
                      "Falls forward toward the camera (heavy foreshortening)", impact_t=2.75))
    S.append(Scenario("fall_backward_away", "fall", 10.0, fall(direction=(0, 0, 1)),
                      "Falls backward away from the camera", impact_t=2.75))
    S.append(Scenario("fall_then_gets_up", "fall+recovered", 16.0, fall(direction=(1, 0, 0), recover_at=8.0),
                      "Falls, lies 5 s, gets up unaided", impact_t=2.75))
    S.append(Scenario("fall_long_lie", "fall+long_lie", 40.0, fall(direction=(1, 0, 0), stay=38, still=True),
                      "Falls and lies motionless", impact_t=2.75))

    def slip_sit(t):
        if t < 2: return _standing()
        k = gravity((t - 2) / 0.5) if t < 2.5 else 1
        return Pose(pelvis=(0, lerp(STAND_H, 0.12, k), lerp(0, -0.25, k)), theta=lerp(3, 30, k),
                    fall_dir=(0, 0, 1), ankles=(0, ANKLE_H, -0.55 * k))
    S.append(Scenario("slip_onto_bottom", "fall", 10.0, slip_sit, "Slips and lands sitting on the floor", impact_t=2.5))

    def slide_chair(t):
        if t < 4: return Pose(pelvis=(0, 0.47, 0.3), theta=12, ankles=(0, ANKLE_H, 0))
        k = smooth((t - 4) / 2.5)
        return Pose(pelvis=(0, lerp(0.47, 0.11, k), lerp(0.3, 0.1, k)), theta=lerp(12, 55, k),
                    fall_dir=(0, 0, 1), ankles=(0, ANKLE_H, lerp(0, -0.5, k)))
    # standing first so the engine is calibrated, then sits, then slides off
    def slide_chair_full(t):
        if t < 2: return _standing()
        if t < 3.5:
            return sit(1.4)(t)
        return slide_chair(t + 0.5)
    S.append(Scenario("slide_off_chair", "check_in", 18.0, slide_chair_full,
                      "Slowly slides off a chair onto the floor", impact_t=6.5))

    def lie_floor_slow(t):
        if t < 2: return _standing()
        if t < 5:
            k = smooth((t - 2) / 3)
            return Pose(pelvis=(0, lerp(STAND_H, 0.12, k), 0), theta=lerp(3, 20, k), ankles=(0, ANKLE_H, -0.4 * k))
        k = smooth((t - 5) / 2)
        return Pose(pelvis=(0, 0.12, 0), theta=lerp(20, 88, k), fall_dir=(1, 0, 0), legs_follow=k > 0.5,
                    ankles=(0, ANKLE_H, -0.4))
    S.append(Scenario("lie_on_floor_deliberately", "check_in", 18.0, lie_floor_slow,
                      "Gets down onto the floor slowly (exercise) — worth a gentle check-in"))

    def out_of_view(t):
        if t >= 2.55: return None         # hidden once the body drops below the bed / sofa edge
        return fall(direction=(1, 0, 0))(t)
    S.append(Scenario("fall_behind_furniture", "fall", 8.0, out_of_view,
                      "Falls; body disappears behind a bed/sofa halfway down", impact_t=2.75))

    def walk_out(t):
        x = 0.0 + 1.2 * t
        if x > 2.6: return None
        return Pose(pelvis=(x, STAND_H, 0), theta=4, facing=(1, 0, 0))
    S.append(Scenario("walk_out_of_frame", "none", 6.0, walk_out, "Walks out of the camera view"))

    def found(t):
        return Pose(pelvis=(0, 0.12, 0.2), theta=88, fall_dir=(1, 0, 0), legs_follow=True)
    S.append(Scenario("found_on_floor", "check_in", 25.0, found,
                      "Camera starts with the person already lying on the floor"))
    return S


def render(scn: Scenario, fps: float = 15.0, distance: float = 4.0, noise_px: float = 1.5,
           drop_kp: float = 0.03, drop_frame: float = 0.02, seed: int = 0):
    """Yields (t, kps_xy or None, kps_conf or None, frame_size)."""
    rng = random.Random(seed)
    cam = Camera(distance=distance)
    n = int(scn.duration * fps)
    for i in range(n):
        t = i / fps
        if rng.random() < drop_frame:
            continue
        pose = scn.pose_at(t)
        if pose is None:
            yield t, None, None, (cam.width, cam.height_px)
            continue
        pts = cam.project(skeleton(pose))
        xy, conf = [], []
        for (x, y) in pts:
            jit = noise_px * (520.0 / cam.focal) * (4.0 / distance)
            xy.append((x + rng.gauss(0, jit), y + rng.gauss(0, jit)))
            conf.append(0.1 if rng.random() < drop_kp else 0.6 + 0.4 * rng.random())
        yield t, xy, conf, (cam.width, cam.height_px)
