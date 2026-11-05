from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey, DateTime
from config import Base
import datetime

class ThresholdConfig(Base):
    __tablename__ = 'threshold_configs'

    id = Column(Integer, primary_key=True, index=True)
    metric = Column(String, index=True, nullable=False)
    age_min = Column(Integer, default=0)
    age_max = Column(Integer, default=150)
    comorbidity_tag = Column(String, nullable=True) # e.g. "diabetes", "ckd"
    
    # Range that triggers this config level
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    
    # Severity and actions
    severity = Column(String, nullable=False) # critical, high, medium, low
    message_template = Column(String, nullable=False)
    actions = Column(JSON, nullable=True)
    action_payload = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
