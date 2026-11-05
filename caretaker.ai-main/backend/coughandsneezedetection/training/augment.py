"""
Data augmentation utilities for training the audio classifier.

Apply to raw audio waveforms before computing spectrograms.
Designed for use with AudioSet, COUGHVID, ESC-50, or custom datasets.
"""

import numpy as np
import librosa


def add_white_noise(audio: np.ndarray, noise_factor: float = 0.005) -> np.ndarray:
    """Add Gaussian white noise."""
    noise = np.random.randn(len(audio)) * noise_factor
    return audio + noise


def time_stretch(audio: np.ndarray, rate: float | None = None) -> np.ndarray:
    """Time-stretch the audio by a random factor (0.8–1.2)."""
    if rate is None:
        rate = np.random.uniform(0.8, 1.2)
    return librosa.effects.time_stretch(audio, rate=rate)


def pitch_shift(audio: np.ndarray, sr: int = 16_000, n_steps: float | None = None) -> np.ndarray:
    """Shift pitch by `n_steps` semitones (random ±2 if None)."""
    if n_steps is None:
        n_steps = np.random.uniform(-2, 2)
    return librosa.effects.pitch_shift(audio, sr=sr, n_steps=n_steps)


def volume_perturbation(audio: np.ndarray) -> np.ndarray:
    """Random gain change between 0.6× and 1.4×."""
    gain = np.random.uniform(0.6, 1.4)
    return audio * gain


def add_background(audio: np.ndarray, bg_audio: np.ndarray, snr_db: float = 10.0) -> np.ndarray:
    """Mix a background noise signal at the specified SNR (dB)."""
    # Match lengths
    if len(bg_audio) < len(audio):
        bg_audio = np.tile(bg_audio, int(np.ceil(len(audio) / len(bg_audio))))
    bg_audio = bg_audio[: len(audio)]

    # Compute powers
    sig_power = np.mean(audio ** 2) + 1e-10
    bg_power = np.mean(bg_audio ** 2) + 1e-10
    target_bg_power = sig_power / (10 ** (snr_db / 10))
    scale = np.sqrt(target_bg_power / bg_power)

    return audio + scale * bg_audio


def random_augment(audio: np.ndarray, sr: int = 16_000) -> np.ndarray:
    """
    Apply a random combination of augmentations.

    Each augmentation has a 50 % chance of being applied, making every
    call produce a unique variant of the input.
    """
    if np.random.rand() > 0.5:
        audio = add_white_noise(audio, noise_factor=np.random.uniform(0.001, 0.01))
    if np.random.rand() > 0.5:
        audio = time_stretch(audio)
    if np.random.rand() > 0.5:
        audio = pitch_shift(audio, sr=sr)
    if np.random.rand() > 0.5:
        audio = volume_perturbation(audio)
    return audio
