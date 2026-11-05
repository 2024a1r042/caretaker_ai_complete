"""
Flask + SocketIO backend for real-time audio classification.

Uses a HYBRID approach:
  - Acoustic Feature Analyzer: rule-based, works immediately
  - CRNN model: learns from data, improves with training

The acoustic analyzer is the primary detection engine.
When the CRNN is trained, both scores are blended.
"""

import os
import datetime
import numpy as np
import tensorflow as tf
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from model import build_model, CLASS_LABELS
from model.preprocessing import SAMPLE_RATE
from model.acoustic_analyzer import classify_acoustic
import requests

# ── Configuration ───────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.60          # 60% — acoustic analyzer is reliable enough
CHUNK_DURATION       = 0.5           # 500 ms windows
CHUNK_SAMPLES        = int(SAMPLE_RATE * CHUNK_DURATION)
OVERLAP_RATIO        = 0.5
SLIDE_SAMPLES        = int(CHUNK_SAMPLES * (1 - OVERLAP_RATIO))

# ── Flask app ───────────────────────────────────────────────────────
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_timeout=60, ping_interval=25, max_http_buffer_size=1e8)

# ── Model (optional — enhances accuracy when trained) ───────────────
print("=" * 52)
print("  SonicGuard CRNN -- Loading ...")
print("=" * 52)

model = build_model()
weights_path = os.path.join(os.path.dirname(__file__), "model", "weights.weights.h5")
MODEL_TRAINED = False

if os.path.isfile(weights_path):
    try:
        model.load_weights(weights_path)
        print(f"  [OK] Loaded weights from {weights_path}")
    except Exception as e:
        print(f"  [WARN] Could not load weights: {e}")
else:
    print("  [INFO] No weights found -- using acoustic analyzer only.")

# Warm-up
_dummy = np.zeros((1, 64, 101, 1), dtype=np.float32)
_ = model(_dummy, training=False)
print("  [OK] Model warmed up")
print("  [OK] Acoustic Feature Analyzer active -- detection ready!")

# ── Sliding window buffer ──────────────────────────────────────────
_buffer = np.array([], dtype=np.float32)

# ── Database Integration ────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
AUTH_TOKEN = None  # Will be set when client connects with auth
RECIPIENT_ID = None  # Will be set when client connects with recipient info

def log_audio_event_to_db(event_type, confidence, care_recipient_id=None):
    """
    Log audio event to the backend database via API.
    This runs asynchronously to avoid blocking the detection pipeline.
    """
    if not AUTH_TOKEN:
        return  # Skip if no authentication token available
    
    try:
        payload = {
            "event_type": event_type,
            "confidence": confidence,
            "care_recipient_id": care_recipient_id,
            "duration_ms": int(CHUNK_DURATION * 1000)
        }
        headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
        
        # Non-blocking request (fire and forget)
        requests.post(
            f"{API_BASE_URL}/audio-events",
            json=payload,
            headers=headers,
            timeout=2
        )
    except Exception as e:
        # Silently fail to avoid disrupting the detection pipeline
        print(f"  [WARN] Failed to log event to database: {e}")


# ── Routes ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": "CRNN + Acoustic",
        "chunk_ms": int(CHUNK_DURATION * 1000),
        "threshold": CONFIDENCE_THRESHOLD,
    })


# ── WebSocket events ────────────────────────────────────────────────
@socketio.on("connect")
def handle_connect():
    global _buffer
    _buffer = np.array([], dtype=np.float32)
    print("  [+] Client connected")


@socketio.on("disconnect")
def handle_disconnect():
    global _buffer
    _buffer = np.array([], dtype=np.float32)
    print("  [-] Client disconnected")


@socketio.on("reset")
def handle_reset():
    """Clear server-side state and acknowledge."""
    global _buffer
    _buffer = np.array([], dtype=np.float32)
    emit("reset_ack", {"status": "ok", "timestamp": datetime.datetime.now().strftime("%H:%M:%S")})
    print("  [RESET] State reset")


@socketio.on("authenticate")
def handle_authenticate(data):
    """Receive authentication token and recipient ID from client for database logging."""
    global AUTH_TOKEN, RECIPIENT_ID
    AUTH_TOKEN = data.get("token")
    RECIPIENT_ID = data.get("recipient_id")
    if AUTH_TOKEN:
        print(f"  [AUTH] Token received for database logging")
        if RECIPIENT_ID:
            print(f"  [AUTH] Recipient ID: {RECIPIENT_ID}")
    emit("auth_ack", {"status": "ok"})


@socketio.on("audio_chunk")
def handle_audio_chunk(data):
    """
    Receive raw PCM audio bytes and classify using acoustic features.
    """
    global _buffer

    try:
        samples = np.frombuffer(data, dtype=np.float32)
    except Exception:
        return

    _buffer = np.concatenate([_buffer, samples])

    while len(_buffer) >= CHUNK_SAMPLES:
        window = _buffer[:CHUNK_SAMPLES]

        # ── Acoustic Feature Analysis (primary) ────────────────────
        result = classify_acoustic(window, sr=SAMPLE_RATE)

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        result["timestamp"] = timestamp

        emit("classification", result)

        # Alert if Cough or Sneeze with sufficient confidence
        predicted = result["predicted"]
        confidence = result["confidence"]

        if predicted in ("Cough", "Sneeze") and confidence >= CONFIDENCE_THRESHOLD * 100:
            emit("alert", {
                "type":       predicted,
                "confidence": round(confidence, 2),
                "timestamp":  timestamp,
            })
            
            # Log to database for long-term analysis
            log_audio_event_to_db(predicted, round(confidence, 2), RECIPIENT_ID)

        # Slide forward
        _buffer = _buffer[SLIDE_SAMPLES:]


# ── Entry point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n  >> Server starting at http://localhost:5001")
    print(f"     Chunk: {int(CHUNK_DURATION*1000)}ms | Overlap: {int(OVERLAP_RATIO*100)}% | Threshold: {int(CONFIDENCE_THRESHOLD*100)}%\n")
    socketio.run(app, host="0.0.0.0", port=5001, debug=False)
