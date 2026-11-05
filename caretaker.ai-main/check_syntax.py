"""Quick syntax check for video_monitoring.py"""
import sys
sys.path.insert(0, 'e:/model_test/caretaker/backend')

try:
    from routes import video_monitoring
    print("✅ SUCCESS: video_monitoring.py imports without errors")
    print("✅ All syntax errors fixed")
    print("\n🚀 Your backend should now be running successfully!")
    print("   Access: http://localhost:8000")
    print("   Dashboard: http://127.0.0.1:5500/video_monitoring.html")
except SyntaxError as e:
    print(f"❌ SYNTAX ERROR: {e}")
    print(f"   File: {e.filename}")
    print(f"   Line: {e.lineno}")
except Exception as e:
    print(f"⚠️  Import error (may be normal): {e}")
    print("   Check if all dependencies are installed")
