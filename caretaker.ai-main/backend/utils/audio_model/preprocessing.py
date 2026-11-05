"""
Audio preprocessing pipeline for the real-time classifier.

Converts raw PCM audio (float32, 16 kHz mono) into a Log-Mel Spectrogram
ready for CNN inference.

Parameters (per spec):
    - Window length : 25 ms  →  400 samples @ 16 kHz
    - Hop length    : 10 ms  →  160 samples @ 16 kHz
    - Mel bands     : 64
    - Duration      : 1 s    →  ~101 time frames
"""

import numpy as np
import librosa

# ── Constants ───────────────────────────────────────────────────────
SAMPLE_RATE    = 16_000
DURATION       = 1.0          # seconds per analysis window
N_FFT          = 512
WIN_LENGTH     = 400          # 25 ms
HOP_LENGTH     = 160          # 10 ms
N_MELS         = 64
EXPECTED_FRAMES = 101         # ceil(16000 / 160) + 1


def audio_to_mel_spectrogram(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Convert a 1-D audio waveform to a Log-Mel Spectrogram.

    Parameters
    ----------
    audio : np.ndarray, shape (n_samples,)
        Mono audio waveform (float32, already at `sr`).
    sr : int
        Sample rate.

    Returns
    -------
    np.ndarray, shape (N_MELS, time_frames)
        Log-scaled mel spectrogram.
    """
    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sr,
        n_fft=N_FFT,
        hop_length=HOP_LENGTH,
        win_length=WIN_LENGTH,
        n_mels=N_MELS,
        fmax=sr // 2,
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)
    return log_mel


def preprocess_chunk(raw_pcm: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Full preprocessing: raw PCM → model-ready tensor.

    Steps:
        1. Ensure correct length (zero-pad or truncate to 1 s).
        2. Compute Log-Mel Spectrogram.
        3. Normalise to [0, 1].
        4. Reshape to (1, mel_bands, time_frames, 1) for the CNN.

    Parameters
    ----------
    raw_pcm : np.ndarray, shape (n_samples,)
        Mono float32 audio at `sr`.

    Returns
    -------
    np.ndarray, shape (1, 64, EXPECTED_FRAMES, 1)
    """
    target_len = int(sr * DURATION)

    # Pad or trim to exactly 1 second
    if len(raw_pcm) < target_len:
        raw_pcm = np.pad(raw_pcm, (0, target_len - len(raw_pcm)))
    else:
        raw_pcm = raw_pcm[:target_len]

    log_mel = audio_to_mel_spectrogram(raw_pcm, sr)

    # Pad / trim time axis to EXPECTED_FRAMES
    if log_mel.shape[1] < EXPECTED_FRAMES:
        pad_w = EXPECTED_FRAMES - log_mel.shape[1]
        log_mel = np.pad(log_mel, ((0, 0), (0, pad_w)), mode="constant")
    else:
        log_mel = log_mel[:, :EXPECTED_FRAMES]

    # Normalise to [0, 1]
    mel_min = log_mel.min()
    mel_max = log_mel.max()
    if mel_max - mel_min > 0:
        log_mel = (log_mel - mel_min) / (mel_max - mel_min)
    else:
        log_mel = np.zeros_like(log_mel)

    # (1, mel_bands, time_frames, 1)
    return log_mel[np.newaxis, :, :, np.newaxis].astype(np.float32)
