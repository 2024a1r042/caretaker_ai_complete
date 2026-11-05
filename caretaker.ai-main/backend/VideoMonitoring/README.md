# Video Monitoring System - Restructured

This folder contains all the components for the elderly video monitoring system.

## File Structure

- **`united_monitor.py`**: The main application logic combining fall detection and inactivity monitoring.
- **`fall_detection.py`**: Accelerated fall detection module (GPU/FP16 enabled).
- **`run_live_monitor.py`**: script to start live camera monitoring.
- **`run_video_monitor.py`**: script to analyze uploaded video files.
- **`BodyMovementDetection/`**: Folder containing inactivity monitoring logic.
- **`PERFORMANCE_OPTIMIZATIONS.md`**: Technical details on performance tuning.
- **`QUICK_START.md`**: Guide for running the system.
- **`OPTIMIZATION_SUMMARY.md`**: Overview of changes and improvements.

## How to Run

### Live Camera
```bash
cd backend/VideoMonitoring
python run_live_monitor.py
```
Output saved to: `backend/output_videos/live_session_output.mp4`

### Uploaded Video
```bash
cd backend/VideoMonitoring
python run_video_monitor.py ../fall_video/your_video.mp4
```
Output saved to: `backend/processed_videos/analyzed_your_video.mp4`

## Configuration
Scripts automatically handle paths to resources (models, etc.) in the parent `backend` directory.
