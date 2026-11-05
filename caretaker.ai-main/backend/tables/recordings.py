from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, LargeBinary
from sqlalchemy.orm import relationship
from config import Base
import datetime


class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    caretaker_id = Column(Integer, ForeignKey("caretakers.id", ondelete="CASCADE"), nullable=False)
    # optional link to a care recipient
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)
    mime_type = Column(String, default="audio/wav")
    # store raw audio bytes (Postgres: bytea)
    data = Column(LargeBinary, nullable=True)
    duration = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    caretaker = relationship("CareTaker")
    care_recipient = relationship("CareRecipient")
