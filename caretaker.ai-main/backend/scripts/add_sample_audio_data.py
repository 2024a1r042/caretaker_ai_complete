"""
Add sample audio events data to the database for prototype demonstration.
This script creates realistic audio detection events across different times and days.
"""

import sys
import os
from datetime import datetime, timedelta
import random

# Add parent directory to path to import from backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SessionLocal
from tables.audio_events import AudioEvent, AudioEventType
from tables.users import CareTaker, CareRecipient

def add_sample_audio_events():
    """Add sample audio events for demonstration"""
    db = SessionLocal()
    
    try:
        # Get the first caretaker and recipient
        caretaker = db.query(CareTaker).first()
        if not caretaker:
            print("❌ No caretaker found. Please create a user first.")
            return
        
        recipient = db.query(CareRecipient).filter(
            CareRecipient.caretaker_id == caretaker.id
        ).first()
        
        if not recipient:
            print("❌ No care recipient found. Please create a recipient first.")
            return
        
        print(f"✅ Found caretaker: {caretaker.username}")
        print(f"✅ Found recipient: {recipient.full_name}")
        
        # Clear existing sample data (optional)
        existing_count = db.query(AudioEvent).filter(
            AudioEvent.caretaker_id == caretaker.id
        ).count()
        
        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing events. Clearing...")
            db.query(AudioEvent).filter(
                AudioEvent.caretaker_id == caretaker.id
            ).delete()
            db.commit()
        
        # Generate sample events over the last 30 days
        events_to_create = []
        now = datetime.utcnow()
        
        # Define realistic patterns
        # More coughs in morning (6-10am) and evening (6-10pm)
        # Sneezes more random throughout the day
        # Some talking and noise events
        
        for days_ago in range(30):
            date = now - timedelta(days=days_ago)
            
            # Vary the number of events per day (2-8 events)
            num_events = random.randint(2, 8)
            
            for _ in range(num_events):
                # Random hour with weighted distribution
                hour = random.choices(
                    range(24),
                    weights=[
                        1, 1, 1, 1, 1, 2,  # 0-5am: low
                        5, 8, 6, 4, 3, 2,  # 6-11am: morning peak
                        2, 2, 3, 3, 4, 5,  # 12-5pm: afternoon
                        8, 9, 7, 5, 3, 2   # 6-11pm: evening peak
                    ]
                )[0]
                
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                
                event_time = date.replace(
                    hour=hour,
                    minute=minute,
                    second=second,
                    microsecond=0
                )
                
                # Event type distribution: 60% cough, 25% sneeze, 10% talking, 5% noise
                event_type_choice = random.choices(
                    [AudioEventType.cough, AudioEventType.sneeze, 
                     AudioEventType.talking, AudioEventType.noise],
                    weights=[60, 25, 10, 5]
                )[0]
                
                # Confidence varies by type
                if event_type_choice == AudioEventType.cough:
                    confidence = random.uniform(65.0, 95.0)
                elif event_type_choice == AudioEventType.sneeze:
                    confidence = random.uniform(70.0, 98.0)
                elif event_type_choice == AudioEventType.talking:
                    confidence = random.uniform(60.0, 85.0)
                else:  # noise
                    confidence = random.uniform(55.0, 75.0)
                
                event = AudioEvent(
                    caretaker_id=caretaker.id,
                    care_recipient_id=recipient.id,
                    event_type=event_type_choice,
                    confidence=round(confidence, 2),
                    detected_at=event_time,
                    duration_ms=500
                )
                
                events_to_create.append(event)
        
        # Bulk insert
        db.bulk_save_objects(events_to_create)
        db.commit()
        
        # Print summary
        total_events = len(events_to_create)
        cough_count = sum(1 for e in events_to_create if e.event_type == AudioEventType.cough)
        sneeze_count = sum(1 for e in events_to_create if e.event_type == AudioEventType.sneeze)
        talking_count = sum(1 for e in events_to_create if e.event_type == AudioEventType.talking)
        noise_count = sum(1 for e in events_to_create if e.event_type == AudioEventType.noise)
        
        print(f"\n✅ Successfully added {total_events} sample audio events!")
        print(f"   📊 Breakdown:")
        print(f"      🤧 Coughs: {cough_count}")
        print(f"      🤧 Sneezes: {sneeze_count}")
        print(f"      🗣️  Talking: {talking_count}")
        print(f"      🔊 Noise: {noise_count}")
        print(f"\n   👤 Linked to recipient: {recipient.full_name}")
        print(f"   📅 Date range: {(now - timedelta(days=29)).date()} to {now.date()}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Adding Sample Audio Events Data")
    print("=" * 60)
    add_sample_audio_events()
    print("=" * 60)
