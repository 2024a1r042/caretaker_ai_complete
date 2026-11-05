import sys
import requests
import main  # Imports all models properly

from config import SessionLocal
from tables.users import CareTaker, CareRecipient
from repository.users import JWTRepo

def run():
    db = SessionLocal()
    caretaker = db.query(CareTaker).first()
    recipient = db.query(CareRecipient).filter(CareRecipient.caretaker_id == caretaker.id).first()
    
    if not recipient:
        print("No recipient found")
        return

    from datetime import timedelta
    access_token_expires = timedelta(minutes=100)
    token = JWTRepo.generate_token({"sub": caretaker.username}, expires_delta=access_token_expires)

    url = f"http://127.0.0.1:8000/api/care-recipients/{recipient.id}/profile"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    print(f"Status code: {resp.status_code}")
    print(resp.json())

if __name__ == "__main__":
    run()
