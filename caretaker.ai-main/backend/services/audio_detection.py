"""
AudioDetectionService — mirrors the logic from coughandsneezedetection/app.py.

Primary engine: Acoustic Feature Analyzer (rule-based, always active).
Secondary engine: CRNN model (optional, boosts confidence when loaded).

The acoustic analyzer is the reliable detection engine.
The CRNN model is used ONLY to confirm/boost a detection that the
acoustic analyzer already flagged — it does NOT override it.
"""

import os
import numpy as np
import logging
import datetime
from typing import Dict, Any, Optional

try:
    from utils.audio_model.preprocessing import preprocess_chunk, SAMPLE_RATE
    from utils.audio_model.acoustic_analyzer import classify_acoustic, explain
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from utils.audio_model.preprocessing import preprocess_chunk, SAMPLE_RATE
    from utils.audio_model.acoustic_analyzer import classify_acoustic, explain

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: TensorFlow must never be imported in the API server process.
# Loading TensorFlow and PyTorch (YOLO pose / fall detection) in the same
# process segfaults — verified: the server crashed the moment a video was
# analysed. The optional CRNN therefore runs in its own helper process, and
# only when trained weights actually exist (they are not in the repo; before,
# an UNTRAINED network was built at every startup and never used).
# ─────────────────────────────────────────────────────────────────────────────
_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "utils", "audio_model", "weights.weights.h5")


def _crnn_worker(conn, weights_path):
    """Runs in a separate process: owns TensorFlow, answers predict requests."""
    import numpy as _np
    from utils.audio_model.architecture import build_model as _build
    model = _build()
    model.load_weights(weights_path)
    model(_np.zeros((1, 64, 101, 1), dtype=_np.float32), training=False)
    conn.send("ready")
    while True:
        msg = conn.recv()
        if msg is None:
            break
        conn.send(model(msg, training=False).numpy()[0].tolist())


class _CRNNClient:
    def __init__(self, weights_path):
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=_crnn_worker, args=(child, weights_path), daemon=True)
        self._proc.start()
        if not self._conn.poll(120) or self._conn.recv() != "ready":
            raise RuntimeError("CRNN helper process did not start")

    def predict(self, x, timeout=2.0):
        self._conn.send(x)
        if not self._conn.poll(timeout):
            raise TimeoutError("CRNN helper timed out")
        return self._conn.recv()

logger = logging.getLogger(__name__)

# Match original app.py constants
CONFIDENCE_THRESHOLD = 0.60   # 60%
CHUNK_DURATION       = 0.5    # 500 ms
CHUNK_SAMPLES        = int(SAMPLE_RATE * CHUNK_DURATION)
OVERLAP_RATIO        = 0.5
SLIDE_SAMPLES        = int(CHUNK_SAMPLES * (1 - OVERLAP_RATIO))

CLASS_LABELS = ["Cough", "Sneeze", "Talking", "Noise"]


class AudioDetectionService:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        # Sliding window buffer — one per connected client (previously a single
        # shared buffer, so two open tabs mixed their audio together)
        self._buffer = np.array([], dtype=np.float32)
        self._buffers = {}
        self._load_model()

    def _load_model(self):
        """Load CRNN weights if available. Mirrors original app.py startup."""
        print("=" * 52)
        print("  SonicGuard CRNN -- Loading ...")
        print("=" * 52)

        if os.getenv("AUDIO_CRNN", "1") == "0":
            print("  [INFO] AUDIO_CRNN=0 -- using acoustic analyzer only.")
        elif not os.path.isfile(_WEIGHTS_PATH):
            print("  [INFO] No trained weights found -- using acoustic analyzer only (TensorFlow not loaded).")
        else:
            try:
                self.model = _CRNNClient(_WEIGHTS_PATH)
                self.model_loaded = True
                print(f"  [OK] CRNN loaded in a helper process from {_WEIGHTS_PATH}")
            except Exception as e:
                logger.error(f"Failed to load audio model: {e}")
                self.model_loaded = False

        print("  [OK] Acoustic Feature Analyzer active -- detection ready!")

    def reset_buffer(self, sid=None):
        """Reset a client's sliding window buffer (each browser tab has its own)."""
        if sid is None:
            self._buffer = np.array([], dtype=np.float32)
        else:
            self._buffers.pop(sid, None)

    def process_audio_chunk(self, audio_bytes: bytes, sid=None):
        """
        Append incoming PCM bytes to the sliding window buffer and
        yield classification results for each complete window.

        This exactly mirrors the while-loop in the original handle_audio_chunk().

        Returns a list of result dicts (may be empty if buffer not full yet).
        """
        try:
            samples = np.frombuffer(audio_bytes, dtype=np.float32)
        except Exception:
            return []

        buf = self._buffers.get(sid, np.array([], dtype=np.float32)) if sid is not None else self._buffer
        buf = np.concatenate([buf, samples])
        results = []

        while len(buf) >= CHUNK_SAMPLES:
            window = buf[:CHUNK_SAMPLES]

            # ── Acoustic Feature Analysis (primary, always runs) ────
            result = classify_acoustic(window, sr=SAMPLE_RATE)

            # ── CRNN boost (secondary, only when model is loaded) ───
            # Only boost if acoustic already suspects Cough/Sneeze
            if self.model_loaded and result["predicted"] in ("Cough", "Sneeze"):
                try:
                    input_tensor = preprocess_chunk(window, sr=SAMPLE_RATE)
                    probs = self.model.predict(input_tensor)

                    dl_scores = {
                        "Cough":   float(probs[0] * 100),
                        "Sneeze":  float(probs[1] * 100),
                        "Talking": float(probs[2] * 100),
                        "Noise":   float(probs[3] * 100),
                    }

                    # Blend: 70% acoustic (reliable) + 30% DL (texture)
                    for cls in CLASS_LABELS:
                        result[cls] = round(result[cls] * 0.70 + dl_scores[cls] * 0.30, 2)

                    # Recompute winner after blend
                    predicted = max(CLASS_LABELS, key=lambda c: result[c])
                    result["predicted"]  = predicted
                    result["confidence"] = result[predicted]
                    if result.get("features"):
                        result["why"] = explain(result["features"], predicted)

                except Exception as e:
                    logger.error(f"DL inference failed: {e}")

            result["timestamp"] = datetime.datetime.now().strftime("%H:%M:%S")
            results.append(result)

            # Slide forward
            buf = buf[SLIDE_SAMPLES:]

        if sid is not None:
            self._buffers[sid] = buf
        else:
            self._buffer = buf
        return results


# Global singleton — loaded once at startup
audio_service = AudioDetectionService()
