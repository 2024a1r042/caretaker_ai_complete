"""
camera_registry.py — Persistent store for named IP/CCTV camera URLs.

Stores camera configs as JSON in the backend directory.
Supports local webcam indexes (0, 1, …) and any RTSP/HTTP stream URL.
"""
import json
import os
import threading
from typing import Dict, List, Optional

_REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "camera_registry.json")
_lock = threading.Lock()


def _load() -> Dict[str, dict]:
    if os.path.isfile(_REGISTRY_FILE):
        try:
            with open(_REGISTRY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    with open(_REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def list_cameras() -> List[dict]:
    """Return all saved cameras as a list of dicts."""
    with _lock:
        data = _load()
        cameras = []
        for cam_id, cam in data.items():
            cameras.append({
                "id": cam_id,
                "name": cam.get("name", cam_id),
                "url": cam.get("url", ""),
                "type": cam.get("type", "ip"),  # "webcam" | "ip" | "rtsp"
                "location": cam.get("location", ""),
                "username": cam.get("username", ""),
                # Never return password in listing
            })
        return cameras


def get_camera(cam_id: str) -> Optional[dict]:
    """Return a single camera including password (for internal use)."""
    with _lock:
        data = _load()
        cam = data.get(cam_id)
        if cam:
            return {"id": cam_id, **cam}
        return None


def add_camera(cam_id: str, name: str, url: str, cam_type: str = "ip",
               location: str = "", username: str = "", password: str = "") -> dict:
    """Add or update a camera. Returns the saved record."""
    with _lock:
        data = _load()
        data[cam_id] = {
            "name": name,
            "url": url,
            "type": cam_type,
            "location": location,
            "username": username,
            "password": password,
        }
        _save(data)
        return {"id": cam_id, "name": name, "url": url, "type": cam_type, "location": location}


def remove_camera(cam_id: str) -> bool:
    """Remove a camera. Returns True if it existed."""
    with _lock:
        data = _load()
        if cam_id in data:
            del data[cam_id]
            _save(data)
            return True
        return False


def build_stream_url(cam_id: str) -> Optional[str]:
    """
    Build the OpenCV-compatible capture URL/index for a camera.

    - Webcam entries: url is an integer string ("0", "1") → returns int
    - IP/RTSP entries: if username+password set, embed creds in RTSP URL
    """
    cam = get_camera(cam_id)
    if not cam:
        return None

    url = cam.get("url", "")
    cam_type = cam.get("type", "ip")

    if cam_type == "webcam":
        try:
            return int(url)   # cv2.VideoCapture(0)
        except ValueError:
            return url

    # Embed credentials into RTSP URL if provided
    username = cam.get("username", "")
    password = cam.get("password", "")
    if username and password and url.startswith("rtsp://"):
        # rtsp://user:pass@host/path
        url = url.replace("rtsp://", f"rtsp://{username}:{password}@", 1)

    return url
