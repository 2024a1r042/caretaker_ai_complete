from datetime import datetime
from sqlalchemy.orm import Session
from tables.conversation_history import ProactiveReminder, ReminderTypeEnum, RecurrenceEnum
from tables.users import CareRecipient
from tables.medications import Medication, MedicationStatus

def create_default_reminders(recipient_id: int, db: Session):
    reminders = [
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water! Staying hydrated is important.", scheduled_time="08:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water!", scheduled_time="10:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water!", scheduled_time="12:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water!", scheduled_time="14:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water!", scheduled_time="16:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time for a glass of water!", scheduled_time="18:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.water, reminder_text="Time to drink a little water before resting.", scheduled_time="20:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.food, reminder_text="10 AM check-in! Feel free to grab a fruit or a light snack.", scheduled_time="10:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.food, reminder_text="4 PM. It's time for an evening snack.", scheduled_time="16:00", recurrence=RecurrenceEnum.daily),
        ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.exercise, reminder_text="Evening walk! Make sure to take a 10-15 minute walk if the weather is nice outside.", scheduled_time="18:00", recurrence=RecurrenceEnum.daily),
    ]

    active_meds = db.query(Medication).filter(
        Medication.care_recipient_id == recipient_id,
        Medication.status == MedicationStatus.active
    ).all()
    
    meds_added = False
    for med in active_meds:
        if med.schedule_time:
            dosage_str = f" ({med.dosage})" if med.dosage else ""
            reminders.append(
                ProactiveReminder(
                    care_recipient_id=recipient_id, 
                    reminder_type=ReminderTypeEnum.medicine, 
                    reminder_text=f"Time to take your medicine: {med.medicine_name}{dosage_str}.", 
                    scheduled_time=med.schedule_time, 
                    recurrence=RecurrenceEnum.daily
                )
            )
            meds_added = True

    if not meds_added:
        reminders.extend([
            ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.medicine, reminder_text="Don't forget your morning medicine.", scheduled_time="08:00", recurrence=RecurrenceEnum.daily),
            ProactiveReminder(care_recipient_id=recipient_id, reminder_type=ReminderTypeEnum.medicine, reminder_text="Don't forget your evening medicine.", scheduled_time="20:00", recurrence=RecurrenceEnum.daily),
        ])

    db.bulk_save_objects(reminders)
    db.commit()

def get_pending_triggers(recipient_id: int, db: Session):
    # Returns all due proactive actions
    now = datetime.now()
    due_reminders = db.query(ProactiveReminder).filter(
        ProactiveReminder.care_recipient_id == recipient_id,
        ProactiveReminder.is_active == True,
    ).all()
    
    triggers = []
    today = now.date()
    
    # Check reminders
    for r in due_reminders:
        try:
            r_time_obj = datetime.strptime(r.scheduled_time, "%H:%M").time()
            if now.time() >= r_time_obj:
                if r.last_triggered_at is None or r.last_triggered_at.date() < today:
                    triggers.append({
                        "id": r.id,
                        "type": "reminder",
                        "text": f"Friendly reminder: {r.reminder_text}",
                        "reminder_type": r.reminder_type.value
                    })
                    r.last_triggered_at = now
        except Exception as e:
            print(f"Error parsing reminder time for reminder ID {r.id}: {e}")
            
    if triggers:
        db.commit()
    
    return triggers
