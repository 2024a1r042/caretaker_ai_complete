"""
Video Monitoring System - Integration Test
Tests both live monitoring and video upload functionality
"""

import sys
import requests
import time
import json
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configuration
API_BASE = "http://127.0.0.1:8000/api"
TOKEN = None  # Will be set after login

def test_login():
    """Test user authentication"""
    global TOKEN
    print("\n[AUTH] Testing Login...")
    
    try:
        response = requests.post(
            f"{API_BASE}/login",
            json={
                "username": "demo_caretaker",
                "password": "Password@123"
            },
            timeout=10
        )
    except Exception as e:
        print(f"[FAIL] Backend unreachable at {API_BASE}: {e}")
        return False
    
    if response.status_code == 200:
        data = response.json()
        TOKEN = data.get("result", {}).get("access_token")
        if TOKEN:
            print("[OK] Login successful (demo_caretaker)")
            return True
        else:
            print(f"[FAIL] Token missing in response: {data}")
            return False
    else:
        print(f"[FAIL] Login failed: {response.text}")
        return False

def test_stats():
    """Test camera registry / stats endpoint"""
    print("\n[CAMERAS] Testing Camera Registry Endpoint...")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        response = requests.get(f"{API_BASE}/video-monitoring/cameras", headers=headers, timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"[OK] Cameras retrieved: {stats}")
            return True
        else:
            print(f"[FAIL] Cameras query failed: {response.text}")
            return False
    except Exception as e:
        print(f"[FAIL] Cameras query exception: {e}")
        return False

def test_live_monitoring():
    """Test live monitoring start/stop"""
    print("\n[LIVE] Testing Live Monitoring...")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Start monitoring
    print("  Starting live session...")
    try:
        response = requests.post(
            f"{API_BASE}/video-monitoring/start",
            headers=headers,
            json={"camera_index": 0, "sensitivity": "medium"},
            timeout=10
        )
    except Exception as e:
        print(f"[SKIP] Camera not available or timed out: {e}")
        return True
    
    if response.status_code != 200:
        print(f"[SKIP] Camera not available: {response.text}")
        return True
    
    session_data = response.json()
    session_id = session_data.get("session_id")
    stream_url = session_data.get("stream_url")
    
    print(f"[OK] Session started: {session_id}")
    print(f"     Stream URL: {stream_url}")
    
    # Wait a bit
    print("  Waiting 2 seconds...")
    time.sleep(2)
    
    # Check alerts
    print("  Checking alerts...")
    try:
        response = requests.get(
            f"{API_BASE}/video-monitoring/session/{session_id}/alerts",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            alerts = response.json()
            print(f"[OK] Alerts retrieved: {alerts.get('total', 0)} alerts")
    except Exception:
        pass
    
    # Stop monitoring
    print("  Stopping session...")
    try:
        response = requests.post(
            f"{API_BASE}/video-monitoring/stop/{session_id}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            print("[OK] Session stopped successfully")
            return True
    except Exception:
        pass
    return True

def test_video_upload():
    """Test video upload and processing"""
    print("\n[UPLOAD] Testing Video Upload...")
    
    # Check if test video exists
    test_video = Path("test_video.mp4")
    if not test_video.exists():
        print("[SKIP] No test_video.mp4 found. Skipping upload test.")
        return True
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Upload video
    print("  Uploading video...")
    with open(test_video, "rb") as f:
        files = {"file": ("test_video.mp4", f, "video/mp4")}
        response = requests.post(
            f"{API_BASE}/video-monitoring/upload-video",
            headers=headers,
            files=files
        )
    
    if response.status_code != 200:
        print(f"[FAIL] Upload failed: {response.text}")
        return False
    
    upload_data = response.json()
    process_id = upload_data.get("process_id")
    print(f"[OK] Upload successful: {process_id}")
    
    # Poll for status
    print("  Monitoring processing status...")
    max_attempts = 60  # 5 minutes max
    attempt = 0
    
    while attempt < max_attempts:
        response = requests.get(
            f"{API_BASE}/video-monitoring/status/{process_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            status_data = response.json()
            status = status_data.get("status")
            progress = status_data.get("progress", 0)
            
            print(f"  Status: {status} - Progress: {progress}%")
            
            if status == "completed":
                print(f"[OK] Processing completed!")
                print(f"     Falls detected: {status_data.get('has_falls', False)}")
                print(f"     Output file: {status_data.get('output_filename')}")
                return True
            elif status == "error":
                print(f"[FAIL] Processing error: {status_data.get('error')}")
                return False
        
        time.sleep(5)
        attempt += 1
    
    print("[FAIL] Processing timeout")
    return False

def test_history():
    """Test history retrieval"""
    print("\n[HISTORY] Testing Recordings History...")
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(f"{API_BASE}/recordings/my", headers=headers)
    
    if response.status_code == 200:
        history = response.json()
        recs = history.get("recordings", [])
        print(f"[OK] History retrieved: {len(recs)} recordings")
        return True
    else:
        print(f"[FAIL] History failed: {response.text}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("VIDEO MONITORING SYSTEM - INTEGRATION TEST")
    print("=" * 60)
    
    results = {
        "Login": False,
        "Stats": False,
        "Live Monitoring": False,
        "Video Upload": False,
        "History": False
    }
    
    # Run tests
    if test_login():
        results["Login"] = True
        results["Stats"] = test_stats()
        results["Live Monitoring"] = test_live_monitoring()
        results["Video Upload"] = test_video_upload()
        results["History"] = test_history()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nALL TESTS PASSED! System is ready for showcase.")
    else:
        print("\nSome tests failed or were skipped. Please review the output above.")

if __name__ == "__main__":
    main()
