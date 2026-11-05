"""
audio_episodes.py — turns per-window audio classifications into real events.

The classifier looks at 0.5 s windows with 50 % overlap, so one cough is seen
by 2-3 consecutive windows. Previously each window above 60 % became its own
alert and its own database row, so one cough was counted two or three times.

CoughEpisodeTracker:
  • merges consecutive Cough/Sneeze windows into ONE event (peak confidence,
    reasons, duration)
  • detects a coughing FIT — several coughs close together — which is worth a
    gentle check-in from Saathi and a note for the family
Pure Python (no audio libs) so it is unit-testable.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

ALERT_THRESHOLD = 60.0      # % confidence for a window to count
MERGE_GAP_S = 0.8           # windows closer than this belong to the same sound
FIT_WINDOW_S = 60.0         # a "fit" = FIT_MIN_COUGHS coughs within this many seconds
FIT_MIN_COUGHS = 5
FIT_COOLDOWN_S = 600.0      # don't repeat the fit alert for 10 minutes


class CoughEpisodeTracker:
    def __init__(self):
        self._open: Optional[dict] = None
        self._coughs: Deque[float] = deque()
        self._last_fit_t = -1e9
        self._seq = 0

    def update(self, t: float, result: dict) -> List[dict]:
        """
        t      : seconds (monotonic) when the window ended
        result : classifier output with predicted / confidence / why
        Returns finished events: {"kind": "sound", ...} and possibly {"kind": "fit", ...}
        """
        out: List[dict] = []
        label = result.get("predicted")
        conf = float(result.get("confidence") or 0.0)
        positive = label in ("Cough", "Sneeze") and conf >= ALERT_THRESHOLD

        # close the open event if this window doesn't continue it
        if self._open is not None:
            same = positive and label == self._open["type"] and t - self._open["last_t"] <= MERGE_GAP_S
            if same:
                o = self._open
                o["last_t"] = t
                o["windows"] += 1
                if conf > o["confidence"]:
                    o["confidence"] = round(conf, 1)
                    o["why"] = list(result.get("why") or o["why"])
                return out
            out.extend(self._close())

        if positive:
            self._seq += 1
            self._open = {"id": self._seq, "type": label, "start_t": t, "last_t": t, "windows": 1,
                          "confidence": round(conf, 1), "why": list(result.get("why") or [])}
        return out

    def flush(self, t: float) -> List[dict]:
        """Close an open event if enough time has passed (call when no new windows arrive)."""
        if self._open is not None and t - self._open["last_t"] > MERGE_GAP_S:
            return self._close()
        return []

    def _close(self) -> List[dict]:
        o, self._open = self._open, None
        ev = {"kind": "sound", "id": o["id"], "type": o["type"], "confidence": o["confidence"],
              "t": o["start_t"], "duration_s": round(o["last_t"] - o["start_t"] + 0.5, 2),
              "why": o["why"]}
        out = [ev]
        if o["type"] == "Cough":
            self._coughs.append(o["start_t"])
            while self._coughs and o["start_t"] - self._coughs[0] > FIT_WINDOW_S:
                self._coughs.popleft()
            n = len(self._coughs)
            if n >= FIT_MIN_COUGHS and o["start_t"] - self._last_fit_t >= FIT_COOLDOWN_S:
                self._last_fit_t = o["start_t"]
                span = o["start_t"] - self._coughs[0]
                out.append({"kind": "fit", "type": "coughing_fit", "t": o["start_t"], "coughs": n,
                            "span_s": round(span, 1),
                            "why": [f"{n} coughs within {max(1, round(span))} seconds"]})
        return out
