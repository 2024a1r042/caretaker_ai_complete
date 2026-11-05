"""
YOLOv8 Person Detection Module
Lightweight and fast person detection using YOLOv8.
"""
from ultralytics import YOLO
import cv2
import numpy as np


class PersonDetector:
    """
    YOLOv8-based person detector optimized for real-time monitoring.
    """
    
    def __init__(self, model_size='n', confidence_threshold=0.5):
        """
        Initialize the YOLOv8 detector.
        
        Args:
            model_size: YOLO model size ('n', 's', 'm', 'l', 'x')
                       'n' = nano (fastest), 'x' = extra large (most accurate)
            confidence_threshold: Minimum confidence for detections (0-1)
        """
        self.confidence_threshold = confidence_threshold
        
        # Load YOLOv8 model (will auto-download on first use)
        print(f"Loading YOLOv8{model_size} model...")
        self.model = YOLO(f'yolov8{model_size}.pt')
        
        # COCO class ID for 'person' is 0
        self.person_class_id = 0
        
        print("YOLOv8 model loaded successfully!")
    
    def detect_person(self, frame):
        """
        Detect person in a frame.
        
        Args:
            frame: OpenCV image (BGR format) or numpy array
            
        Returns:
            list: List of bounding boxes [(x1, y1, x2, y2), ...] for detected persons
                  Returns empty list if no person detected
        """
        # Run inference
        results = self.model(frame, verbose=False, conf=self.confidence_threshold)
        
        # Extract person detections
        person_boxes = []
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Check if detection is a person (class 0)
                if int(box.cls[0]) == self.person_class_id:
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    person_boxes.append((float(x1), float(y1), float(x2), float(y2)))
        
        return person_boxes
    
    def detect_and_draw(self, frame):
        """
        Detect person and draw bounding boxes on frame.
        
        Args:
            frame: OpenCV image (BGR format)
            
        Returns:
            tuple: (annotated_frame, person_boxes)
        """
        person_boxes = self.detect_person(frame)
        annotated_frame = frame.copy()
        
        for box in person_boxes:
            x1, y1, x2, y2 = box
            # Draw bounding box
            cv2.rectangle(annotated_frame, 
                         (int(x1), int(y1)), 
                         (int(x2), int(y2)), 
                         (0, 255, 0), 2)
            
            # Draw centroid
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cv2.circle(annotated_frame, (cx, cy), 5, (0, 0, 255), -1)
            
            # Add label
            cv2.putText(annotated_frame, "Person", 
                       (int(x1), int(y1) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return annotated_frame, person_boxes
