from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from config import Base

class VideoAnalysis(Base):
    __tablename__ = "video_analysis"

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, ForeignKey("care_recipients.id"), nullable=True)
    caretaker_id = Column(Integer, ForeignKey("caretakers.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    video_filename = Column(String, nullable=True)
    
    # Analysis Metrics
    has_fall = Column(Boolean, default=False)
    fall_count = Column(Integer, default=0)
    inactivity_duration_seconds = Column(Integer, default=0)
    activity_score = Column(Float, default=0.0) # 0-10 scale
    mobility_score = Column(Float, default=0.0) # 0-10 scale
    
    # Relationships
    recipient = relationship("CareRecipient", back_populates="video_analyses")
    caretaker = relationship("CareTaker", back_populates="video_analyses")
