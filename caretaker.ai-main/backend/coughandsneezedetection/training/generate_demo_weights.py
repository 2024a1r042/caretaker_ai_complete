"""
Generate initial model weights so the application can start immediately.

The CNN is built from scratch with random initialisation.  This script simply
saves those initial weights to disk so app.py can load them without error.

Run once:
    python training/generate_demo_weights.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from model.architecture import build_model


def main():
    print("Building model …")
    model = build_model()
    model.summary()

    weights_path = os.path.join(os.path.dirname(__file__), "..", "model", "weights.weights.h5")
    weights_path = os.path.normpath(weights_path)
    os.makedirs(os.path.dirname(weights_path), exist_ok=True)

    model.save_weights(weights_path)
    print(f"\n[OK] Demo weights saved to {weights_path}")
    print("     (Predictions will be random until you train on real data.)")


if __name__ == "__main__":
    main()
