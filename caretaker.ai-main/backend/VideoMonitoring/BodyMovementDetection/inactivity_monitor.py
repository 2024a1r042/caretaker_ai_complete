"""
Inactivity Monitor - Core Logic for Elderly Monitoring System
Tracks person's position stability over time to detect prolonged inactivity.
"""
import time
import math
from collections import deque


class InactivityMonitor:
    """
    Monitors a person's position stability to detect prolonged inactivity.
    Uses centroid tracking with relative stability radius to ignore minor movements.
    """
    
    def __init__(self, 
                 safety_threshold_seconds=1800,  # 30 minutes default
                 grace_period_seconds=5,          # 5 seconds grace for detection loss
                 stability_percentage=0.10):       # 10% of box width
        """
        Initialize the inactivity monitor.
        
        Args:
            safety_threshold_seconds: Time in seconds before triggering alert
            grace_period_seconds: Time to wait before resetting when person not detected
            stability_percentage: Percentage of bounding box width for stability radius
        """
        self.safety_threshold = safety_threshold_seconds
        self.grace_period = grace_period_seconds
        self.stability_percentage = stability_percentage
        
        # State tracking
        self.anchor_position = None  # (x, y) reference point
        self.last_detection_time = None
        self.inactivity_start_time = None
        self.time_inactive = 0  # Total seconds inactive
        self.is_person_present = False
        self.last_box_width = None
        
        # Smoothing for centroid (reduces jitter)
        self.centroid_history = deque(maxlen=3)  # Moving average over 3 frames
        
        # Alert state
        self.alert_triggered = False
        
        # External sensor integration
        self.is_sleeping_external = False
        
    def set_external_sleep_status(self, is_sleeping):
        """
        Update sleep status from external sensor.
        Args:
            is_sleeping (bool): True if sensor detects sleep, False otherwise
        """
        self.is_sleeping_external = is_sleeping
        
    def update(self, detected_boxes, current_time=None):
        """
        Update the monitor with new detection results.
        
        Args:
            detected_boxes: List of bounding boxes [(x1, y1, x2, y2), ...] or None/empty
            current_time: Current timestamp (defaults to time.time())
            
        Returns:
            dict: Status information {
                'person_detected': bool,
                'time_inactive': float (seconds),
                'alert': bool,
                'status': str (description)
            }
        """
        if current_time is None:
            current_time = time.time()
        
        selected_box = None
        
        # Scenario 1: We are already tracking someone
        if self.is_person_present and self.centroid_history:
            # Get last known position (most recent centroid)
            last_cx, last_cy = self.centroid_history[-1]
            
            # Find the box whose centroid is closest to our last known position
            closest_dist = float('inf')
            
            for box in detected_boxes:
                bx1, by1, bx2, by2 = box
                bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
                
                dist = math.sqrt((bcx - last_cx)**2 + (bcy - last_cy)**2)
                
                # Check if this person is reasonably close (not a random teleport)
                # Using a loose threshold (e.g. 200px jump) allowed frame-to-frame
                if dist < closest_dist:
                    closest_dist = dist
                    selected_box = box
            
            # If the closest person is too far, assume our person is lost/occluded
            # and what we see is someone else. (Threshold could be tuned)
            if closest_dist > 300:  # If closest person is >300px away
                selected_box = None
                
        # Scenario 2: diverse - Not tracking anyone yet
        elif detected_boxes:
            # Pick the LARGEST box (closest/main subject)
            largest_area = 0
            for box in detected_boxes:
                bx1, by1, bx2, by2 = box
                area = (bx2 - bx1) * (by2 - by1)
                if area > largest_area:
                    largest_area = area
                    selected_box = box
        
        # Process the selected person
        if selected_box is not None:
            return self._handle_person_detected(selected_box, current_time)
        else:
            return self._handle_person_not_detected(current_time)
    
    def _handle_person_detected(self, box, current_time):
        """Handle case when person is detected."""
        x1, y1, x2, y2 = box
        
        # Calculate centroid and box width
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        width = x2 - x1
        
        # Use EXTERNAL SENSOR flag for sleep status
        # Defaults to False unless set via set_location_status or similar
        is_sleeping = self.is_sleeping_external
        
        if is_sleeping:
            posture = "Sleeping (Sensor)"
            current_threshold = self.safety_threshold * 4
        else:
            posture = "Active/Monitoring"
            current_threshold = self.safety_threshold
        
        # Add to history for smoothing
        self.centroid_history.append((cx, cy))
        
        # Calculate smoothed centroid
        smoothed_cx = sum(c[0] for c in self.centroid_history) / len(self.centroid_history)
        smoothed_cy = sum(c[1] for c in self.centroid_history) / len(self.centroid_history)
        
        # Update state
        self.is_person_present = True
        self.last_detection_time = current_time
        
        # Initialize anchor if first detection
        if self.anchor_position is None:
            self.anchor_position = (smoothed_cx, smoothed_cy)
            self.inactivity_start_time = current_time
            return self._get_status(f"Person detected ({posture})", box, posture)
        
        # Calculate distance from anchor (MOVEMENT CHECK only)
        # Removed Shape Check as requested
        distance = math.sqrt(
            (smoothed_cx - self.anchor_position[0])**2 + 
            (smoothed_cy - self.anchor_position[1])**2
        )
        # Calculate stability radius (relative to box width)
        stability_radius = width * self.stability_percentage
        
        # Stability Check (Distance only)
        if distance < stability_radius:
            # Person is STILL
            if self.inactivity_start_time is not None:
                self.time_inactive = current_time - self.inactivity_start_time
            
            # Check alert
            if self.time_inactive >= current_threshold:
                self.alert_triggered = True
                return self._get_status(f"⚠️ ALERT: Inactive for {int(self.time_inactive)}s ({posture})", box, posture)
            else:
                seconds = int(self.time_inactive)
                if is_sleeping:
                    status_msg = f"Sleeping (Sensor Mode): {seconds}s"
                else:
                    status_msg = f"Monitoring: {seconds}s"
                return self._get_status(status_msg, box, posture)
        else:
            # MOVEMENT detected
            self.anchor_position = (smoothed_cx, smoothed_cy)
            self.inactivity_start_time = current_time
            self.time_inactive = 0
            self.alert_triggered = False
            self.centroid_history.clear()
            
            return self._get_status("Movement detected - timer reset", box, posture="Moving")
    
    def _handle_person_not_detected(self, current_time):
        """Handle case when person is not detected."""
        if not self.is_person_present:
            # Was already not present
            return self._get_status("No person detected")
        
        # Person was present but now missing
        if self.last_detection_time is None:
            time_since_last = 0
        else:
            time_since_last = current_time - self.last_detection_time
        
        if time_since_last < self.grace_period:
            # Within grace period - maintain state
            if self.inactivity_start_time is not None:
                self.time_inactive = current_time - self.inactivity_start_time
            return self._get_status("Person temporarily lost (grace period)")
        else:
            # Grace period exceeded - person left
            self._reset_state()
            return self._get_status("Person left - monitoring reset")
    
    def _reset_state(self):
        """Reset all tracking state."""
        self.anchor_position = None
        self.inactivity_start_time = None
        self.time_inactive = 0
        self.is_person_present = False
        self.alert_triggered = False
        self.centroid_history.clear()
    
    def _get_status(self, message, box=None, posture=None):
        """Generate status dictionary."""
        return {
            'person_detected': self.is_person_present,
            'time_inactive': self.time_inactive,
            'time_inactive_minutes': int(self.time_inactive / 60),
            'time_inactive_seconds': int(self.time_inactive),
            'alert': self.alert_triggered,
            'status': message,
            'tracked_box': box,
            'posture': posture
        }

    
    def reset(self):
        """Manually reset the monitor."""
        self._reset_state()
    
    def set_safety_threshold(self, seconds):
        """Update the safety threshold."""
        self.safety_threshold = seconds
