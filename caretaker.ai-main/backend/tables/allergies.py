from sqlalchemy import Column, Integer, String, Date, ForeignKey, Enum
from sqlalchemy.orm import relationship
from config import Base
import enum

class AllergyType(str, enum.Enum):
    drug = "drug"
    food = "food"
    environment = "environment"
    other = "other"

class AllergyStatus(str, enum.Enum):
    active = "active"
    resolved = "resolved"

class Allergy(Base):
    __tablename__ = "allergies"

    allergy_id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    allergen = Column(String, nullable=False)
    allergy_type = Column(Enum(AllergyType), default=AllergyType.other)
    reaction = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    diagnosed_date = Column(Date, nullable=True)
    status = Column(Enum(AllergyStatus), default=AllergyStatus.active)

    care_recipient = relationship("CareRecipient", back_populates="allergies")
