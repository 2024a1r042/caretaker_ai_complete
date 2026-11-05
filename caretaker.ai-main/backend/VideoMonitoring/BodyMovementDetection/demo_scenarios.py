"""
Demo script - Simulates inactivity detection without webcam
Shows how the system responds to different scenarios
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from inactivity_monitor import InactivityMonitor
import time


def print_status(status, scenario):
    """Pretty print status."""
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario}")
    print(f"{'='*60}")
    print(f"Person Detected: {status['person_detected']}")
    print(f"Time Inactive: {status['time_inactive_minutes']} minutes ({status['time_inactive']:.1f} seconds)")
    print(f"Alert: {'🚨 YES' if status['alert'] else '✓ No'}")
    print(f"Status: {status['status']}")
    print(f"{'='*60}")


def demo_normal_monitoring():
    """Demo: Normal monitoring scenario."""
    print("\n" + "🎬 DEMO 1: Normal Monitoring (Person Sitting Still)")
    print("="*60)
    
    monitor = InactivityMonitor(
        safety_threshold_seconds=60,  # 1 minute for demo
        stability_percentage=0.10
    )
    
    # Person sitting in chair
    sitting_box = [(100, 100, 300, 300)]
    
    print("\nPerson sits down in chair...")
    status = monitor.update(sitting_box, time.time())
    print(f"  → {status['status']}")
    
    # Simulate 30 seconds of sitting
    print("\n⏱️  30 seconds pass (person remains still)...")
    time.sleep(0.5)  # Simulate
    status = monitor.update(sitting_box, time.time() + 30)
    print(f"  → Inactive for {status['time_inactive']:.0f} seconds")
    
    # Simulate 70 seconds total (exceeds 60s threshold)
    print("\n⏱️  70 seconds total (exceeds 60s threshold)...")
    time.sleep(0.5)
    status = monitor.update(sitting_box, time.time() + 70)
    print_status(status, "Alert Triggered")


def demo_movement_reset():
    """Demo: Person moves, timer resets."""
    print("\n\n🎬 DEMO 2: Movement Detection (Timer Reset)")
    print("="*60)
    
    monitor = InactivityMonitor(safety_threshold_seconds=60)
    
    # Person sitting
    sitting_box = [(100, 100, 300, 300)]
    t0 = time.time()
    
    print("\nPerson sits down...")
    monitor.update(sitting_box, t0)
    
    print("\n⏱️  40 seconds pass...")
    status = monitor.update(sitting_box, t0 + 40)
    print(f"  → Inactive for {status['time_inactive']:.0f} seconds")
    
    print("\n🚶 Person stands up and walks to kitchen...")
    # Bounding box moves significantly
    standing_box = [(300, 50, 500, 400)]
    status = monitor.update(standing_box, t0 + 45)
    print_status(status, "Movement Detected - Timer Reset")


def demo_minor_movements():
    """Demo: Minor movements are ignored."""
    print("\n\n🎬 DEMO 3: Minor Movements Ignored")
    print("="*60)
    
    monitor = InactivityMonitor(safety_threshold_seconds=60)
    
    t0 = time.time()
    
    print("\nPerson sitting in chair (200x200 box)...")
    box = [(100, 100, 300, 300)]  # Width 200, centroid at (200, 200)
    monitor.update(box, t0)
    
    print("\n⏱️  10 seconds: Person waves arm...")
    # Small shift (5 pixels = 2.5% of width)
    box = [(105, 105, 305, 305)]  # Centroid at (205, 205)
    status = monitor.update(box, t0 + 10)
    print(f"  → {status['status']}")
    print(f"  → Timer continues: {status['time_inactive']:.0f}s")
    
    print("\n⏱️  20 seconds: Person turns head...")
    # Another small shift
    box = [(103, 107, 303, 307)]
    status = monitor.update(box, t0 + 20)
    print(f"  → {status['status']}")
    print(f"  → Timer continues: {status['time_inactive']:.0f}s")
    
    print("\n⏱️  30 seconds: Person adjusts posture slightly...")
    box = [(98, 102, 298, 302)]
    status = monitor.update(box, t0 + 30)
    print_status(status, "Minor Movements Ignored - Timer Running")


def demo_grace_period():
    """Demo: Grace period prevents false resets."""
    print("\n\n🎬 DEMO 4: Grace Period (Temporary Detection Loss)")
    print("="*60)
    
    monitor = InactivityMonitor(
        safety_threshold_seconds=60,
        grace_period_seconds=5
    )
    
    box = [(100, 100, 300, 300)]
    t0 = time.time()
    
    print("\nPerson detected and sitting...")
    monitor.update(box, t0)
    
    print("\n⏱️  20 seconds: Still sitting...")
    status = monitor.update(box, t0 + 20)
    print(f"  → Inactive: {status['time_inactive']:.0f}s")
    
    print("\n⚠️  22 seconds: Camera briefly loses detection (shadow/lighting)...")
    status = monitor.update([], t0 + 22)  # No detection
    print(f"  → {status['status']}")
    
    print("\n⏱️  24 seconds: Person detected again...")
    status = monitor.update(box, t0 + 24)
    print(f"  → {status['status']}")
    print(f"  → Timer preserved: {status['time_inactive']:.0f}s")
    
    print_status(status, "Grace Period Prevented False Reset")


def demo_person_leaves():
    """Demo: Person leaves room."""
    print("\n\n🎬 DEMO 5: Person Leaves Room")
    print("="*60)
    
    monitor = InactivityMonitor(grace_period_seconds=5)
    
    box = [(100, 100, 300, 300)]
    t0 = time.time()
    
    print("\nPerson sitting...")
    monitor.update(box, t0)
    
    print("\n⏱️  30 seconds: Still sitting...")
    status = monitor.update(box, t0 + 30)
    print(f"  → Inactive: {status['time_inactive']:.0f}s")
    
    print("\n🚪 Person walks out of frame...")
    print("   (No detection for 10 seconds - exceeds grace period)")
    status = monitor.update([], t0 + 40)
    print_status(status, "Person Left - Monitoring Reset")


def demo_relative_radius():
    """Demo: Stability radius scales with distance."""
    print("\n\n🎬 DEMO 6: Relative Stability Radius")
    print("="*60)
    
    monitor = InactivityMonitor(stability_percentage=0.10)
    
    print("\nScenario A: Person far from camera (small box)")
    print("  Box width: 100 pixels")
    print("  Stability radius: 10 pixels (10% of 100)")
    
    box = [(0, 0, 100, 100)]
    t0 = time.time()
    monitor.update(box, t0)
    
    print("\n  Movement of 8 pixels...")
    box = [(8, 8, 108, 108)]
    status = monitor.update(box, t0 + 10)
    print(f"  → {status['status']}")
    
    print("\n" + "-"*60)
    
    monitor.reset()
    print("\nScenario B: Person close to camera (large box)")
    print("  Box width: 400 pixels")
    print("  Stability radius: 40 pixels (10% of 400)")
    
    box = [(0, 0, 400, 400)]
    monitor.update(box, t0)
    
    print("\n  Movement of 30 pixels...")
    box = [(30, 30, 430, 430)]
    status = monitor.update(box, t0 + 10)
    print(f"  → {status['status']}")
    
    print("\n✓ Same relative movement (7.5%) treated consistently!")


if __name__ == "__main__":
    print("\n" + "🎭"*30)
    print("ELDERLY INACTIVITY MONITOR - INTERACTIVE DEMO")
    print("🎭"*30)
    
    demo_normal_monitoring()
    input("\n\nPress Enter to continue to next demo...")
    
    demo_movement_reset()
    input("\n\nPress Enter to continue to next demo...")
    
    demo_minor_movements()
    input("\n\nPress Enter to continue to next demo...")
    
    demo_grace_period()
    input("\n\nPress Enter to continue to next demo...")
    
    demo_person_leaves()
    input("\n\nPress Enter to continue to next demo...")
    
    demo_relative_radius()
    
    print("\n\n" + "="*60)
    print("✅ Demo Complete!")
    print("="*60)
    print("\nTo run the actual system with webcam:")
    print("  python elderly_monitor_main.py")
    print("="*60)
