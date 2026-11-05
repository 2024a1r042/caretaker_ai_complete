"""The fall engine on the synthetic test bench — every scenario, several frame-rates and distances."""
import pytest

from fall_inference import FallInferenceEngine, EV_FALL, EV_RECOVERED, EV_LONG_LIE, NORMAL, LYING_IN_BED
from fall_scenarios import build_scenarios, render

SCENARIOS = {s.name: s for s in build_scenarios()}


def run(scn, fps=15.0, dist=4.5, seed=1, sensitivity="medium", **kw):
    eng = FallInferenceEngine(sensitivity=sensitivity, bed_zones=scn.bed_zones)
    events, last = [], None
    for t, xy, conf, size in render(scn, fps=fps, distance=dist, seed=seed, **kw):
        last = eng.update(t, xy, conf, frame_size=size)
        events.extend(last["events"])
    return eng, events, last


@pytest.mark.parametrize("name", list(SCENARIOS))
@pytest.mark.parametrize("fps,dist", [(10.0, 3.0), (15.0, 4.5), (30.0, 6.5)])
def test_scenario_expectation(name, fps, dist):
    scn = SCENARIOS[name]
    _, events, _ = run(scn, fps=fps, dist=dist)
    falls = [e for e in events if e["type"] == EV_FALL]
    if scn.expect == "none":
        assert not falls, f"false alarm: {falls[0]['explanation']}"
    elif scn.expect == "fall":
        assert len(falls) == 1 and falls[0]["severity"] == "high"
    elif scn.expect == "check_in":
        assert len(falls) == 1
    elif scn.expect == "fall+recovered":
        assert len(falls) == 1 and any(e["type"] == EV_RECOVERED for e in events)
    elif scn.expect == "fall+long_lie":
        assert len(falls) == 1 and any(e["type"] == EV_LONG_LIE for e in events)


def test_every_alert_is_explained():
    _, events, _ = run(SCENARIOS["fall_sideways"])
    ev = next(e for e in events if e["type"] == EV_FALL)
    assert ev["explanation"].startswith(("Hard fall", "Fall"))
    signals = {e["signal"] for e in ev["evidence"]}
    assert {"head_drop", "peak_speed", "torso_rotation", "on_ground", "stayed_down"} <= signals
    assert 0 < ev["confidence"] <= 1
    assert abs(sum(c["weight"] for c in ev["score_breakdown"]) - 1.0) < 0.02


def test_detection_latency_is_short():
    scn = SCENARIOS["fall_sideways"]
    _, events, _ = run(scn)
    ev = next(e for e in events if e["type"] == EV_FALL)
    assert ev["t"] - scn.impact_t < 2.5      # confirmed within ~2 s of hitting the floor


def test_recovery_reports_time_on_ground():
    _, events, last = run(SCENARIOS["fall_then_gets_up"])
    rec = next(e for e in events if e["type"] == EV_RECOVERED)
    assert 3 <= rec["time_on_ground_s"] <= 8
    assert last["state"] == NORMAL


def test_long_lie_is_critical():
    _, events, _ = run(SCENARIOS["fall_long_lie"])
    ll = next(e for e in events if e["type"] == EV_LONG_LIE)
    assert ll["severity"] == "critical" and ll["still_for_s"] >= 25


def test_bed_zone_is_rest_not_fall():
    _, events, last = run(SCENARIOS["lie_down_in_bed_zone"])
    assert not [e for e in events if e["type"] == EV_FALL]
    assert last["state"] == LYING_IN_BED


def test_robust_to_heavy_pose_noise():
    for name in ("fall_sideways", "sit_down_fast", "bend_pick_up", "fall_long_lie"):
        scn = SCENARIOS[name]
        _, events, _ = run(scn, noise_px=4.0, drop_kp=0.10, drop_frame=0.08, seed=3)
        falls = [e for e in events if e["type"] == EV_FALL]
        assert bool(falls) == (scn.expect != "none"), name


def test_learned_model_is_one_input_not_a_gate():
    scn = SCENARIOS["fall_sideways"]
    eng = FallInferenceEngine()
    got = []
    for t, xy, conf, size in render(scn, fps=15, distance=4.5, seed=1):
        got += eng.update(t, xy, conf, size, lstm_prob=0.05)["events"]   # model says "no fall"
    fall = next(e for e in got if e["type"] == EV_FALL)                  # kinematics still catch it
    assert any(e["signal"] == "learned_model" and not e["passed"] for e in fall["evidence"])
