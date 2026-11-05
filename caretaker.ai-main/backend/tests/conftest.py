"""
Test setup: an isolated SQLite database (no PostgreSQL needed), all ORM tables
created, and one caretaker + care recipient to work with.
Run from backend/:   python -m pytest tests -q
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="caretaker_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["GEMINI_API_KEY"] = ""          # never call the real LLM from tests

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "VideoMonitoring"))

import pytest  # noqa: E402

import tables.users, tables.recordings, tables.medical_reports, tables.video_analysis, tables.vital_signs  # noqa
import tables.audio_events, tables.medical_conditions, tables.disease_dictionary, tables.conversation_history  # noqa
import tables.environment, tables.medications, tables.medication_dose_logs, tables.allergies, tables.admin  # noqa
import tables.thresholds, tables.weekly_reports, tables.medical_recommendations, tables.personalization, tables.safety_events  # noqa
from config import Base, SessionLocal, engine  # noqa: E402

Base.metadata.create_all(bind=engine)


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def people(db):
    """A caretaker (son) and his mother, the care recipient. Fresh per test."""
    import uuid
    from tables.users import CareTaker, CareRecipient
    tag = uuid.uuid4().hex[:6]
    ct = CareTaker(email=f"rahul{tag}@example.com", username=f"rahul{tag}", phone_number=str(9000000000 + int(tag, 16) % 99999999)[:10],
                   password="x", full_name="Rahul Sharma")
    db.add(ct)
    db.commit()
    rec = CareRecipient(caretaker_id=ct.id, full_name="Kamla Devi Sharma", email=f"kamla{tag}@example.com",
                        phone_number=str(8000000000 + int(tag, 16) % 99999999)[:10], age=78, city="Jammu")
    db.add(rec)
    db.commit()
    return ct, rec


@pytest.fixture()
def token(people):
    from repository.users import JWTRepo
    return JWTRepo.generate_token({"sub": people[0].username})
