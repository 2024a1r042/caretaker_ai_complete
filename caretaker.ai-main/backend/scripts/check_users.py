"""
Quick script to check if there are users in the database and create a test user if needed.
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SessionLocal
from tables.users import CareTaker, CareRecipient
from repository.users import UsersRepo

def check_and_create_users():
    """Check for existing users and create a test user if needed"""
    db = SessionLocal()
    
    try:
        # Check for existing caretakers
        caretakers = db.query(CareTaker).all()
        
        if not caretakers:
            print("❌ No caretakers found in database!")
            print("\n📝 Creating a test caretaker account...")
            
            # Create test caretaker
            test_user = UsersRepo.create_caretaker(
                db=db,
                full_name="John Doe",
                username="john_doe",
                email="john@example.com",
                password="password123",  # Simple password for testing
                phone_number="+1234567890"
            )
            
            print(f"✅ Test caretaker created!")
            print(f"   Username: john_doe")
            print(f"   Password: password123")
            print(f"   Email: john@example.com")
            
            # Create a test recipient
            recipient = CareRecipient(
                caretaker_id=test_user.id,
                full_name="Jane Doe",
                age=75,
                gender="Female",
                medical_history="Test recipient for prototype"
            )
            db.add(recipient)
            db.commit()
            
            print(f"\n✅ Test recipient created!")
            print(f"   Name: Jane Doe")
            print(f"   Age: 75")
            
        else:
            print(f"✅ Found {len(caretakers)} caretaker(s) in database:")
            for ct in caretakers:
                print(f"\n   👤 {ct.full_name or ct.username}")
                print(f"      Username: {ct.username}")
                print(f"      Email: {ct.email}")
                
                # Check recipients
                recipients = db.query(CareRecipient).filter(
                    CareRecipient.caretaker_id == ct.id
                ).all()
                
                if recipients:
                    print(f"      Recipients: {len(recipients)}")
                    for r in recipients:
                        print(f"         - {r.full_name} (Age: {r.age})")
                else:
                    print(f"      Recipients: None")
        
        print("\n" + "="*60)
        print("To log in to the frontend:")
        print("1. Go to http://localhost:5500/index.html")
        print("2. Use the credentials shown above")
        print("3. Navigate to profile.html")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Checking Database Users")
    print("=" * 60)
    check_and_create_users()
