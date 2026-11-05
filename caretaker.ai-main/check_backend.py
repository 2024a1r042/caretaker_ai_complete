"""
Simple backend health check
"""
import requests
import sys

def check_backend():
    """Check if backend is running and responding"""
    try:
        print("🔍 Checking backend health...")
        response = requests.get("http://localhost:8000/", timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Backend is running!")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            print(f"\n🎯 Your system is ready for showcase!")
            print(f"   Backend: http://localhost:8000")
            print(f"   Dashboard: http://127.0.0.1:5500/video_monitoring.html")
            return True
        else:
            print(f"⚠️  Backend responded with status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend on port 8000")
        print("   Make sure uvicorn is running:")
        print("   cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = check_backend()
    sys.exit(0 if success else 1)
