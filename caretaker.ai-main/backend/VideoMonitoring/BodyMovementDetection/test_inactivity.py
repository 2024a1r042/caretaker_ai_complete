"""
Test script for Inactivity Monitor
Tests the core logic without requiring webcam.
"""
import sys
import io
# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from inactivity_monitor import InactivityMonitor
import time


def test_inactivity_detection():
    """Test the inactivity detection logic."""
    print("="*60)
    print("Testing Inactivity Monitor")
    print("="*60)
    
    # Create monitor with short threshold for testing (30 seconds)
    monitor = InactivityMonitor(
        safety_threshold_seconds=30,
        grace_period_seconds=3,
        stability_percentage=0.10
    )
    
    print("\n1. Testing initial detection...")
    # Simulate person detected at position (100, 100) with width 200
    boxes = [(50, 50, 250, 250)]  # x1, y1, x2, y2
    status = monitor.update(boxes, time.time())
    print(f"   Status: {status['status']}")
    assert status['person_detected'] == True
    print("   ✓ Person detected correctly")
    
    print("\n2. Testing stability (person remains still)...")
    start_time = time.time()
    for i in range(5):
        # Person stays in same position (with minor jitter)
        boxes = [(48 + i, 48 + i, 252 + i, 252 + i)]
        current_time = start_time + (i * 2)  # 2 seconds apart
        status = monitor.update(boxes, current_time)
        print(f"   t={i*2}s: {status['status']} | Inactive: {status['time_inactive']:.1f}s")
    
    assert status['time_inactive'] > 0
    print("   ✓ Inactivity timer increasing correctly")
    
    print("\n3. Testing movement detection...")
    # Person moves significantly (centroid shifts by >10% of width)
    boxes = [(150, 150, 350, 350)]  # Moved 100 pixels
    status = monitor.update(boxes, time.time())
    print(f"   Status: {status['status']}")
    assert status['time_inactive'] == 0
    print("   ✓ Timer reset on movement")
    
    print("\n4. Testing alert trigger...")
    # Simulate 35 seconds of inactivity
    start_time = time.time()
    boxes = [(50, 50, 250, 250)]
    for i in range(8):
        current_time = start_time + (i * 5)
        status = monitor.update(boxes, current_time)
        if i == 7:  # After 35 seconds
            print(f"   t={i*5}s: {status['status']}")
            print(f"   Alert triggered: {status['alert']}")
    
    assert status['alert'] == True
    print("   ✓ Alert triggered after threshold")
    
    print("\n5. Testing grace period (temporary detection loss)...")
    monitor.reset()
    boxes = [(50, 50, 250, 250)]
    t0 = time.time()
    
    # Person detected
    status = monitor.update(boxes, t0)
    print(f"   t=0s: Person detected")
    
    # Person temporarily lost (within grace period)
    status = monitor.update([], t0 + 2)
    print(f"   t=2s: {status['status']}")
    
    # Person reappears
    status = monitor.update(boxes, t0 + 4)
    print(f"   t=4s: {status['status']}")
    assert status['person_detected'] == True
    print("   ✓ Grace period working correctly")
    
    print("\n6. Testing person leaving (beyond grace period)...")
    # Person lost for longer than grace period
    status = monitor.update([], t0 + 10)
    print(f"   t=10s: {status['status']}")
    assert status['person_detected'] == False
    assert status['time_inactive'] == 0
    print("   ✓ State reset when person leaves")
    
    print("\n" + "="*60)
    print("✓ All tests passed!")
    print("="*60)


def test_relative_stability():
    """Test that stability radius scales with box size."""
    print("\n" + "="*60)
    print("Testing Relative Stability Radius")
    print("="*60)
    
    monitor = InactivityMonitor(stability_percentage=0.10)
    
    print("\n1. Small bounding box (width=100)...")
    boxes = [(0, 0, 100, 100)]  # Width 100, centroid at (50, 50)
    status = monitor.update(boxes, time.time())
    
    # Move 8 pixels (8% of width) - should be stable
    boxes = [(8, 8, 108, 108)]  # Centroid at (58, 58)
    status = monitor.update(boxes, time.time() + 1)
    print(f"   Moved 8px (8% of width): {status['status']}")
    assert status['time_inactive'] > 0
    print("   ✓ Small movement ignored")
    
    print("\n2. Large bounding box (width=400)...")
    monitor.reset()
    boxes = [(0, 0, 400, 400)]  # Width 400, centroid at (200, 200)
    status = monitor.update(boxes, time.time())
    
    # Move 30 pixels (7.5% of width) - should be stable
    boxes = [(30, 30, 430, 430)]  # Centroid at (230, 230)
    status = monitor.update(boxes, time.time() + 1)
    print(f"   Moved 30px (7.5% of width): {status['status']}")
    assert status['time_inactive'] > 0
    print("   ✓ Radius scales with box size")
    
    print("\n" + "="*60)
    print("✓ Relative stability tests passed!")
    print("="*60)


if __name__ == "__main__":
    test_inactivity_detection()
    test_relative_stability()
    print("\n🎉 All tests completed successfully!")
