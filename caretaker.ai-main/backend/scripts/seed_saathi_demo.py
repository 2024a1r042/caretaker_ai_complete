"""
Seed a realistic personal profile + a few learned memories for a demo recipient,
so Saathi is personal from the very first sentence of the demo.

    cd backend
    python scripts/seed_saathi_demo.py --recipient-id 7

Edit the values below to match the real person you demo with — a convincing
demo uses true details (their real bhajan, their grandson's real name).
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import every model so SQLAlchemy can resolve relationships (same set main.py loads)
import importlib  # noqa: E402
for _m in ("users", "recordings", "medical_reports", "video_analysis", "vital_signs", "audio_events",
           "medical_conditions", "disease_dictionary", "conversation_history", "environment", "medications",
           "medication_dose_logs", "allergies", "admin", "thresholds", "weekly_reports", "medical_recommendations",
           "personalization", "safety_events"):
    importlib.import_module(f"tables.{_m}")
from config import Base, SessionLocal, engine  # noqa: E402
from services import personalization as P  # noqa: E402

PROFILE = {
    "preferred_name": "Amma",
    "language_preference": "hi",
    "native_language": "Dogri",
    "hometown": "Jammu",
    "former_occupation": "a maths teacher at a government school for 30 years",
    "faith": "Krishna bhakt — evening aarti at 6:30, Ekadashi fast",
    "favorite_foods": ["aloo paratha", "rajma chawal", "adrak wali chai"],
    "disliked_foods": ["karela"],
    "dietary_notes": "diabetic — chai without sugar, no sweets",
    "favorite_music": ["Achyutam Keshavam", "Lag Jaa Gale", "Kishore Kumar songs"],
    "favorite_shows": ["Ramayan (1987)", "Kaun Banega Crorepati"],
    "hobbies": ["tulsi and rose plants", "knitting sweaters for grandchildren"],
    "family_members": [
        {"name": "Rahul", "relation": "son", "location": "Bangalore", "notes": "video-calls every Sunday",
         "is_emergency_contact": True},
        {"name": "Aarav", "relation": "grandson", "location": "Bangalore", "notes": "class 10, loves cricket"},
        {"name": "Mrs. Gupta", "relation": "neighbour", "location": "next door", "notes": "comes for evening chai"},
    ],
    "important_dates": [{"label": "Aarav's birthday", "date": (dt.date.today() + dt.timedelta(days=1)).strftime("%m-%d")}],
    "daily_routine": [
        {"time": "06:30", "activity": "morning walk in the park", "checkin": True},
        {"time": "08:00", "activity": "breakfast and morning medicines", "checkin": True},
        {"time": "16:00", "activity": "chai with Mrs. Gupta", "checkin": True},
        {"time": "18:30", "activity": "evening aarti", "checkin": True},
    ],
    "life_stories": ["Taught maths in Jammu for 30 years — former students still visit",
                     "Walked to school across the Tawi bridge as a girl"],
    "topics_to_avoid": ["her late husband's illness"],
    "conversation_style": "Slightly hard of hearing — short sentences. Loves gentle humour and being asked for advice.",
    "wake_time": "06:00",
    "sleep_time": "22:00",
}

MEMORIES = [
    ("health", "Left knee hurts when climbing stairs", 4, None),
    ("event", "Aarav has his maths exam this week and she is worried for him", 4, 0),
    ("preference", "Likes her chai served in the old steel glass", 2, None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipient-id", type=int, required=True)
    args = ap.parse_args()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        P.update_profile(db, args.recipient_id, PROFILE)
        for cat, text, imp, fu_days in MEMORIES:
            fu = dt.datetime.utcnow() + dt.timedelta(days=fu_days) if fu_days is not None else None
            P.upsert_memory(db, args.recipient_id, cat, text, importance=imp, follow_up_at=fu, source="caregiver")
        ctx = P.build_personal_context(db, args.recipient_id, "")
        print(P.personal_prompt_block(ctx))
        print("Seeded. Open the voice bot — Saathi will greet them personally.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
