from config import SessionLocal
from tables.users import CareTaker
from repository.users import JWTRepo

db = SessionLocal()
caretaker = db.query(CareTaker).first()
if caretaker:
    token = JWTRepo.generate_token(caretaker.username)
    print(token)
else:
    print("No caretaker found")
db.close()
