# Real-video checks

Two public clips from GitHub, run through the **full pipeline** (YOLOv8s-pose →
FallInferenceEngine, BiGRU as one input) — and through the app's own upload route
and browser UI. They are not bundled here (unknown licence); fetch them with:

```bash
git clone --depth 1 https://github.com/harishrithish7/Fall-Detection      # videos/video.mp4
git clone --depth 1 https://github.com/kanis777/Yavar_hackathon           # inputmp4/output_video.mp4
```

| Clip | What happens | ORIGINAL pipeline | NEW pipeline |
|---|---|---|---|
| A `video.mp4` (320×240, 10 fps, real room) | walks in, **sits on a chair** (~8–12 s), stands, **falls to the floor** at ~15.6 s (partly out of frame) | **false alarm at the chair (frame 90), real fall missed** | chair → no alert; fall → **"Hard fall", high**, ~1.5 s after hitting the floor |
| B `output_video.mp4` (720×480, overhead fisheye lab camera) | walks in, **falls onto a floor mat**, lies still | fall detected (frame 101) | **fall, high** at a realistic 15–30 fps reading (see note) |

Note on clip B: the file's metadata says 120 fps, but 210 frames cannot contain a walk,
a fall and lying still in 1.75 s — the clip has clearly been subsampled. At the stated
120 fps the engine thinks they were on the floor for under a second and does not
confirm; at 15–30 fps it confirms. Real cameras report true timestamps, so this only
affects re-encoded files.

## What the real footage taught us (and what was changed because of it)
1. **The trained BiGRU outputs 0.95–1.00 "fall" while the person simply walks and sits**
   in clip A — it does not transfer to real footage. That is why the old pipeline
   false-alarmed on the chair. It is now one 10%-weighted input, not the gate.
2. **yolov8n-pose missed a person lying on the floor in 10/11 overhead frames**;
   yolov8s-pose found 9/11. The default is now yolov8s-pose (`POSE_MODEL` in `.env`).
3. **A person who drops fast and then slides out of view** used to reset the engine;
   it now raises the alarm ("reached the floor, then left the camera's view").
4. **TensorFlow + PyTorch in one process segfaults** — the server crashed on the
   first uploaded video. TensorFlow is no longer loaded in the server process.

Two clips is a smoke test, not an accuracy figure. For the review, label 20–40 clips
(UR Fall / Le2i / your own room) and run `../evaluate_on_videos.py`.
