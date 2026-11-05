from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from config import Base
import datetime

class VitalSign(Base):
    __tablename__ = "vital_signs"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=False)
    
    heart_rate = Column(Integer, nullable=True)          # bpm
    systolic_bp = Column(Integer, nullable=True)         # mmHg
    diastolic_bp = Column(Integer, nullable=True)        # mmHg
    oxygen_saturation = Column(Integer, nullable=True)   # %
    sleep_score = Column(Integer, nullable=True)         # 0-100
    temperature = Column(Float, nullable=True)           # Fahrenheit
    bmi = Column(Float, nullable=True)                   # kg/m^2
    height = Column(Float, nullable=True)                # cm or m? user mentioned BMI, usually calculated. Let's store raw H/W if needed later. But user mentioned H:-- W:-- on UI.
    weight = Column(Float, nullable=True)                # kg or lbs? 
    
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship back to recipient
    recipient = relationship("CareRecipient", back_populates="vital_signs")
