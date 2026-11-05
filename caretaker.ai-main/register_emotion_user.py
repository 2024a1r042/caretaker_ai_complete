import base64
import os
from pathlib import Path

import requests

EMOTION_API_BASE = "http://127.0.0.1:8000/emotion"


def image_to_base64(path: str) -> str:
    path_obj = Path(path).expanduser().resolve()
    if not path_obj.is_file():
        raise FileNotFoundError(f"Image not found: {path_obj}")
    with open(path_obj, "rb") as f:
        data = f.read()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")


def main():
    print("=== Emotion Service User Registration ===")
    name = input("Name (for display): ").strip() or "Caretaker"
    email = input("Email (must be unique in emotion service): ").strip() or "caretaker@example.com"
    img_path = input("Path to reference face photo (jpg/png): ").strip()

    ref_photo_b64 = image_to_base64(img_path)

    payload = {
        "name": name,
        "email": email,
        "reference_photo": ref_photo_b64,
    }

    print("\nSending registration request to", EMOTION_API_BASE + "/api/register")
    resp = requests.post(EMOTION_API_BASE + "/register", json=payload, timeout=60)

    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    print("Status:", resp.status_code)
    print("Response:", data)
    if resp.ok and "user_id" in data:
        print("\nSUCCESS: Registered user with id:", data["user_id"])
        print("Video Monitoring will now show emotions when THIS face is in frame.")
    else:
        print("\nRegistration failed; see response above.")


if __name__ == "__main__":
    main()
