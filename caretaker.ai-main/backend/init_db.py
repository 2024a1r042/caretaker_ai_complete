import sys
from config import engine, Base
from sqlalchemy import inspect

print("Connecting to PostgreSQL database:", engine.url)

# Import all table definitions so they are registered with SQLAlchemy's Base.metadata
import tables.users as user_tables
import tables.recordings as recordings_tables
import tables.medical_reports as med_reports_tables
import tables.video_analysis as video_analysis_tables
import tables.vital_signs as vital_signs_tables
import tables.audio_events as audio_events_tables
import tables.medical_conditions as medical_conditions_tables
import tables.disease_dictionary as disease_dictionary_tables
import tables.conversation_history as conversation_history_tables
import tables.environment as environment_tables
import tables.medications as medications_tables
import tables.medication_dose_logs as medication_dose_logs_tables
import tables.allergies as allergies_tables
import tables.admin as admin_tables
import tables.thresholds as thresholds_tables
import tables.weekly_reports as weekly_reports_tables
import tables.personalization as personalization_tables
import tables.safety_events as safety_events_tables
import tables.medical_recommendations as medical_recommendations_tables

print("Creating all tables in PostgreSQL...")
all_bases = [
    user_tables.Base, recordings_tables.Base, med_reports_tables.Base,
    video_analysis_tables.Base, vital_signs_tables.Base, audio_events_tables.Base,
    medical_conditions_tables.Base, disease_dictionary_tables.Base,
    conversation_history_tables.Base, environment_tables.Base,
    medications_tables.Base, medication_dose_logs_tables.Base,
    allergies_tables.Base, admin_tables.Base, thresholds_tables.Base,
    weekly_reports_tables.Base, personalization_tables.Base,
    safety_events_tables.Base, medical_recommendations_tables.Base
]

for b in all_bases:
    b.metadata.create_all(bind=engine)

insp = inspect(engine)
tables = insp.get_table_names()
print(f"SUCCESS! Created {len(tables)} tables in PostgreSQL database '{engine.url.database}':")
for t in sorted(tables):
    print(" -", t)
