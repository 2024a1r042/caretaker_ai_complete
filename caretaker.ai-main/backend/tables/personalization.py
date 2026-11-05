"""
Personalization tables — what makes Saathi feel like it *knows* the person.

RecipientProfile : facts the family enters once (and can edit any time):
                   how to address them, foods, music/bhajans, family, routine,
                   important dates, life stories, topics to avoid.
RecipientMemory  : long-term memory Saathi learns from conversations
                   ("loves aloo paratha", "grandson Aarav has exams on Friday"),
                   with importance, recency and follow-up dates.
"""

import datetime
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text

from config import Base


class RecipientProfile(Base):
    __tablename__ = "recipient_profiles"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"),
                               nullable=False, unique=True, index=True)

    preferred_name = Column(String, nullable=True)          # "Amma", "Sharma ji", "Dadi"
    language_preference = Column(String, default="hi")       # hi | en | hinglish
    native_language = Column(String, nullable=True)          # "Punjabi", "Dogri"…
    hometown = Column(String, nullable=True)
    former_occupation = Column(String, nullable=True)
    faith = Column(String, nullable=True)                    # e.g. "Hindu — Krishna bhakt, morning aarti"

    favorite_foods = Column(JSON, default=list)              # ["aloo paratha", "adrak chai"]
    disliked_foods = Column(JSON, default=list)
    dietary_notes = Column(Text, nullable=True)              # "diabetic — no sugar in chai"
    favorite_music = Column(JSON, default=list)              # ["Achyutam Keshavam", "Lata Mangeshkar"]
    favorite_shows = Column(JSON, default=list)              # ["Ramayan (1987)", "KBC"]
    hobbies = Column(JSON, default=list)

    family_members = Column(JSON, default=list)              # [{"name","relation","location","notes","is_emergency_contact"}]
    important_dates = Column(JSON, default=list)             # [{"label","date":"MM-DD"|"YYYY-MM-DD"}]
    daily_routine = Column(JSON, default=list)               # [{"time":"HH:MM","activity","checkin":bool}]
    life_stories = Column(JSON, default=list)                # ["Was a school teacher in Jammu for 30 years"]
    topics_to_avoid = Column(JSON, default=list)             # ["late husband's illness"]
    conversation_style = Column(Text, nullable=True)         # "Loves jokes; speak slowly; hard of hearing"
    wake_time = Column(String, nullable=True)                # "06:00"
    sleep_time = Column(String, nullable=True)               # "22:00"

    # bookkeeping for proactive check-ins so the same nudge isn't repeated
    proactive_state = Column(JSON, default=dict)             # {"routine:16:00": "2026-10-26", ...}

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class MemoryCategoryEnum(str, enum.Enum):
    preference = "preference"   # likes
    dislike = "dislike"
    person = "person"           # people in their life
    event = "event"             # something upcoming / happened (follow-up worthy)
    health = "health"           # "knee hurts when climbing stairs"
    routine = "routine"
    life_story = "life_story"
    feeling = "feeling"         # recurring emotional theme
    media = "media"             # songs / stories they asked for
    other = "other"


class RecipientMemory(Base):
    __tablename__ = "recipient_memories"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"),
                               nullable=False, index=True)

    category = Column(Enum(MemoryCategoryEnum), nullable=False, default=MemoryCategoryEnum.other)
    key = Column(String, nullable=False, index=True)        # normalised dedupe key, e.g. "food:aloo paratha"
    content = Column(Text, nullable=False)                   # short fact in plain language
    importance = Column(Integer, default=3)                  # 1 (trivia) … 5 (core identity / safety)
    confidence = Column(Float, default=0.8)
    source = Column(String, default="conversation")          # conversation | caregiver | system
    mention_count = Column(Integer, default=1)

    follow_up_at = Column(DateTime, nullable=True)           # when Saathi should ask about it
    followed_up = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    first_mentioned_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_mentioned_at = Column(DateTime, default=datetime.datetime.utcnow)
