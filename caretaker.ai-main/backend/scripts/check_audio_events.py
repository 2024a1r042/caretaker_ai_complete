"""
Check if audio events exist in the database for recipient 45
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SessionLocal
from tables.audio_events import AudioEvent
from tables.users import CareRecipient

db = SessionLocal()

try:
    # Check recipient 45
    recipient = db.query(CareRecipient).filter(CareRecipient.id == 45).first()
    
    if recipient:
        print(f"✅ Recipient found: {recipient.full_name} (ID: 45)")
        
        # Count events
        events = db.query(AudioEvent).filter(
            AudioEvent.care_recipient_id == 45
        ).all()
        
        print(f"\n📊 Audio Events for Recipient 45:")
        print(f"   Total events: {len(events)}")
        
        if events:
            from collections import Counter
            types = Counter(e.event_type.value for e in events)
            print(f"\n   Breakdown:")
            for event_type, count in types.items():
                print(f"      {event_type}: {count}")
            
            print(f"\n   Latest 5 events:")
            for e in sorted(events, key=lambda x: x.detected_at, reverse=True)[:5]:
                print(f"      {e.detected_at} - {e.event_type.value} ({e.confidence}%)")
        else:
            print("   ❌ No events found!")
    else:
        print(f"❌ Recipient 45 not found")
        
        # Show all recipients
        all_recipients = db.query(CareRecipient).all()
        print(f"\n📋 All recipients in database:")
        for r in all_recipients:
            event_count = db.query(AudioEvent).filter(
                AudioEvent.care_recipient_id == r.id
            ).count()
            print(f"   ID {r.id}: {r.full_name} - {event_count} events")
            
finally:
    db.close()
