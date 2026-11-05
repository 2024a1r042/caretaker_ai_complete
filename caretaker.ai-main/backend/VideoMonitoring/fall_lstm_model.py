"""
fall_lstm_model.py — Enhanced temporal model architecture for fall detection.

Components:
  - FallLSTM              : Baseline Bidirectional GRU + self-attention + classifier (34 features)
  - EnhancedFallModel     : Hybrid Conv1D + BiGRU + self-attention with residual dynamics (34 or 72 features)
  - FallSequenceBuffer    : Rolling sequence buffer supporting 'coords' (34-dim) or 'enhanced' (72-dim)
  - normalize_keypoints   : Hip-centred, torso-scaled normalisation (34-dim coords)
  - extract_enhanced_features : High-fidelity 72-dim vector (coords + inter-frame velocities + posture cues)
  - compile_torchscript   : JIT-trace model for low-latency CPU inference
  - load_model            : Load and auto-detect checkpoint type, dimensions, with optional JIT acceleration
"""

import os
import math
import numpy as np
import torch
import torch.nn as nn
from collections import deque
from typing import Optional, Tuple, Union

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_SEQ_LEN    = 30    # frames per sequence (~1.5s at 20fps)
INPUT_FEATURES     = 34    # 17 COCO keypoints × 2 (x, y)
ENHANCED_FEATURES  = 72    # 34 coords + 34 velocities + 4 posture/geometric signals
HIDDEN_SIZE        = 128
NUM_LAYERS         = 2
DROPOUT            = 0.4

# COCO keypoint indices
NOSE           =  0
L_SHO,  R_SHO  =  5,  6
L_HIP,  R_HIP  = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANK,  R_ANK  = 15, 16
# ─────────────────────────────────────────────────────────────────────────────


def normalize_keypoints(xy: np.ndarray,
                        conf: np.ndarray | None = None,
                        min_conf: float = 0.2) -> np.ndarray:
    """
    Normalize 17 COCO keypoints to be hip-centred and torso-scaled.

    Args:
        xy       : (17, 2) float array of keypoint coordinates (pixels)
        conf     : (17,)  float array of keypoint confidences (optional)
        min_conf : confidences below this are zeroed out

    Returns:
        (34,) float32 normalised feature vector
    """
    if xy is None or len(xy) < 17:
        return np.zeros(INPUT_FEATURES, dtype=np.float32)

    kps = xy.copy().astype(np.float32)

    # Zero out low-confidence keypoints
    if conf is not None:
        for i in range(len(kps)):
            if conf[i] < min_conf:
                kps[i] = [0.0, 0.0]

    hip_mid = (kps[L_HIP] + kps[R_HIP]) / 2.0
    sho_mid = (kps[L_SHO] + kps[R_SHO]) / 2.0
    torso   = float(np.linalg.norm(sho_mid - hip_mid))

    if torso < 1e-4:
        return np.zeros(INPUT_FEATURES, dtype=np.float32)

    norm = (kps - hip_mid) / torso

    # Re-zero points that were originally zero (missing)
    for i in range(len(kps)):
        if xy[i, 0] == 0.0 and xy[i, 1] == 0.0:
            norm[i] = [0.0, 0.0]

    return norm.flatten().astype(np.float32)


def extract_enhanced_features(xy: np.ndarray,
                              prev_xy: np.ndarray | None = None,
                              conf: np.ndarray | None = None,
                              min_conf: float = 0.2) -> np.ndarray:
    """
    Extract a rich 72-dimensional feature vector combining:
      1. (34) Normalized coordinates (hip-centered, torso-scaled)
      2. (34) Normalized inter-frame velocity / displacement (dx, dy)
      3. (1)  Torso tilt angle relative to vertical (0.0=upright, 1.0=horizontal)
      4. (1)  Bounding box aspect ratio (width / height, scaled to 0..1)
      5. (1)  Hip vertical position relative to leg span
      6. (1)  Head elevation relative to hip and torso length

    Returns:
        (72,) float32 enhanced feature vector
    """
    if xy is None or len(xy) < 17:
        return np.zeros(ENHANCED_FEATURES, dtype=np.float32)

    kps = xy.copy().astype(np.float32)

    if conf is not None:
        for i in range(len(kps)):
            if conf[i] < min_conf:
                kps[i] = [0.0, 0.0]

    hip_mid = (kps[L_HIP] + kps[R_HIP]) / 2.0
    sho_mid = (kps[L_SHO] + kps[R_SHO]) / 2.0
    torso   = float(np.linalg.norm(sho_mid - hip_mid))

    if torso < 1e-4:
        return np.zeros(ENHANCED_FEATURES, dtype=np.float32)

    # 1. Normalized coords (34 dims)
    norm = (kps - hip_mid) / torso
    for i in range(len(kps)):
        if xy[i, 0] == 0.0 and xy[i, 1] == 0.0:
            norm[i] = [0.0, 0.0]
    coords_vec = norm.flatten().astype(np.float32)

    # 2. Velocity / displacement vector (34 dims)
    if prev_xy is not None and len(prev_xy) >= 17:
        prev_kps = prev_xy.copy().astype(np.float32)
        prev_hip = (prev_kps[L_HIP] + prev_kps[R_HIP]) / 2.0
        prev_sho = (prev_kps[L_SHO] + prev_kps[R_SHO]) / 2.0
        prev_torso = float(np.linalg.norm(prev_sho - prev_hip))
        if prev_torso > 1e-4:
            prev_norm = (prev_kps - prev_hip) / prev_torso
            vel_vec = (norm - prev_norm).flatten().astype(np.float32)
        else:
            vel_vec = np.zeros(34, dtype=np.float32)
    else:
        vel_vec = np.zeros(34, dtype=np.float32)

    # 3. Geometric and posture signals (4 dims)
    # (a) Torso tilt angle relative to vertical (0..1)
    vx = sho_mid[0] - hip_mid[0]
    vy = sho_mid[1] - hip_mid[1]
    torso_angle = float(math.atan2(abs(vx), max(1e-4, abs(vy))) / (math.pi / 2.0))
    torso_angle = min(1.0, max(0.0, torso_angle))

    # (b) Bounding box aspect ratio (width / height)
    valid_mask = (kps[:, 0] > 0) | (kps[:, 1] > 0)
    if np.any(valid_mask):
        valid_kps = kps[valid_mask]
        box_w = float(np.max(valid_kps[:, 0]) - np.min(valid_kps[:, 0]))
        box_h = float(np.max(valid_kps[:, 1]) - np.min(valid_kps[:, 1]))
        aspect = box_w / max(1.0, box_h)
        aspect_norm = min(1.0, max(0.0, aspect / 2.5))
    else:
        aspect_norm = 0.0

    # (c) Hip vertical position relative to leg span
    ank_mid = (kps[L_ANK] + kps[R_ANK]) / 2.0
    if ank_mid[1] > 0 and hip_mid[1] > 0:
        leg_span = max(1e-4, ank_mid[1] - hip_mid[1])
        hip_height_ratio = float(min(1.5, max(0.0, leg_span / (torso * 1.6))))
    else:
        hip_height_ratio = 0.5

    # (d) Head vertical elevation relative to hip
    nose = kps[NOSE]
    if nose[1] > 0 and hip_mid[1] > 0:
        head_elevation = float((hip_mid[1] - nose[1]) / torso)
        head_elev_norm = min(1.0, max(0.0, (head_elevation + 0.5) / 2.0))
    else:
        head_elev_norm = 0.5

    geo_vec = np.array([torso_angle, aspect_norm, hip_height_ratio, head_elev_norm], dtype=np.float32)

    return np.concatenate([coords_vec, vel_vec, geo_vec]).astype(np.float32)


# ── Attention layer ──────────────────────────────────────────────────────────

class _SelfAttention(nn.Module):
    """Additive self-attention over the time dimension (Bahdanau-style)."""

    def __init__(self, hidden_dim: int):
        super().__init__()
        self.attn = nn.Linear(hidden_dim * 2, 1)   # ×2 because BiGRU

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq, hidden*2)
        scores  = self.attn(x).squeeze(-1)          # (batch, seq)
        weights = torch.softmax(scores, dim=-1)     # (batch, seq)
        context = (weights.unsqueeze(-1) * x).sum(dim=1)  # (batch, hidden*2)
        return context


# ── Baseline Model ───────────────────────────────────────────────────────────

class FallLSTM(nn.Module):
    """
    Bidirectional GRU with self-attention for fall/normal classification.
    Compatible with existing checkpoint `fall_lstm.pth`.

    Input  : (batch, seq_len, 34)
    Output : (batch, 2)   logits — 0=normal, 1=fall
    """

    def __init__(self,
                 input_size:  int = INPUT_FEATURES,
                 hidden_size: int = HIDDEN_SIZE,
                 num_layers:  int = NUM_LAYERS,
                 dropout:     float = DROPOUT):
        super().__init__()
        self.input_size  = input_size
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        self.bn_input = nn.BatchNorm1d(input_size)

        self.gru = nn.GRU(
            input_size    = input_size,
            hidden_size   = hidden_size,
            num_layers    = num_layers,
            batch_first   = True,
            bidirectional = True,
            dropout       = dropout if num_layers > 1 else 0.0,
        )

        self.attention = _SelfAttention(hidden_size)

        self.classifier = nn.Sequential(
            nn.Linear(hidden_size * 2, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, features)
        batch, seq, feat = x.shape

        # BatchNorm expects (batch*seq, features)
        x = x.reshape(batch * seq, feat)
        x = self.bn_input(x)
        x = x.reshape(batch, seq, feat)

        out, _  = self.gru(x)         # (batch, seq, hidden*2)
        context = self.attention(out) # (batch, hidden*2)
        logits  = self.classifier(context)
        return logits


# ── Enhanced Temporal Model ──────────────────────────────────────────────────

class EnhancedFallModel(nn.Module):
    """
    Hybrid Conv1D + BiGRU + Additive Self-Attention model with residual connection
    for multi-joint spatio-temporal fall detection.

    Architecture:
      1. BatchNorm1d input normalization
      2. Conv1D temporal filter (kernel_size=3) to extract joint acceleration/jerk
      3. Bidirectional GRU (2 layers) capturing full-sequence trajectory
      4. Additive Self-Attention pooling across time
      5. LayerNorm + Dense classification head

    Input  : (batch, seq_len, in_features) — typically 34 or 72 features
    Output : (batch, 2) logits — [normal, fall]
    """

    def __init__(self,
                 input_size:    int = ENHANCED_FEATURES,
                 conv_channels: int = 64,
                 hidden_size:   int = HIDDEN_SIZE,
                 num_layers:    int = NUM_LAYERS,
                 dropout:       float = 0.3):
        super().__init__()
        self.input_size    = input_size
        self.conv_channels = conv_channels
        self.hidden_size   = hidden_size
        self.num_layers    = num_layers

        self.bn_input = nn.BatchNorm1d(input_size)

        # 1D Temporal Convolution to capture short-term multi-joint dynamic changes
        self.conv1d = nn.Sequential(
            nn.Conv1d(in_channels=input_size, out_channels=conv_channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(conv_channels),
            nn.ReLU(),
            nn.Dropout(dropout / 2),
        )

        # Bidirectional GRU to model trajectory over the window
        self.gru = nn.GRU(
            input_size    = conv_channels,
            hidden_size   = hidden_size,
            num_layers    = num_layers,
            batch_first   = True,
            bidirectional = True,
            dropout       = dropout if num_layers > 1 else 0.0,
        )

        self.attention = _SelfAttention(hidden_size)

        self.classifier = nn.Sequential(
            nn.Linear(hidden_size * 2, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, features)
        batch, seq, feat = x.shape
        x_bn = self.bn_input(x.reshape(batch * seq, feat)).reshape(batch, seq, feat)

        # Conv1d expects (batch, channels, seq)
        x_conv = self.conv1d(x_bn.transpose(1, 2)).transpose(1, 2)

        out, _  = self.gru(x_conv)     # (batch, seq, hidden * 2)
        context = self.attention(out)  # (batch, hidden * 2)
        logits  = self.classifier(context)
        return logits


# ── Sequence buffer for inference ────────────────────────────────────────────

class FallSequenceBuffer:
    """
    Rolling ring buffer that accumulates sequence windows of normalised keypoints.

    Supported feature modes:
      - 'coords'   : 34 features (baseline FallLSTM checkpoint compatibility)
      - 'enhanced' : 72 features (coords + velocity + geometric signals for EnhancedFallModel)

    Usage:
        buf = FallSequenceBuffer(seq_len=30, feature_mode="enhanced")
        for frame in video:
            buf.push(xy, conf)
            if buf.ready:
                tensor = buf.get_tensor(device)
                logits = model(tensor)
    """

    def __init__(self, seq_len: int = DEFAULT_SEQ_LEN, feature_mode: str = "coords"):
        self.seq_len = seq_len
        self.feature_mode = feature_mode
        self._buf: deque = deque(maxlen=seq_len)
        self._prev_xy: Optional[np.ndarray] = None
        self._prev_conf: Optional[np.ndarray] = None

    @property
    def ready(self) -> bool:
        return len(self._buf) == self.seq_len

    @property
    def feature_dim(self) -> int:
        return ENHANCED_FEATURES if self.feature_mode == "enhanced" else INPUT_FEATURES

    def push(self, xy: np.ndarray, conf: np.ndarray | None = None):
        """Push one frame's keypoints into the buffer."""
        if self.feature_mode == "enhanced":
            vec = extract_enhanced_features(xy, self._prev_xy, conf)
            self._prev_xy = xy.copy() if xy is not None else None
            self._prev_conf = conf.copy() if conf is not None else None
        else:
            vec = normalize_keypoints(xy, conf)
        self._buf.append(vec)

    def get_tensor(self, device: str = "cpu") -> torch.Tensor:
        """Return a (1, seq_len, feature_dim) float32 tensor ready for the model."""
        arr = np.stack(list(self._buf), axis=0)   # (seq_len, feature_dim)
        t   = torch.from_numpy(arr).unsqueeze(0)  # (1, seq_len, feature_dim)
        return t.to(device)

    def reset(self):
        self._buf.clear()
        self._prev_xy = None
        self._prev_conf = None


# ── Checkpoint & JIT helpers ─────────────────────────────────────────────────

def compile_torchscript(model: nn.Module,
                        seq_len: int = DEFAULT_SEQ_LEN,
                        input_size: int = INPUT_FEATURES,
                        device: str = "cpu") -> torch.jit.ScriptModule:
    """
    Traces and optimizes a PyTorch model with TorchScript for low-latency CPU inference.
    """
    model.eval()
    dummy_input = torch.zeros(1, seq_len, input_size, dtype=torch.float32, device=device)
    with torch.no_grad():
        traced_model = torch.jit.trace(model, dummy_input)
        # Warm up
        _ = traced_model(dummy_input)
    traced_model.input_size = input_size
    return traced_model


def load_model(path: str,
               input_size:  int = INPUT_FEATURES,
               hidden_size: int = HIDDEN_SIZE,
               num_layers:  int = NUM_LAYERS,
               use_jit:     bool = True) -> tuple[nn.Module, str]:
    """
    Load a fall detection model checkpoint. Automatically detects model architecture
    (FallLSTM vs EnhancedFallModel) and input feature dimension (34 vs 72).

    Returns:
        (model, device_str)

    Raises:
        FileNotFoundError if path does not exist.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"[FallLSTM] Model not found: {path}\n"
            "  → Run extract_keypoints.py first, then train_lstm.py."
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    checkpoint = torch.load(path, map_location=device)
    state_dict = checkpoint["model_state_dict"] if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint else checkpoint

    # Auto-detect input dimension from bn_input weight
    if "bn_input.weight" in state_dict:
        in_feat = state_dict["bn_input.weight"].shape[0]
    else:
        in_feat = input_size

    # Auto-detect whether this is an EnhancedFallModel (has conv1d) or baseline FallLSTM
    is_enhanced = any(k.startswith("conv1d") for k in state_dict.keys())
    if is_enhanced:
        model = EnhancedFallModel(input_size=in_feat, hidden_size=hidden_size, num_layers=num_layers)
    else:
        model = FallLSTM(input_size=in_feat, hidden_size=hidden_size, num_layers=num_layers)

    model.load_state_dict(state_dict)
    val_acc = checkpoint.get("val_accuracy", "?") if isinstance(checkpoint, dict) else "?"
    val_f1  = checkpoint.get("val_f1", "?") if isinstance(checkpoint, dict) else "?"
    print(f"[FallLSTM] Loaded {'Enhanced' if is_enhanced else 'Standard'} checkpoint: in_feat={in_feat} acc={val_acc} f1={val_f1}")

    model.to(device)
    model.eval()

    if use_jit and device == "cpu":
        try:
            model = compile_torchscript(model, seq_len=30, input_size=in_feat, device=device)
            print("[FallLSTM] TorchScript JIT acceleration active.")
        except Exception as e:
            print(f"[FallLSTM] JIT tracing skipped ({e}); using standard PyTorch.")

    return model, device
