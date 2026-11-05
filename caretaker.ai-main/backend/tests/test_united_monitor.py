"""
UnitedMonitor end-to-end with YOLO stubbed out (the real BiGRU checkpoint is
loaded): synthetic skeletons go in as if YOLO had produced them, and the
monitor must fire exactly one explained fall event and draw the overlay.
"""
import sys
import types

import numpy as np
import pytest

from fall_scenarios import build_scenarios, render

torch = pytest.importorskip("torch")


class _T:
    def __init__(self, a): self.a = np.asarray(a, dtype=np.float32)
    def cpu(self): return self
    def numpy(self): return self.a
    def __getitem__(self, i): return _T(self.a[i])
    def __len__(self): return len(self.a)


class _FakeYOLO:
    feed = []

    def __init__(self, *a, **k): pass

    def _res(self):
        xy, conf = _FakeYOLO.feed.pop(0)
        if xy is None:
            return [types.SimpleNamespace(boxes=None, keypoints=None)]
        xy = np.asarray(xy, dtype=np.float32)
        box = [xy[:, 0].min() - 20, xy[:, 1].min() - 30, xy[:, 0].max() + 20, xy[:, 1].max() + 10]
        boxes = types.SimpleNamespace(xyxy=_T([box]), id=None)
        kps = types.SimpleNamespace(xy=_T([xy]), conf=_T([conf]))
        return [types.SimpleNamespace(boxes=boxes, keypoints=kps)]

    def predict(self, *a, **k): return self._res()
    def track(self, *a, **k): return self._res()


@pytest.fixture()
def monitor_cls(monkeypatch):
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=_FakeYOLO))
    sys.modules.pop("united_monitor", None)
    import united_monitor
    return united_monitor


def test_monitor_fires_one_explained_fall(monitor_cls):
    scn = next(s for s in build_scenarios() if s.name == "fall_sideways")
    frames = list(render(scn, fps=15, distance=4.0, seed=1, drop_kp=0.0))
    _FakeYOLO.feed = [(xy, conf) for _, xy, conf, _ in frames]
    mon = monitor_cls.UnitedMonitor(is_live=False, video_fps=15)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    fired, last = [], None
    for t, *_ in frames:
        last = mon.process_frame(img, timestamp=t)
        fired += [e for e in last["fall"]["events"] if e["type"] == "fall_confirmed"]
    assert len(fired) == 1
    assert fired[0]["explanation"]
    assert last["global_state"]["fall_detected"] is True
    out = monitor_cls.draw_united_interface(img, last)
    assert out.shape == img.shape and out.sum() > 0      # overlay with evidence drawn


def test_monitor_ignores_sitting(monitor_cls):
    scn = next(s for s in build_scenarios() if s.name == "sit_down_fast")
    frames = list(render(scn, fps=15, distance=4.0, seed=1, drop_kp=0.0))
    _FakeYOLO.feed = [(xy, conf) for _, xy, conf, _ in frames]
    mon = monitor_cls.UnitedMonitor(is_live=False, video_fps=15)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    for t, *_ in frames:
        r = mon.process_frame(img, timestamp=t)
        assert not r["fall"]["fall_event_fired"]
