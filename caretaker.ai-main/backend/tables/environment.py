from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from config import Base

class EnvironmentSensor(Base):
    __tablename__ = "environment_sensors"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Sensor Readings
    temperature_c = Column(Float, nullable=False) # Temperature in Celsius
    humidity_percent = Column(Float, nullable=False) # Humidity percentage
    aqi = Column(Integer, nullable=True) # Air Quality Index
    
    # Define relationship with CareRecipient
    care_recipient = relationship("CareRecipient", back_populates="environment_readings")
