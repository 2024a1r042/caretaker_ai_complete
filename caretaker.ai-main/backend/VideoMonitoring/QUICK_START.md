# Quick Start Guide - Optimized Video Monitoring

## New Directory Structure
All video monitoring scripts are now located in the `VideoMonitoring` folder.
Output videos are saved to `output_videos` or `processed_videos` in the main backend folder.

## For Live Camera Monitoring

### Basic Usage (Recommended):
```bash
cd backend/VideoMonitoring
python united_monitor.py --camera 0 --frame-skip 2
```

### High Performance Mode (if you have a good GPU):
```bash
python united_monitor.py --camera 0 --frame-skip 1 --sensitivity high
```

### Low Resource Mode (for slower computers):
```bash
python united_monitor.py --camera 0 --frame-skip 3 --sensitivity low
```

## For Uploaded Video Analysis

### Basic Usage:
```bash
cd backend/VideoMonitoring
python run_video_monitor.py ../fall_video/your_video.mp4
```

### With Custom Output:
```bash
python run_video_monitor.py ../fall_video/your_video.mp4 --output ../processed_videos/custom_output.mp4
```

## Command Line Options

### united_monitor.py Options:
- `--camera N`: Camera index (default: 0)
- `--video PATH`: Use video file instead of camera
- `--output PATH`: Save output video (default: output.mp4)
- `--sensitivity [low|medium|high]`: Detection sensitivity (default: medium)
- `--threshold N`: Inactivity threshold in seconds (default: 30)
- `--frame-skip N`: Process every N frames for live camera (default: 2)
- `--no-show`: Don't display window (headless mode)

## Understanding the Display

### HUD Information:
1. **FPS Display**: 
   - Green (>15 FPS): Excellent performance
   - Orange (10-15 FPS): Acceptable performance
   - Red (<10 FPS): Poor performance - increase frame skip

2. **Status Indicators**:
   - "Status: Normal" (Green): Everything is fine
   - "FALL DETECTED!" (Red): Fall detected
   - "INACTIVITY ALERT" (Orange): Person inactive too long
   - "Status: No Person" (Gray): No person in frame

3. **Bounding Boxes**:
   - Green: Monitored person (normal)
   - Red: Fall detected
   - Orange: Inactivity alert
   - Cyan: Other people (visitors)

4. **Metrics**:
   - Inactivity Timer: Seconds person has been inactive
   - Angle: Body torso angle (degrees)
   - Speed: Vertical movement speed

## Performance Tips

### If FPS is Low (<10):
1. Increase `--frame-skip` to 3 or 4
2. Lower sensitivity to "low"
3. Reduce camera resolution in camera settings
4. Close other applications
5. Check if GPU is being used (see console output)

### If Detection is Inaccurate:
1. Decrease `--frame-skip` to 1 or 2
2. Increase sensitivity to "high"
3. Ensure good lighting
4. Position camera to see full body
5. Avoid cluttered backgrounds

## System Requirements

### Minimum (CPU Only):
- Intel i5 or AMD Ryzen 5
- 8GB RAM
- Webcam or video file
- Expected FPS: 8-12 (with frame-skip=3)

### Recommended (with GPU):
- NVIDIA GPU (GTX 1060 or better)
- 16GB RAM
- CUDA 11.8 or later
- Expected FPS: 15-25 (with frame-skip=2)

### Optimal (High-End GPU):
- NVIDIA RTX 3060 or better
- 16GB+ RAM
- CUDA 11.8 or later
- Expected FPS: 25-30 (with frame-skip=1)

## Keyboard Controls

- **Q**: Quit the application
- **ESC**: Quit the application (alternative)

## Troubleshooting

### "No camera found" Error:
```bash
# List available cameras (Windows)
python -c "import cv2; print([i for i in range(10) if cv2.VideoCapture(i).isOpened()])"

# Try different camera index
python united_monitor.py --camera 1
```

### GPU Not Working:
```bash
# Check if CUDA is available
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"

# If False, install CUDA-enabled PyTorch:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Low FPS Despite GPU:
1. Check console for "[FallDetector] Using device: cuda"
2. If it says "cpu", GPU is not being used
3. Verify NVIDIA drivers are up to date
4. Check GPU usage with `nvidia-smi` command

## Examples

### Example 1: Monitor elderly person with default settings
```bash
python united_monitor.py --camera 0 --threshold 30
```

### Example 2: High sensitivity for fall-prone individual
```bash
python united_monitor.py --camera 0 --sensitivity high --threshold 20
```

### Example 3: Analyze uploaded video
```bash
python run_video_monitor.py ../fall_video/test_fall.mp4
```

### Example 4: Save output without display (headless)
```bash
python united_monitor.py --camera 0 --output recording.mp4 --no-show
```

## What's New in This Version

✅ **Frame Skipping**: Intelligent frame skipping for live feeds
✅ **GPU Acceleration**: Automatic GPU detection and usage
✅ **FP16 Inference**: Half precision for 2x faster processing
✅ **Optimized Image Size**: Reduced from 640 to 416 for speed
✅ **FPS Display**: Real-time performance monitoring
✅ **Result Caching**: Smooth visualization with frame skipping
✅ **Smart Processing**: Always process frames during fall detection

## Support

For issues or questions:
1. Check console output for error messages
2. Review PERFORMANCE_OPTIMIZATIONS.md for detailed information
3. Verify system requirements are met
4. Test with different frame-skip values
