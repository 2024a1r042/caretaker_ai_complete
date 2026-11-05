"""
Add sample audio events data for a specific recipient ID.
This script creates realistic audio detection events for recipient ID 45.
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

def add_sample_audio_events_for_recipient(recipient_id=45):
    """Add sample audio events for a specific recipient"""
    db = SessionLocal()
    
    try:
        # Get the recipient
        recipient = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
        
        if not recipient:
            print(f"❌ No care recipient found with ID {recipient_id}")
            return
        
        caretaker = db.query(CareTaker).filter(CareTaker.id == recipient.caretaker_id).first()
        
        if not caretaker:
            print(f"❌ No caretaker found for recipient {recipient_id}")
            return
        
        print(f"✅ Found recipient: {recipient.full_name} (ID: {recipient_id})")
        print(f"✅ Caretaker: {caretaker.username}")
        
        # Clear existing events for this recipient
        existing_count = db.query(AudioEvent).filter(
            AudioEvent.care_recipient_id == recipient_id
        ).count()
        
        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing events. Clearing...")
            db.query(AudioEvent).filter(
                AudioEvent.care_recipient_id == recipient_id
            ).delete()
            db.commit()
        
        # Generate sample events over the last 30 days
        events_to_create = []
        now = datetime.utcnow()
        
        print(f"\n📊 Generating sample events...")
        
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
                    care_recipient_id=recipient_id,
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
        print(f"\n   👤 Linked to recipient: {recipient.full_name} (ID: {recipient_id})")
        print(f"   📅 Date range: {(now - timedelta(days=29)).date()} to {now.date()}")
        print(f"\n✨ Refresh your profile page to see the data!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Adding Sample Audio Events for Recipient ID 45")
    print("=" * 60)
    add_sample_audio_events_for_recipient(recipient_id=45)
    print("=" * 60)
