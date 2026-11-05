"""
STEP 2: Train temporal fall detection models (FallLSTM or EnhancedFallModel).

Supports:
  - Baseline BiGRU + Attention (34 keypoint coordinates)
  - Enhanced Conv1D + BiGRU + Residual Attention (72 features: coords + velocities + posture)
  - Training on extracted real keypoints (data/*.npy) or synthetic scenario bench (--synthetic)
  - GroupShuffleSplit (80/20) by event group to ensure ZERO data leakage
  - Weighted CrossEntropyLoss for class imbalance
  - Cosine annealing learning rate schedule + gradient clipping

Usage:
  python train_lstm.py --model enhanced --features enhanced --epochs 25
  python train_lstm.py --model baseline --features coords --epochs 50
"""

import os
import sys
import argparse
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

try:
    from sklearn.model_selection import GroupShuffleSplit
except ImportError:
    print("[ERROR] scikit-learn not installed. Run: pip install scikit-learn")
    sys.exit(1)

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

from fall_lstm_model import (
    FallLSTM,
    EnhancedFallModel,
    normalize_keypoints,
    extract_enhanced_features,
    INPUT_FEATURES,
    ENHANCED_FEATURES,
    DEFAULT_SEQ_LEN,
)
from fall_scenarios import build_scenarios, render

DATA_DIR = os.path.join(_here, "data")
DEFAULT_MODEL_OUT = os.path.join(_here, "fall_lstm_enhanced.pth")


def generate_synthetic_dataset(feature_mode: str = "enhanced",
                               seq_len: int = DEFAULT_SEQ_LEN,
                               stride: int = 15) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate synthetic dataset of keypoint sequence windows from 3D physics-based scenarios.
    Returns:
        X : (N, seq_len, num_features) float32
        y : (N,) int64 (0=normal, 1=fall)
        g : (N,) object group tags for zero-leakage splitting
    """
    print(f"\n[DataGenerator] Synthesizing dataset across 20 scripted scenarios (mode='{feature_mode}')...")
    scenarios = build_scenarios()
    fps_set = (10.0, 15.0, 30.0)
    dist_set = (3.0, 4.5, 6.0)
    seeds = (1, 2, 3)

    seq_list, label_list, group_list = [], [], []

    for scn in scenarios:
        is_fall_scenario = (scn.expect != "none")

        for fps in fps_set:
            for dist in dist_set:
                for seed in seeds:
                    group_id = f"{scn.name}_d{dist:.1f}_s{seed}"
                    frames = list(render(scn, fps=fps, distance=dist, seed=seed))
                    if len(frames) < seq_len:
                        continue

                    # Extract frame-level features
                    features = []
                    prev_xy = None
                    for t, xy, conf, _ in frames:
                        xy_arr = np.array(xy, dtype=np.float32) if xy is not None else None
                        conf_arr = np.array(conf, dtype=np.float32) if conf is not None else None

                        if feature_mode == "enhanced":
                            feat = extract_enhanced_features(xy_arr, prev_xy=prev_xy, conf=conf_arr)
                        else:
                            feat = normalize_keypoints(xy_arr, conf=conf_arr)

                        features.append((t, feat))
                        prev_xy = xy_arr

                    # Extract sliding windows
                    for start_idx in range(0, len(features) - seq_len + 1, stride):
                        window = features[start_idx:start_idx + seq_len]
                        win_t_start = window[0][0]
                        win_t_end = window[-1][0]
                        win_data = np.stack([f[1] for f in window], axis=0)  # (seq_len, features)

                        # Determine if this specific window captures the fall transition
                        if is_fall_scenario:
                            if scn.impact_t is not None:
                                # Fall occurs when window overlaps impact time or floor state
                                is_fall_win = (win_t_end >= scn.impact_t and win_t_start <= scn.impact_t + 2.5)
                            else:
                                is_fall_win = (win_t_end >= 2.0)
                            lbl = 1 if is_fall_win else 0
                        else:
                            lbl = 0

                        seq_list.append(win_data)
                        label_list.append(lbl)
                        group_list.append(group_id)

    X = np.stack(seq_list, axis=0).astype(np.float32)
    y = np.array(label_list, dtype=np.int64)
    g = np.array(group_list, dtype=object)

    print(f"[DataGenerator] Generated {len(X)} sequences (falls={int(y.sum())}, normal={int((y == 0).sum())})")
    print(f"[DataGenerator] Unique event groups: {len(set(g))}")
    return X, y, g


def main():
    parser = argparse.ArgumentParser(description="Train Fall Detection Neural Network")
    parser.add_argument("--model", choices=["baseline", "enhanced"], default="enhanced",
                        help="Model architecture ('baseline' for FallLSTM, 'enhanced' for EnhancedFallModel)")
    parser.add_argument("--features", choices=["coords", "enhanced"], default="enhanced",
                        help="Feature mode ('coords' for 34 dims, 'enhanced' for 72 dims)")
    parser.add_argument("--epochs", type=int, default=25, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Initial learning rate")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic dataset generation")
    parser.add_argument("--out", type=str, default=None, help="Output checkpoint file path")
    args = parser.parse_args()

    # Determine feature dimensions
    in_features = ENHANCED_FEATURES if args.features == "enhanced" else INPUT_FEATURES
    model_out = args.out or (DEFAULT_MODEL_OUT if args.model == "enhanced" else os.path.join(_here, "fall_lstm.pth"))

    # ── Load or Synthesize Data ──────────────────────────────────────────────
    has_real_data = all(
        os.path.isfile(os.path.join(DATA_DIR, fname))
        for fname in ("sequences.npy", "labels.npy", "groups.npy")
    )

    if args.synthetic or not has_real_data:
        if not has_real_data and not args.synthetic:
            print("[Info] Real dataset files not found in data/. Falling back to synthetic physics bench...")
        X, y, g = generate_synthetic_dataset(feature_mode=args.features)
    else:
        print("[Data] Loading extracted keypoint sequences from data/...")
        X = np.load(os.path.join(DATA_DIR, "sequences.npy"))
        y = np.load(os.path.join(DATA_DIR, "labels.npy"))
        g = np.load(os.path.join(DATA_DIR, "groups.npy"), allow_pickle=True)

    # Validate feature dimension compatibility
    if X.shape[-1] != in_features:
        print(f"[Warning] Data feature dim ({X.shape[-1]}) != configured features ({in_features}).")
        if not args.synthetic:
            print("[Warning] Re-synthesizing dataset to match feature mode...")
            X, y, g = generate_synthetic_dataset(feature_mode=args.features)

    # ── Zero-Leakage Group Split (80 / 20) ───────────────────────────────────
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, val_idx = next(splitter.split(X, y, groups=g))

    train_groups = set(g[train_idx])
    val_groups = set(g[val_idx])
    overlap = train_groups & val_groups
    assert len(overlap) == 0, f"[FATAL] Group leakage detected: {overlap}"

    print(f"\n[Split] Train: {len(train_idx)} sequences across {len(train_groups)} groups")
    print(f"[Split] Val  : {len(val_idx)} sequences across {len(val_groups)} groups")
    print("[Split] Group leakage verification: PASSED\n")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[Device] Using {device.upper()}")

    # ── Class Balancing ──────────────────────────────────────────────────────
    counts = np.bincount(y)
    total = counts.sum()
    weights = torch.tensor(
        [total / (2.0 * max(1, counts[0])), total / (2.0 * max(1, counts[1]))],
        dtype=torch.float32
    ).to(device)
    print(f"[Loss] Class weights -> normal={weights[0]:.3f}, fall={weights[1]:.3f}")
    loss_fn = nn.CrossEntropyLoss(weight=weights)

    # ── Data Loaders ─────────────────────────────────────────────────────────
    def make_loader(idx, shuffle: bool) -> DataLoader:
        Xt = torch.from_numpy(X[idx].astype(np.float32))
        yt = torch.from_numpy(y[idx])
        return DataLoader(TensorDataset(Xt, yt), batch_size=args.batch, shuffle=shuffle)

    train_loader = make_loader(train_idx, shuffle=True)
    val_loader = make_loader(val_idx, shuffle=False)

    # ── Model Instantiation ──────────────────────────────────────────────────
    if args.model == "enhanced":
        model = EnhancedFallModel(input_size=in_features).to(device)
        print(f"[Architecture] Initialized EnhancedFallModel (Conv1D + BiGRU + Residual Attention, in_feat={in_features})")
    else:
        model = FallLSTM(input_size=in_features).to(device)
        print(f"[Architecture] Initialized FallLSTM (BiGRU + Attention, in_feat={in_features})")

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_f1 = 0.0
    best_acc = 0.0

    print(f"\n{'Epoch':>5}  {'Loss':>8}  {'Acc':>7}  {'Prec':>7}  {'Rec':>7}  {'F1':>7}")
    print("-" * 55)

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()
        avg_loss = total_loss / max(1, len(train_loader))

        # Validate
        model.eval()
        correct = total = 0
        tp = fp = fn = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                preds = model(xb).argmax(dim=1)
                correct += (preds == yb).sum().item()
                total += len(yb)
                tp += ((preds == 1) & (yb == 1)).sum().item()
                fp += ((preds == 1) & (yb == 0)).sum().item()
                fn += ((preds == 0) & (yb == 1)).sum().item()

        acc = correct / max(1, total)
        prec = tp / (tp + fp + 1e-8)
        rec = tp / (tp + fn + 1e-8)
        f1 = 2 * prec * rec / (prec + rec + 1e-8)

        print(f"{epoch:5d}  {avg_loss:8.4f}  {acc:7.4f}  {prec:7.4f}  {rec:7.4f}  {f1:7.4f}", end="")

        if f1 > best_f1 or (f1 == best_f1 and acc > best_acc):
            best_f1 = f1
            best_acc = acc
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_accuracy": round(acc, 4),
                "val_f1": round(f1, 4),
                "val_precision": round(prec, 4),
                "val_recall": round(rec, 4),
                "model_type": args.model,
                "features": args.features,
                "input_features": in_features,
            }, model_out)
            print("  <- saved checkpoint", end="")

        print()

    print(f"\n{'=' * 55}")
    print(f"Training Complete! Best Val Accuracy: {best_acc:.4f} | Best F1: {best_f1:.4f}")
    print(f"Checkpoint saved to: {model_out}")


if __name__ == "__main__":
    main()
