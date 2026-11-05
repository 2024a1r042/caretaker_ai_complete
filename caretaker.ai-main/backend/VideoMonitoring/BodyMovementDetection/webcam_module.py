"""
Webcam Inactivity Monitoring Module
Continuously monitors webcam feed for elderly inactivity detection.
"""
import cv2
import time
import threading
from tkinter import messagebox
from yolo_detector import PersonDetector
from inactivity_monitor import InactivityMonitor


class WebcamInactivityMonitor:
    """
    Manages webcam feed and inactivity monitoring.
    """
    
    def __init__(self, window, 
                 safety_threshold_seconds=30,
                 detection_interval_seconds=1):
        """
        Initialize webcam monitor.
        
        Args:
            window: Parent Tkinter window
            safety_threshold_seconds: Seconds before alert
            detection_interval_seconds: Seconds between detections
        """
        self.window = window
        self.detection_interval = detection_interval_seconds
        
        # Initialize detector and monitor
        self.detector = None  # Lazy load
        self.monitor = InactivityMonitor(
            safety_threshold_seconds=safety_threshold_seconds
        )
        
        # Threading control
        self.running = False
        self.thread = None
        self.cap = None
        
        # Cache last detection to prevent blinking
        self.last_person_boxes = []
        self.last_status = None
        
        # Alert state
        self.alert_sound_played = False
    
    def start(self):
        """Start webcam monitoring."""
        if self.running:
            return
        
        # Initialize detector (lazy load to avoid startup delay)
        if self.detector is None:
            try:
                # Lower confidence threshold for better detection
                self.detector = PersonDetector(model_size='n', confidence_threshold=0.3)
                print("YOLOv8 detector initialized successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load YOLOv8: {str(e)}")
                return
        
        # Open webcam
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Cannot access webcam")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop webcam monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        self.monitor.reset()
    
    def _monitoring_loop(self):
        """Main monitoring loop (runs in separate thread)."""
        last_detection_time = 0
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            
            current_time = time.time()
            
            # Run detection at specified interval
            if current_time - last_detection_time >= self.detection_interval:
                person_boxes = self.detector.detect_person(frame)
                status = self.monitor.update(person_boxes, current_time)
                
                # Cache the detection results
                self.last_person_boxes = person_boxes
                self.last_status = status
                
                # Handle alerts
                if status['alert'] and not self.alert_sound_played:
                    self._trigger_alert(status)
                    self.alert_sound_played = True
                elif not status['alert']:
                    self.alert_sound_played = False
                
                last_detection_time = current_time
            
            # Always display with last known detection (prevents blinking)
            self._update_ui(frame, self.last_person_boxes, self.last_status)
            
            time.sleep(0.03)  # ~30 FPS display
    
    def _update_ui(self, frame, person_boxes, status):
        """Update UI with detection results and status."""
        try:
            # Draw bounding boxes
            display_frame = frame.copy()
            
            # Handle None status (before first detection)
            if status is None:
                status = {
                    'person_detected': False,
                    'time_inactive': 0,
                    'time_inactive_minutes': 0,
                    'alert': False,
                    'status': 'Initializing...'
                }
            
            tracked_box = status.get('tracked_box')
            
            for box in person_boxes:
                x1, y1, x2, y2 = box
                
                # Check if this is the tracked person
                is_tracked = (tracked_box is not None and box == tracked_box)
                
                if is_tracked:
                    # TRACKED PERSON
                    posture = status.get('posture', '')
                    
                    if posture == "Lying Down":
                        # SLEEP MODE: Cyan/Thick
                        color = (255, 255, 0) # Cyan (BGR)
                        thickness = 4
                        label = "SLEEPING"
                    else:
                        # ACTIVE MODE: Green/Thick
                        color = (0, 255, 0)  # Green
                        thickness = 4
                        label = "MONITORED"
                else:
                    # OTHERS: Yellow/Thin
                    color = (0, 255, 255)  # Yellow
                    thickness = 2
                    label = "VISITOR"
                
                # Draw bounding box
                cv2.rectangle(display_frame, 
                            (int(x1), int(y1)), 
                            (int(x2), int(y2)), 
                            color, thickness)
                
                # Draw centroid
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                cv2.circle(display_frame, (cx, cy), 8, (0, 0, 255), -1)
                
                # Add label
                cv2.putText(display_frame, label, 
                           (int(x1), int(y1) - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            
            # Add status text
            self._add_status_overlay(display_frame, status)
            
            # Display
            self._display_frame(display_frame, person_boxes, status)
            
        except Exception as e:
            print(f"UI update error: {e}")
    
    def _add_status_overlay(self, frame, status):
        """Add status information overlay to frame."""
        h, w = frame.shape[:2]
        
        # Background for text
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (w - 10, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Status text
        if status['alert']:
            color = (0, 0, 255)  # Red
            text = "⚠️ ALERT: PROLONGED INACTIVITY"
        elif status['person_detected']:
            color = (0, 255, 0)  # Green
            text = "✓ Monitoring Active"
        else:
            color = (255, 255, 0)  # Yellow
            text = "⚠ No Person Detected"
        
        cv2.putText(frame, text, (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Time inactive
        if 'time_inactive_seconds' in status:
            seconds = status['time_inactive_seconds']
        else:
            seconds = int(status['time_inactive'])
            
        time_text = f"Inactive Time: {seconds} sec"
        cv2.putText(frame, time_text, (20, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Detailed status
        cv2.putText(frame, status['status'], (20, 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    def _display_frame(self, frame, person_boxes, status):
        """Display frame in Tkinter window."""
        try:
            from PIL import Image, ImageTk
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize for display
            display_height = 550
            h, w = rgb_frame.shape[:2]
            display_width = int(w * display_height / h)
            rgb_frame = cv2.resize(rgb_frame, (display_width, display_height))
            
            # Convert to PhotoImage
            img = Image.fromarray(rgb_frame)
            photo = ImageTk.PhotoImage(image=img)
            
            # Update label
            self.window.webcam_frame.configure(image=photo)
            self.window.webcam_frame.image = photo
            
        except Exception as e:
            print(f"Display error: {e}")
    
    def _trigger_alert(self, status):
        """Trigger alert for prolonged inactivity."""
        try:
            # Visual alert (could add sound here)
            print(f"\n{'='*50}")
            print(f"ALERT: Person inactive for {status['time_inactive_seconds']} seconds!")
            print(f"{'='*50}\n")
            
            # Could add: winsound.Beep() on Windows, or play audio file
            
        except Exception as e:
            print(f"Alert error: {e}")
    
    def set_safety_threshold(self, seconds):
        """Update safety threshold."""
        # Now treating input as seconds directly
        self.monitor.set_safety_threshold(seconds)
    
    def reset_monitor(self):
        """Reset the inactivity monitor."""
        self.monitor.reset()
        self.alert_sound_played = False


# Global monitor instance
webcam_monitor = None


def show_webcam(window):
    """Start webcam monitoring (called from UI)."""
    global webcam_monitor
    
    try:
        # Show webcam frame (already placed in the UI)
        # No need to hide other frames - they don't exist in new UI
        
        # Initialize monitor if needed
        if webcam_monitor is None:
            webcam_monitor = WebcamInactivityMonitor(
                window,
                safety_threshold_seconds=30,  # Default 30 seconds
                detection_interval_seconds=1   # Check every 1 second
            )
        
        # Start monitoring
        webcam_monitor.start()
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start webcam: {str(e)}")


def stop_webcam():
    """Stop webcam monitoring."""
    global webcam_monitor
    if webcam_monitor:
        webcam_monitor.stop()
