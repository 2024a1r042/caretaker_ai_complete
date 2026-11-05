from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from config import Base
import datetime
import enum


class AudioEventType(str, enum.Enum):
    """Types of audio events detected"""
    cough = "Cough"
    sneeze = "Sneeze"
    talking = "Talking"
    noise = "Noise"


class AudioEvent(Base):
    """
    Stores detected audio events (cough, sneeze, etc.) for long-term analysis.
    Each event is linked to a care recipient and caretaker.
    """
    __tablename__ = "audio_events"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    caretaker_id = Column(Integer, ForeignKey("caretakers.id", ondelete="CASCADE"), nullable=False)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=True)
    
    # Event details
    event_type = Column(Enum(AudioEventType), nullable=False, index=True)
    confidence = Column(Float, nullable=False)  # 0.0 to 100.0
    
    # Timestamp
    detected_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # Optional metadata
    duration_ms = Column(Integer, nullable=True)  # Duration of the audio chunk in milliseconds
    notes = Column(String, nullable=True)  # Optional notes or additional context
    
    # Relationships
    caretaker = relationship("CareTaker")
    care_recipient = relationship("CareRecipient")
