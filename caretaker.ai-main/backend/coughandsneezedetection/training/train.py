"""
Training script for the 4-class audio classifier.

Expected data directory layout:
    data/
        cough/        *.wav
        sneeze/       *.wav
        talking/      *.wav
        noise/        *.wav

Usage:
    python training/train.py --data_dir data --epochs 50 --batch_size 32
"""

import os
import sys
import argparse
import numpy as np
import librosa

# Add project root so we can import the model package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from model.architecture import build_model
from model.preprocessing import (
    audio_to_mel_spectrogram,
    SAMPLE_RATE,
    EXPECTED_FRAMES,
    N_MELS,
)
from training.augment import random_augment


CLASS_DIRS = ["cough", "sneeze", "talking", "noise"]
CLASS_LABELS = {name: idx for idx, name in enumerate(CLASS_DIRS)}


def load_dataset(data_dir: str, augment: bool = True, augment_factor: int = 5):
    """
    Load all audio files from data_dir/{class}/ and return X, y arrays.

    Parameters
    ----------
    data_dir : str
        Root directory containing one sub-folder per class.
    augment : bool
        Whether to apply data augmentation.
    augment_factor : int
        How many augmented copies per original sample.
    """
    X, y = [], []

    for cls_name, cls_idx in CLASS_LABELS.items():
        cls_path = os.path.join(data_dir, cls_name)
        if not os.path.isdir(cls_path):
            print(f"  ⚠  Skipping {cls_path} (not found)")
            continue

        files = [f for f in os.listdir(cls_path) if f.endswith((".wav", ".mp3", ".flac"))]
        print(f"  {cls_name}: {len(files)} files")

        for fname in files:
            fpath = os.path.join(cls_path, fname)
            try:
                audio, _ = librosa.load(fpath, sr=SAMPLE_RATE, mono=True, duration=1.0)
            except Exception as e:
                print(f"    ⚠  Could not load {fname}: {e}")
                continue

            # Pad to 1 second
            target = int(SAMPLE_RATE * 1.0)
            if len(audio) < target:
                audio = np.pad(audio, (0, target - len(audio)))
            else:
                audio = audio[:target]

            # Original sample
            mel = _to_model_input(audio)
            X.append(mel)
            y.append(cls_idx)

            # Augmented copies
            if augment:
                for _ in range(augment_factor):
                    aug = random_augment(audio.copy(), sr=SAMPLE_RATE)
                    mel_aug = _to_model_input(aug)
                    X.append(mel_aug)
                    y.append(cls_idx)

    X = np.concatenate(X, axis=0)
    y = np.array(y, dtype=np.int32)
    return X, y


def _to_model_input(audio: np.ndarray) -> np.ndarray:
    """Audio → normalised mel → (1, 64, 101, 1)."""
    log_mel = audio_to_mel_spectrogram(audio)
    # Pad/trim time
    if log_mel.shape[1] < EXPECTED_FRAMES:
        log_mel = np.pad(log_mel, ((0, 0), (0, EXPECTED_FRAMES - log_mel.shape[1])))
    else:
        log_mel = log_mel[:, :EXPECTED_FRAMES]
    mel_min, mel_max = log_mel.min(), log_mel.max()
    if mel_max - mel_min > 0:
        log_mel = (log_mel - mel_min) / (mel_max - mel_min)
    else:
        log_mel = np.zeros_like(log_mel)
    return log_mel[np.newaxis, :, :, np.newaxis].astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="Train the audio classifier")
    parser.add_argument("--data_dir", type=str, default="data", help="Path to data root")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--augment_factor", type=int, default=5)
    parser.add_argument("--output", type=str, default="model/weights.weights.h5")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════╗")
    print("║   Audio Classifier — Training Pipeline      ║")
    print("╚══════════════════════════════════════════════╝\n")

    print("[1/3] Loading dataset …")
    X, y = load_dataset(args.data_dir, augment=True, augment_factor=args.augment_factor)
    print(f"       Total samples: {len(y)}  |  Classes: {np.bincount(y)}\n")

    # Shuffle
    idx = np.random.permutation(len(y))
    X, y = X[idx], y[idx]

    # Train / val split (80/20)
    split = int(0.8 * len(y))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    print("[2/3] Building model …")
    model = build_model(input_shape=(N_MELS, EXPECTED_FRAMES, 1), num_classes=4)
    model.compile(
        optimizer=__import__("tensorflow").keras.optimizers.Adam(learning_rate=args.lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()

    print("\n[3/3] Training …")
    model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=[
            __import__("tensorflow").keras.callbacks.EarlyStopping(
                patience=8, restore_best_weights=True
            ),
        ],
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    model.save_weights(args.output)
    print(f"\n✅  Weights saved to {args.output}")


if __name__ == "__main__":
    main()
