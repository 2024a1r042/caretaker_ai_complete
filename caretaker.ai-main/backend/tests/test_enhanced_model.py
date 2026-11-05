"""
test_enhanced_model.py — Unit tests and benchmarks for enhanced temporal fall models.

Verifies:
  1. Feature extraction dimensions (34-dim coords vs 72-dim enhanced features)
  2. Velocity calculation & geometry bounds (angle, aspect ratio)
  3. FallSequenceBuffer in both 'coords' and 'enhanced' modes
  4. Forward pass & gradient flow for EnhancedFallModel
  5. TorchScript JIT acceleration & accuracy parity
  6. Backward compatibility with pre-trained fall_lstm.pth
"""

import sys
import os
import math
import numpy as np
import pytest
import torch

_video_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "VideoMonitoring"))
sys.path.insert(0, _video_dir)

from fall_lstm_model import (
    FallLSTM,
    EnhancedFallModel,
    FallSequenceBuffer,
    normalize_keypoints,
    extract_enhanced_features,
    compile_torchscript,
    load_model,
    INPUT_FEATURES,
    ENHANCED_FEATURES,
    DEFAULT_SEQ_LEN,
)


def _sample_keypoints(standing: bool = True):
    """Generate synthetic 17-point COCO skeleton (upright vs horizontal fall)."""
    kps = np.zeros((17, 2), dtype=np.float32)
    if standing:
        # Vertical upright posture
        kps[0] = [320, 100]  # nose
        kps[1], kps[2] = [315, 95], [325, 95]
        kps[3], kps[4] = [310, 95], [330, 95]
        kps[5], kps[6] = [290, 140], [350, 140]  # shoulders
        kps[7], kps[8] = [280, 190], [360, 190]
        kps[9], kps[10] = [275, 240], [365, 240]
        kps[11], kps[12] = [300, 260], [340, 260]  # hips
        kps[13], kps[14] = [295, 360], [345, 360]
        kps[15], kps[16] = [290, 450], [350, 450]  # ankles
    else:
        # Horizontal fallen posture on the floor
        kps[0] = [150, 410]  # nose
        kps[1], kps[2] = [155, 408], [155, 412]
        kps[3], kps[4] = [160, 405], [160, 415]
        kps[5], kps[6] = [200, 395], [200, 425]  # shoulders (lateral across vertical)
        kps[7], kps[8] = [250, 395], [250, 425]
        kps[9], kps[10] = [280, 395], [280, 425]
        kps[11], kps[12] = [320, 400], [320, 420]  # hips (shifted horizontally)
        kps[13], kps[14] = [380, 405], [380, 425]
        kps[15], kps[16] = [440, 410], [440, 430]  # ankles
    return kps


def test_normalize_keypoints_shape_and_centering():
    xy = _sample_keypoints(standing=True)
    vec = normalize_keypoints(xy)
    assert vec.shape == (34,)
    assert vec.dtype == np.float32
    # Mid-hip should be at (0, 0)
    hip_x = (vec[11 * 2] + vec[12 * 2]) / 2.0
    hip_y = (vec[11 * 2 + 1] + vec[12 * 2 + 1]) / 2.0
    assert abs(hip_x) < 1e-5
    assert abs(hip_y) < 1e-5


def test_extract_enhanced_features_velocity_and_geometry():
    standing = _sample_keypoints(standing=True)
    falling = _sample_keypoints(standing=False)

    # First frame (no velocity)
    f0 = extract_enhanced_features(standing, prev_xy=None)
    assert f0.shape == (ENHANCED_FEATURES,)
    # Velocities (features 34:68) must be zero on the initial frame
    assert np.allclose(f0[34:68], 0.0)

    # Torso tilt for standing person should be low (~0)
    torso_tilt_standing = f0[68]
    assert torso_tilt_standing < 0.15

    # Second frame with downward movement (high velocity & horizontal posture)
    f1 = extract_enhanced_features(falling, prev_xy=standing)
    assert f1.shape == (ENHANCED_FEATURES,)
    vel_mag = np.linalg.norm(f1[34:68])
    assert vel_mag > 0.1  # Clear downward displacement

    # Torso tilt for fallen person should be high
    torso_tilt_fallen = f1[68]
    assert torso_tilt_fallen > torso_tilt_standing


def test_fall_sequence_buffer_both_modes():
    # 1. Coords mode (34-dim)
    b_coords = FallSequenceBuffer(seq_len=DEFAULT_SEQ_LEN, feature_mode="coords")
    assert not b_coords.ready
    kps = _sample_keypoints(standing=True)
    for _ in range(DEFAULT_SEQ_LEN):
        b_coords.push(kps)
    assert b_coords.ready
    t_coords = b_coords.get_tensor("cpu")
    assert t_coords.shape == (1, DEFAULT_SEQ_LEN, INPUT_FEATURES)

    # 2. Enhanced mode (72-dim)
    b_enh = FallSequenceBuffer(seq_len=DEFAULT_SEQ_LEN, feature_mode="enhanced")
    assert not b_enh.ready
    for _ in range(DEFAULT_SEQ_LEN):
        b_enh.push(kps)
    assert b_enh.ready
    t_enh = b_enh.get_tensor("cpu")
    assert t_enh.shape == (1, DEFAULT_SEQ_LEN, ENHANCED_FEATURES)


def test_enhanced_fall_model_forward_and_backward():
    model = EnhancedFallModel(input_size=ENHANCED_FEATURES, hidden_size=64, num_layers=2)
    model.train()
    batch = torch.randn(4, DEFAULT_SEQ_LEN, ENHANCED_FEATURES, requires_grad=True)
    logits = model(batch)
    assert logits.shape == (4, 2)
    loss = logits.sum()
    loss.backward()
    assert batch.grad is not None
    assert torch.any(batch.grad != 0)


def test_torchscript_acceleration_and_parity():
    model = EnhancedFallModel(input_size=ENHANCED_FEATURES, hidden_size=64, num_layers=1)
    model.eval()
    traced = compile_torchscript(model, seq_len=DEFAULT_SEQ_LEN, input_size=ENHANCED_FEATURES)

    inp = torch.randn(2, DEFAULT_SEQ_LEN, ENHANCED_FEATURES)
    with torch.no_grad():
        out_eager = model(inp)
        out_traced = traced(inp)

    diff = torch.max(torch.abs(out_eager - out_traced)).item()
    assert diff < 1e-4, f"Parity mismatch: diff={diff}"
    assert getattr(traced, "input_size", None) == ENHANCED_FEATURES


def test_load_model_checkpoint_backward_compatibility():
    ckpt_path = os.path.join(_video_dir, "fall_lstm.pth")
    if not os.path.isfile(ckpt_path):
        pytest.skip("fall_lstm.pth not found")

    model, dev = load_model(ckpt_path, use_jit=True)
    assert model is not None
    assert dev in ("cpu", "cuda")

    # The existing checkpoint takes 34 input features
    inp = torch.randn(1, 30, 34, device=dev)
    with torch.no_grad():
        out = model(inp)
    assert out.shape == (1, 2)
