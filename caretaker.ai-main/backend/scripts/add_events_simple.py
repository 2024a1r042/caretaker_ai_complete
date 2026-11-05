"""
Simple script to add audio events using direct SQL approach
"""

import sys
import os
from datetime import datetime, timedelta
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from config import SessionLocal

def add_events():
    db = SessionLocal()
    
    try:
        # First, check if recipient 45 exists
        result = db.execute(text("SELECT id, full_name, caretaker_id FROM care_recipients WHERE id = 45")).fetchone()
        
        if not result:
            print("❌ Recipient 45 not found")
            # Show all recipients
            all_recipients = db.execute(text("SELECT id, full_name FROM care_recipients")).fetchall()
            print("\n📋 Available recipients:")
            for r in all_recipients:
                print(f"   ID {r[0]}: {r[1]}")
            return
        
        recipient_id = result[0]
        recipient_name = result[1]
        caretaker_id = result[2]
        
        print(f"✅ Found recipient: {recipient_name} (ID: {recipient_id})")
        print(f"✅ Caretaker ID: {caretaker_id}")
        
        # Clear existing events
        db.execute(text("DELETE FROM audio_events WHERE care_recipient_id = :rid"), {"rid": recipient_id})
        db.commit()
        print("🗑️  Cleared existing events")
        
        # Generate events
        now = datetime.utcnow()
        events_added = 0
        
        event_types = ['Cough', 'Sneeze', 'Talking', 'Noise']
        weights = [60, 25, 10, 5]
        
        for days_ago in range(30):
            date = now - timedelta(days=days_ago)
            num_events = random.randint(2, 8)
            
            for _ in range(num_events):
                hour = random.randint(6, 22)  # Between 6am and 10pm
                minute = random.randint(0, 59)
                
                event_time = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                event_type = random.choices(event_types, weights=weights)[0]
                confidence = round(random.uniform(65.0, 95.0), 2)
                
                db.execute(text("""
                    INSERT INTO audio_events 
                    (caretaker_id, care_recipient_id, event_type, confidence, detected_at, duration_ms)
                    VALUES (:cid, :rid, :etype, :conf, :dt, 500)
                """), {
                    "cid": caretaker_id,
                    "rid": recipient_id,
                    "etype": event_type,
                    "conf": confidence,
                    "dt": event_time
                })
                events_added += 1
        
        db.commit()
        
        # Verify
        count = db.execute(text("SELECT COUNT(*) FROM audio_events WHERE care_recipient_id = :rid"), 
                          {"rid": recipient_id}).scalar()
        
        print(f"\n✅ Successfully added {events_added} events!")
        print(f"✅ Verified: {count} events in database")
        
        # Show breakdown
        breakdown = db.execute(text("""
            SELECT event_type, COUNT(*) as count 
            FROM audio_events 
            WHERE care_recipient_id = :rid 
            GROUP BY event_type
        """), {"rid": recipient_id}).fetchall()
        
        print(f"\n📊 Breakdown:")
        for row in breakdown:
            print(f"   {row[0]}: {row[1]}")
        
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
    print("Adding Audio Events for Recipient 45")
    print("=" * 60)
    add_events()
    print("=" * 60)
