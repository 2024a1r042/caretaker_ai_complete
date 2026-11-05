"""
Quick diagnostic test for YOLOv8 person detection
Tests if the detector is working properly with your webcam
"""
import cv2
from yolo_detector import PersonDetector
import time

print("="*60)
print("YOLOv8 Person Detection Test")
print("="*60)

# Initialize detector
print("\n1. Loading YOLOv8 model...")
try:
    detector = PersonDetector(model_size='n', confidence_threshold=0.3)  # Lower threshold
    print("   ✓ Model loaded successfully!")
except Exception as e:
    print(f"   ✗ Error loading model: {e}")
    exit(1)

# Open webcam
print("\n2. Opening webcam...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("   ✗ Cannot access webcam!")
    exit(1)
print("   ✓ Webcam opened!")

print("\n3. Starting detection...")
print("   Press 'q' to quit")
print("="*60)

frame_count = 0
detection_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    
    # Run detection every frame
    person_boxes = detector.detect_person(frame)
    
    if person_boxes:
        detection_count += 1
        print(f"\rFrame {frame_count}: {len(person_boxes)} person(s) detected!", end="")
    else:
        print(f"\rFrame {frame_count}: No person detected", end="")
    
    # Draw bounding boxes
    for box in person_boxes:
        x1, y1, x2, y2 = box
        # Draw box
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 3)
        
        # Draw centroid
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        cv2.circle(frame, (cx, cy), 8, (0, 0, 255), -1)
        
        # Add label with confidence
        cv2.putText(frame, "PERSON", (int(x1), int(y1) - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # Add info text
    cv2.putText(frame, f"Frame: {frame_count} | Detections: {detection_count}", 
               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Display
    cv2.imshow('YOLOv8 Detection Test', frame)
    
    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print(f"\n\n{'='*60}")
print(f"Test Complete!")
print(f"Total frames: {frame_count}")
print(f"Frames with person detected: {detection_count}")
print(f"Detection rate: {detection_count/frame_count*100:.1f}%")
print(f"{'='*60}")
