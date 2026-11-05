import os
from sqlalchemy import create_engine, Column, Integer, String, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

Base = declarative_base()
class CareTaker(Base):
    __tablename__ = 'caretakers'
    id = Column(Integer, primary_key=True)
    username = Column(String)
    email = Column(String)
    phone_number = Column(String)
    password = Column(String)
    full_name = Column(String)

engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)
db = Session()

# Try to insert a duplicate email
try:
    # ID 1 has duplicate-test@example.com
    new_ct = CareTaker(
        username="test_random", 
        email="duplicate-test@example.com", 
        phone_number="9999999999", 
        password="Password@123", 
        full_name="Test"
    )
    db.add(new_ct)
    db.commit()
except Exception as e:
    db.rollback()
    print(f"RAW ERROR: {str(e)}")
