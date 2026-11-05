"""
Acoustic Feature Analyzer — Rule-based cough/sneeze detection.

Uses real signal-processing features to classify audio WITHOUT trained
neural network weights.  This makes the system functional immediately.

Detection is based on physical acoustic properties:
  - Cough:  sudden energy burst, broad spectral content, high onset strength
  - Sneeze: very high energy burst, high-frequency content, sharp attack
  - Talking: harmonic structure, moderate sustained energy, low onset
  - Noise:  low energy, flat spectrum, no transients

Features used:
  1. RMS Energy (loudness)
  2. Spectral Centroid (brightness)
  3. Zero-Crossing Rate (noisiness / fricatives)
  4. Spectral Rolloff (frequency distribution)
  5. Onset Strength (suddenness of sound)
  6. Spectral Bandwidth (frequency spread)
  7. Spectral Flatness (tonal vs noise-like)
"""

import numpy as np
import librosa


def extract_features(audio: np.ndarray, sr: int = 16000) -> dict:
    """
    Extract acoustic features from a short audio clip.

    Parameters
    ----------
    audio : np.ndarray, shape (n_samples,)
        Mono float32 audio at `sr`.
    sr : int
        Sample rate.

    Returns
    -------
    dict of feature name → float value
    """
    # Guard against silence / empty
    if len(audio) < 256 or np.max(np.abs(audio)) < 1e-6:
        return {
            "rms": 0.0, "zcr": 0.0, "centroid": 0.0,
            "rolloff": 0.0, "onset": 0.0, "bandwidth": 0.0,
            "flatness": 0.0, "energy_db": -80.0,
        }

    rms = float(np.sqrt(np.mean(audio ** 2)))
    energy_db = float(20 * np.log10(rms + 1e-10))

    zcr = float(np.mean(librosa.feature.zero_crossing_rate(audio)[0]))

    centroid = float(np.mean(
        librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
    ))

    rolloff = float(np.mean(
        librosa.feature.spectral_rolloff(y=audio, sr=sr, roll_percent=0.85)[0]
    ))

    bandwidth = float(np.mean(
        librosa.feature.spectral_bandwidth(y=audio, sr=sr)[0]
    ))

    flatness = float(np.mean(
        librosa.feature.spectral_flatness(y=audio)[0]
    ))

    onset_env = librosa.onset.onset_strength(y=audio, sr=sr)
    onset = float(np.max(onset_env)) if len(onset_env) > 0 else 0.0

    return {
        "rms": rms,
        "energy_db": energy_db,
        "zcr": zcr,
        "centroid": centroid,
        "rolloff": rolloff,
        "bandwidth": bandwidth,
        "flatness": flatness,
        "onset": onset,
    }


def classify_acoustic(audio: np.ndarray, sr: int = 16000) -> dict:
    """
    Classify audio using acoustic feature heuristics.

    Returns dict with:
      - "Cough", "Sneeze", "Talking", "Noise" confidence scores (0-100)
      - "predicted": class label
      - "confidence": top confidence

    The scores are computed from weighted feature analysis based on
    known acoustic properties of each sound class.
    """
    feat = extract_features(audio, sr)

    # ── Score each class ────────────────────────────────────────────
    scores = {
        "Cough":   _score_cough(feat),
        "Sneeze":  _score_sneeze(feat),
        "Talking": _score_talking(feat),
        "Noise":   _score_noise(feat),
    }

    # Normalise to sum = 100
    total = sum(scores.values())
    if total > 0:
        for k in scores:
            scores[k] = round(scores[k] / total * 100, 2)
    else:
        scores = {"Cough": 0, "Sneeze": 0, "Talking": 0, "Noise": 100}

    predicted = max(scores, key=scores.get)
    return {
        **scores,
        "predicted": predicted,
        "confidence": scores[predicted],
    }


# ── Scoring functions ───────────────────────────────────────────────
# Each returns a raw score (higher = more likely).  Based on:
#   - Cough:  impulsive, broad-band, short, moderate-high energy
#   - Sneeze: very impulsive, high-frequency, sharp attack
#   - Talking: harmonic, sustained, moderate energy, low onset
#   - Noise:  low energy, flat spectrum, low onset

def _score_cough(f: dict) -> float:
    """
    Cough: sudden energy burst, broad spectral content.
    Key: high onset + high energy + moderate centroid + high bandwidth.
    """
    score = 0.0

    # Must have meaningful energy (not silence)
    if f["energy_db"] < -40:
        return 0.0

    # Strong onset (impulsive)
    if f["onset"] > 1.5:
        score += 25
    if f["onset"] > 3.0:
        score += 15

    # High energy
    if f["energy_db"] > -25:
        score += 15
    if f["energy_db"] > -15:
        score += 10

    # Moderate spectral centroid (300-3000 Hz typical for cough)
    if 800 < f["centroid"] < 4000:
        score += 15

    # Broad bandwidth (cough is wideband)
    if f["bandwidth"] > 1500:
        score += 10

    # Moderate-high ZCR
    if f["zcr"] > 0.05:
        score += 5

    # Not too tonal (cough is noise-like)
    if f["flatness"] > 0.01:
        score += 5

    return score


def _score_sneeze(f: dict) -> float:
    """
    Sneeze: very high energy burst with high-frequency content.
    Key: very high onset + high rolloff + high centroid + high energy.
    """
    score = 0.0

    if f["energy_db"] < -35:
        return 0.0

    # Very strong onset
    if f["onset"] > 2.0:
        score += 20
    if f["onset"] > 4.0:
        score += 15

    # Very high energy
    if f["energy_db"] > -20:
        score += 15
    if f["energy_db"] > -10:
        score += 10

    # High-frequency content (sneezes have more HF than coughs)
    if f["centroid"] > 2500:
        score += 15
    if f["centroid"] > 4000:
        score += 10

    # High rolloff (lots of high-freq energy)
    if f["rolloff"] > 4000:
        score += 10

    # High ZCR (fricative "hiss" component)
    if f["zcr"] > 0.1:
        score += 10

    # Broad bandwidth
    if f["bandwidth"] > 2000:
        score += 5

    return score


def _score_talking(f: dict) -> float:
    """
    Talking: harmonic, rhythmic, moderate sustained energy.
    Key: low flatness (tonal) + moderate energy + low onset + moderate centroid.
    """
    score = 0.0

    if f["energy_db"] < -45:
        return 0.0

    # Moderate energy (not too loud, not silent)
    if -35 < f["energy_db"] < -10:
        score += 15

    # Low onset (sustained, not impulsive)
    if f["onset"] < 2.0:
        score += 20
    if f["onset"] < 1.0:
        score += 10

    # Tonal (low spectral flatness = harmonic)
    if f["flatness"] < 0.05:
        score += 15

    # Moderate centroid (speech: ~500-3000 Hz)
    if 400 < f["centroid"] < 3500:
        score += 10

    # Moderate ZCR
    if 0.02 < f["zcr"] < 0.12:
        score += 10

    # Moderate bandwidth
    if 500 < f["bandwidth"] < 2500:
        score += 5

    return score


def _score_noise(f: dict) -> float:
    """
    Background noise: low energy, flat spectrum, no transients.
    Key: low energy + low onset + high flatness.
    """
    score = 0.0

    # Very low energy = very likely noise
    if f["energy_db"] < -40:
        score += 40
    elif f["energy_db"] < -30:
        score += 20
    elif f["energy_db"] < -20:
        score += 5

    # Low onset (no impulsive events)
    if f["onset"] < 0.8:
        score += 25
    elif f["onset"] < 1.5:
        score += 10

    # High spectral flatness (white-noise-like)
    if f["flatness"] > 0.1:
        score += 10

    # Low ZCR
    if f["zcr"] < 0.05:
        score += 5

    return score
