"""
personalization.py — the "X-factor" layer for Saathi.

Turns the family-entered profile + what Saathi has learned in past
conversations + the current situation (time, routine, upcoming dates, recent
falls) into:

  • a compact "who this person is / what's happening now" block for the LLM
  • long-term memories learned from each message (LLM extraction with a
    rule-based fallback that works offline, Hindi/Hinglish/English)
  • relevant-memory selection for the current message
  • follow-ups ("how did Aarav's exam go?") on the right day
  • personal proactive check-ins tied to their routine and life
  • music / bhajan recommendations from *their* favourites first
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from tables.personalization import MemoryCategoryEnum, RecipientMemory, RecipientProfile

PROFILE_LIST_FIELDS = ["favorite_foods", "disliked_foods", "favorite_music", "favorite_shows", "hobbies",
                       "family_members", "important_dates", "daily_routine", "life_stories", "topics_to_avoid"]
PROFILE_TEXT_FIELDS = ["preferred_name", "language_preference", "native_language", "hometown",
                       "former_occupation", "faith", "dietary_notes", "conversation_style", "wake_time", "sleep_time"]

SPIRITUAL_WORDS = ("bhajan", "aarti", "arti", "keshavam", "ram", "krishna", "shiv", "hanuman", "kirtan", "bhakti",
                   "gurbani", "shabad", "path", "chalisa", "mantra", "satsang", "geeta", "gita", "bhagwat",
                   "भजन", "आरती", "राम", "कृष्ण", "शिव", "हनुमान", "कीर्तन", "चालीसा")

STOPWORDS = set("""a an the and or but to of in on at for with is are was were be been am i me my mine you your it this that
these those he she they them we us our do does did have has had not no yes so very just also about from as by
hai hain tha thi the ho hoon hun ka ki ke ko se me mein par aur ya bhi to toh ye yeh wo woh kya kaise kab
nahi nahin na ji aap aapka aapki mera meri mere mujhe hum hamara kuch bahut bohot abhi phir fir""".split())


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────
def get_or_create_profile(db: Session, recipient_id: int) -> RecipientProfile:
    prof = db.query(RecipientProfile).filter(RecipientProfile.care_recipient_id == recipient_id).first()
    if prof is None:
        prof = RecipientProfile(care_recipient_id=recipient_id, proactive_state={})
        for f in PROFILE_LIST_FIELDS:
            setattr(prof, f, [])
        db.add(prof)
        db.commit()
        db.refresh(prof)
    return prof


def profile_to_dict(prof: RecipientProfile) -> dict:
    out = {"care_recipient_id": prof.care_recipient_id}
    for f in PROFILE_TEXT_FIELDS:
        out[f] = getattr(prof, f)
    for f in PROFILE_LIST_FIELDS:
        out[f] = list(getattr(prof, f) or [])
    out["updated_at"] = prof.updated_at.isoformat() if prof.updated_at else None
    return out


def update_profile(db: Session, recipient_id: int, data: dict) -> RecipientProfile:
    prof = get_or_create_profile(db, recipient_id)
    for f in PROFILE_TEXT_FIELDS:
        if f in data:
            v = data[f]
            setattr(prof, f, (v.strip() or None) if isinstance(v, str) else v)
    for f in PROFILE_LIST_FIELDS:
        if f in data and data[f] is not None:
            val = data[f]
            if isinstance(val, str):  # allow comma-separated input for simple lists
                val = [x.strip() for x in val.split(",") if x.strip()]
            setattr(prof, f, list(val))
    db.commit()
    db.refresh(prof)
    return prof


def address_name(prof: Optional[RecipientProfile], full_name: Optional[str]) -> str:
    if prof is not None and prof.preferred_name:
        return prof.preferred_name.strip()
    first = (full_name or "").split()[0] if full_name else ""
    return f"{first} ji" if first else "ji"


# ─────────────────────────────────────────────────────────────────────────────
# Time / routine / dates
# ─────────────────────────────────────────────────────────────────────────────
def _parse_hhmm(s: str) -> Optional[dt.time]:
    try:
        h, m = str(s).strip().split(":")[:2]
        return dt.time(int(h), int(m))
    except Exception:
        return None


def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def period_of_day(now: dt.datetime) -> str:
    h = now.hour
    return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 21 else "night"


def routine_context(prof: Optional[RecipientProfile], now: dt.datetime) -> dict:
    items = []
    for it in (prof.daily_routine if prof else None) or []:
        tm = _parse_hhmm(it.get("time", ""))
        if tm and it.get("activity"):
            items.append((tm, it))
    items.sort(key=lambda x: _minutes(x[0]))
    cur_m = now.hour * 60 + now.minute
    current = nxt = None
    for tm, it in items:
        delta = cur_m - _minutes(tm)
        if -10 <= delta <= 45:
            current = {"time": tm.strftime("%H:%M"), "activity": it["activity"], "minutes_since": delta,
                       "checkin": it.get("checkin", True)}
        if _minutes(tm) > cur_m + 10 and nxt is None:
            nxt = {"time": tm.strftime("%H:%M"), "activity": it["activity"]}
    meal = None
    for name, (a, b) in {"breakfast": (7 * 60, 10 * 60), "lunch": (12 * 60 + 30, 14 * 60 + 30),
                         "evening tea": (16 * 60, 17 * 60 + 30), "dinner": (19 * 60 + 30, 21 * 60 + 30)}.items():
        if a <= cur_m <= b:
            meal = name
    return {"current": current, "next": nxt, "meal_window": meal, "period": period_of_day(now)}


def upcoming_dates(prof: Optional[RecipientProfile], now: dt.datetime, days: int = 7) -> List[dict]:
    out = []
    today = now.date()
    for d in (prof.important_dates if prof else None) or []:
        raw = str(d.get("date", "")).strip()
        try:
            parts = [int(x) for x in raw.split("-")]
            if len(parts) == 3:
                month, day = parts[1], parts[2]
            elif len(parts) == 2:
                month, day = parts
            else:
                continue
            cand = dt.date(today.year, month, day)
            if cand < today:
                cand = dt.date(today.year + 1, month, day)
        except Exception:
            continue
        diff = (cand - today).days
        if diff <= days:
            out.append({"label": d.get("label", "special day"), "in_days": diff, "date": cand.isoformat()})
    return sorted(out, key=lambda x: x["in_days"])


# ─────────────────────────────────────────────────────────────────────────────
# Memory: storage
# ─────────────────────────────────────────────────────────────────────────────
def _tokens(text: str) -> set:
    toks = re.findall(r"[\wऀ-ॿ]+", (text or "").lower())
    return {t for t in toks if len(t) > 2 and t not in STOPWORDS}


def normalize_key(category: str, text: str) -> str:
    toks = sorted(_tokens(text))[:6]
    return f"{category}:{' '.join(toks)}" if toks else f"{category}:{(text or '').strip().lower()[:40]}"


def upsert_memory(db: Session, recipient_id: int, category: str, content: str, key: Optional[str] = None,
                  importance: int = 3, follow_up_at: Optional[dt.datetime] = None, source: str = "conversation",
                  confidence: float = 0.8, now: Optional[dt.datetime] = None) -> Optional[RecipientMemory]:
    content = (content or "").strip()
    if not content:
        return None
    now = now or dt.datetime.utcnow()
    try:
        cat = MemoryCategoryEnum(category)
    except ValueError:
        cat = MemoryCategoryEnum.other
    key = (key or normalize_key(cat.value, content)).strip().lower()[:200]
    existing = db.query(RecipientMemory).filter(RecipientMemory.care_recipient_id == recipient_id,
                                                RecipientMemory.key == key).first()
    if existing is None:
        # near-duplicate check: same category and heavy token overlap
        new_t = _tokens(content)
        for m in db.query(RecipientMemory).filter(RecipientMemory.care_recipient_id == recipient_id,
                                                  RecipientMemory.category == cat,
                                                  RecipientMemory.active == True).all():  # noqa: E712
            old_t = _tokens(m.content)
            if new_t and old_t and len(new_t & old_t) / min(len(new_t), len(old_t)) >= 0.8:
                existing = m
                break
    if existing is not None:
        existing.mention_count = (existing.mention_count or 1) + 1
        existing.last_mentioned_at = now
        existing.importance = max(existing.importance or 1, int(importance))
        existing.active = True
        if len(content) > len(existing.content or ""):
            existing.content = content
        if follow_up_at and (existing.follow_up_at is None or existing.followed_up):
            existing.follow_up_at, existing.followed_up = follow_up_at, False
        db.commit()
        return existing
    mem = RecipientMemory(care_recipient_id=recipient_id, category=cat, key=key, content=content,
                          importance=max(1, min(5, int(importance))), confidence=confidence, source=source,
                          follow_up_at=follow_up_at, first_mentioned_at=now, last_mentioned_at=now)
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def record_media_interest(db: Session, recipient_id: int, query: str, kind: str = "music"):
    """Every song/story they ask for becomes a (weighted) memory → personal recommendations later."""
    q = (query or "").strip()
    if len(q) < 3:
        return None
    return upsert_memory(db, recipient_id, "media", f"Likes listening to: {q}" if kind == "music" else f"Enjoyed the story: {q}",
                         key=f"media:{kind}:{q.lower()[:60]}", importance=2, source="behaviour")


# ─────────────────────────────────────────────────────────────────────────────
# Memory: extraction (LLM first, rules as offline fallback)
# ─────────────────────────────────────────────────────────────────────────────
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
             "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3, "shukravar": 4, "shanivar": 5, "ravivar": 6,
             "सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3, "शुक्रवार": 4, "शनिवार": 5, "रविवार": 6}
_RELATIONS = {"son": "son", "beta": "son", "daughter": "daughter", "beti": "daughter", "grandson": "grandson",
              "pota": "grandson", "nati": "grandson", "granddaughter": "granddaughter", "poti": "granddaughter",
              "natin": "granddaughter", "wife": "wife", "patni": "wife", "husband": "husband", "pati": "husband",
              "bahu": "daughter-in-law", "damad": "son-in-law", "friend": "friend", "dost": "friend",
              "sister": "sister", "behen": "sister", "bhai": "brother", "brother": "brother", "neighbour": "neighbour",
              "padosi": "neighbour", "बेटा": "son", "बेटी": "daughter", "पोता": "grandson", "पोती": "granddaughter",
              "बहू": "daughter-in-law", "दोस्त": "friend"}


def _event_date(sentence: str, now: dt.datetime) -> Optional[dt.datetime]:
    s = sentence.lower()
    if re.search(r"\b(parso|parson|day after tomorrow)\b|परसों", s):
        return now + dt.timedelta(days=2)
    if re.search(r"\b(kal|tomorrow)\b|कल", s):
        # Hindi "kal" is both yesterday and tomorrow; future markers decide
        if re.search(r"\b(hoga|hogi|honge|jayenge|jaungi|jaunga|aayega|aayegi|aa raha|aa rahi|hai kal|tomorrow|will|going to)\b|होगा|होगी|आएगा|आएगी|जाएंगे", s) or "tomorrow" in s:
            return now + dt.timedelta(days=1)
        return None
    if re.search(r"\b(next week|agle hafte|agle haftay)\b|अगले हफ्ते", s):
        return now + dt.timedelta(days=7)
    for w, idx in _WEEKDAYS.items():
        if w in s:
            ahead = (idx - now.weekday()) % 7 or 7
            return now + dt.timedelta(days=ahead)
    return None


def extract_memories_rules(text: str, now: Optional[dt.datetime] = None) -> List[dict]:
    now = now or dt.datetime.utcnow()
    out: List[dict] = []
    for sent in re.split(r"[.!?।\n]+", text or ""):
        s = sent.strip()
        if len(s) < 4:
            continue
        low = s.lower()

        # dislikes first (so "pasand nahi" isn't read as a like)
        m = (re.search(r"(?:mujhe|muje|hume|humein)\s+(.+?)\s+(?:bilkul\s+)?(?:pasand\s+nahi|pasand\s+nahin|achha\s+nahi|acha\s+nahi)", s, re.I)
             or re.search(r"\bi\s+(?:really\s+)?(?:don'?t|do not)\s+(?:like|enjoy)\s+(.+)", s, re.I)
             or re.search(r"\bi\s+(?:hate|dislike)\s+(.+)", s, re.I)
             or re.search(r"मुझे\s+(.+?)\s+(?:बिल्कुल\s+)?पसंद\s+नहीं", s))
        if m:
            obj = m.group(1).strip(" ,")
            out.append({"category": "dislike", "content": f"Does not like {obj}", "key": f"dislike:{obj[:50]}",
                        "importance": 3})
            continue
        m = (re.search(r"(?:mujhe|muje|hume|humein)\s+(.+?)\s+(?:bahut\s+|bohot\s+|bada\s+)?(?:pasand|achha\s+lag|acha\s+lag|achhi\s+lag|acchi\s+lag|bahut\s+bhata)", s, re.I)
             or re.search(r"\bi\s+(?:really\s+|absolutely\s+)?(?:love|like|enjoy|adore)\s+(.+)", s, re.I)
             or re.search(r"\bmy\s+favou?rite\s+(?:\w+\s+)?is\s+(.+)", s, re.I)
             or re.search(r"मुझे\s+(.+?)\s+(?:बहुत\s+)?(?:पसंद|अच्छा\s+लग|अच्छी\s+लग)", s))
        if m:
            obj = m.group(1).strip(" ,")
            if 2 < len(obj) < 80:
                out.append({"category": "preference", "content": f"Likes {obj}", "key": f"like:{obj[:50]}",
                            "importance": 3})
            continue

        m = (re.search(r"\b(?:my|mera|meri|mere)\s+(son|daughter|grandson|granddaughter|wife|husband|friend|sister|brother|beta|beti|pota|poti|nati|natin|bahu|damad|dost|bhai|behen|neighbour|padosi)\b(?:\s+(?:named|called|ka naam|ki naam|,))?\s*([A-Z][a-z]{2,})?", s, re.I)
             or re.search(r"(?:मेरा|मेरी|मेरे)\s+(बेटा|बेटी|पोता|पोती|बहू|दोस्त)\s*([ऀ-ॿ]{2,})?", s))
        if m:
            rel = _RELATIONS.get(m.group(1).lower(), m.group(1).lower())
            name = (m.group(2) or "").strip()
            if name.lower() in STOPWORDS or name.lower() in ("is", "has", "was", "ne", "ki", "ka"):
                name = ""
            when = _event_date(s, now)
            out.append({"category": "person", "content": s if len(s) < 160 else s[:157] + "...",
                        "key": f"person:{rel}:{name.lower()}" if name else None, "importance": 4})
            if when:
                out.append({"category": "event", "content": s, "importance": 4,
                            "follow_up_at": when + dt.timedelta(hours=20)})
            continue

        if re.search(r"\b(dard|pain|hurts?|hurting|dukh|takleef|chakkar|dizzy|ghabrahat|neend nahi|can'?t sleep|"
                     r"sir dard|ghutna|ghutne|kamar|saans|breathless|cough|khansi|bukhar|fever)\b|दर्द|चक्कर|घुटन|बुखार|खांसी", low):
            out.append({"category": "health", "content": s if len(s) < 160 else s[:157] + "...", "importance": 4,
                         "follow_up_at": now + dt.timedelta(hours=20)})
            continue

        when = _event_date(s, now)
        if when and len(s.split()) >= 4:
            out.append({"category": "event", "content": s if len(s) < 160 else s[:157] + "...", "importance": 3,
                        "follow_up_at": when + dt.timedelta(hours=20)})
    return out


def extract_memories_llm(text: str, last_bot: str = "", name: str = "", now: Optional[dt.datetime] = None) -> Optional[List[dict]]:
    """Returns None when the LLM is unavailable (caller falls back to rules)."""
    try:
        from utils.gemini_client import call_gemini, safe_json_parse
    except Exception:
        return None
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    now = now or dt.datetime.utcnow()
    prompt = f"""You maintain the long-term memory of an AI companion for an elderly person named {name or 'the user'}.
From the USER message below, extract up to 3 durable facts worth remembering for future conversations
(likes/dislikes, people in their life and their names, upcoming or recent events, health complaints,
routines, life stories). Ignore greetings, small talk and anything the assistant said.
Today is {now.strftime('%A %Y-%m-%d')}.

Assistant's previous line (context only): "{(last_bot or '')[:300]}"
USER message: "{(text or '')[:800]}"

Return ONLY JSON:
{{"memories": [{{"category": "preference|dislike|person|event|health|routine|life_story|feeling|other",
  "content": "short fact in English, third person, e.g. 'Loves aloo paratha' or 'Grandson Aarav has a maths exam on Friday'",
  "key": "short stable dedupe key, e.g. 'food:aloo paratha' or 'person:grandson:aarav'",
  "importance": 1-5,
  "follow_up_in_days": null or integer (for events/health: when to gently ask about it)}}]}}
If nothing is worth remembering return {{"memories": []}}."""
    data = call_gemini({"contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 400}},
                       timeout=12, caller="[memory_extract]")
    if not data or not data.get("candidates"):
        return None
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = safe_json_parse(raw) or {}
    except Exception:
        return None
    out = []
    for m in parsed.get("memories", [])[:3]:
        if not isinstance(m, dict) or not m.get("content"):
            continue
        fu = m.get("follow_up_in_days")
        item = {"category": m.get("category", "other"), "content": str(m["content"])[:240],
                "key": (m.get("key") or None), "importance": int(m.get("importance") or 3)}
        if isinstance(fu, (int, float)) and fu >= 0:
            item["follow_up_at"] = now + dt.timedelta(days=float(fu), hours=2)
        out.append(item)
    return out


def learn_from_message(db: Session, recipient_id: int, user_text: str, last_bot_text: str = "", name: str = "",
                       use_llm: bool = True, now: Optional[dt.datetime] = None) -> List[RecipientMemory]:
    now = now or dt.datetime.utcnow()
    items = extract_memories_llm(user_text, last_bot_text, name, now) if use_llm else None
    if items is None:
        items = extract_memories_rules(user_text, now)
    saved = []
    for it in items:
        m = upsert_memory(db, recipient_id, it.get("category", "other"), it.get("content", ""), key=it.get("key"),
                          importance=it.get("importance", 3), follow_up_at=it.get("follow_up_at"), now=now)
        if m is not None:
            saved.append(m)
    return saved


def learn_in_background(recipient_id: int, user_text: str, last_bot_text: str = "", name: str = "",
                        use_llm: bool = False):
    """Fire-and-forget learning so the reply is never delayed by memory extraction.
    Offline rules by default: an extra LLM call per message would double quota use."""
    import threading

    def _run():
        try:
            from config import SessionLocal
            db = SessionLocal()
            try:
                learn_from_message(db, recipient_id, user_text, last_bot_text, name, use_llm=use_llm)
            finally:
                db.close()
        except Exception as e:
            print(f"[personalization] learning failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Memory: retrieval
# ─────────────────────────────────────────────────────────────────────────────
def select_memories(db: Session, recipient_id: int, user_text: str = "", limit: int = 8,
                    now: Optional[dt.datetime] = None) -> List[RecipientMemory]:
    now = now or dt.datetime.utcnow()
    mems = db.query(RecipientMemory).filter(RecipientMemory.care_recipient_id == recipient_id,
                                            RecipientMemory.active == True).all()  # noqa: E712
    if not mems:
        return []
    q = _tokens(user_text)
    scored = []
    for m in mems:
        mt = _tokens(m.content) | _tokens(m.key.split(":", 1)[-1] if m.key else "")
        overlap = (len(q & mt) / max(1, min(len(q), len(mt)))) if q and mt else 0.0
        age_days = max(0.0, (now - (m.last_mentioned_at or now)).total_seconds() / 86400)
        recency = math.exp(-age_days / 30.0)
        score = 0.35 * (m.importance or 3) / 5 + 0.20 * recency + 0.40 * min(1.0, overlap) \
            + 0.05 * min(m.mention_count or 1, 5) / 5
        scored.append((score, overlap, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [m for s, o, m in scored if o > 0][: max(3, limit // 2)]          # relevant to *this* message
    for s, o, m in scored:                                                     # then the most important overall
        if len(chosen) >= limit:
            break
        if m not in chosen:
            chosen.append(m)
    return chosen[:limit]


def due_followups(db: Session, recipient_id: int, now: Optional[dt.datetime] = None) -> List[RecipientMemory]:
    now = now or dt.datetime.utcnow()
    return db.query(RecipientMemory).filter(
        RecipientMemory.care_recipient_id == recipient_id, RecipientMemory.active == True,  # noqa: E712
        RecipientMemory.followed_up == False, RecipientMemory.follow_up_at != None,  # noqa: E711,E712
        RecipientMemory.follow_up_at <= now,
        RecipientMemory.follow_up_at >= now - dt.timedelta(days=5),
    ).order_by(desc(RecipientMemory.importance), RecipientMemory.follow_up_at).all()


def mark_followed_up(db: Session, memory_id: Optional[int]):
    if not memory_id:
        return
    m = db.query(RecipientMemory).filter(RecipientMemory.id == memory_id).first()
    if m:
        m.followed_up = True
        db.commit()


def recent_safety_events(db: Session, recipient_id: int, hours: int = 72, now: Optional[dt.datetime] = None) -> List:
    try:
        from tables.safety_events import SafetyEvent
    except Exception:
        return []
    now = now or dt.datetime.utcnow()
    return db.query(SafetyEvent).filter(SafetyEvent.care_recipient_id == recipient_id,
                                        SafetyEvent.created_at >= now - dt.timedelta(hours=hours)) \
        .order_by(desc(SafetyEvent.created_at)).limit(3).all()


# ─────────────────────────────────────────────────────────────────────────────
# Personal context → prompt
# ─────────────────────────────────────────────────────────────────────────────
def _favourite_media(db: Session, recipient_id: int, prof: Optional[RecipientProfile]) -> List[str]:
    favs: List[str] = list((prof.favorite_music if prof else None) or [])
    try:
        from tables.conversation_history import VoiceBotPreferences
        prefs = db.query(VoiceBotPreferences).filter(VoiceBotPreferences.care_recipient_id == recipient_id).first()
        if prefs:
            favs += [s.get("title") or s.get("query") for s in (prefs.favorite_songs or []) if isinstance(s, dict)]
    except Exception:
        pass
    media = db.query(RecipientMemory).filter(RecipientMemory.care_recipient_id == recipient_id,
                                             RecipientMemory.category == MemoryCategoryEnum.media,
                                             RecipientMemory.active == True) \
        .order_by(desc(RecipientMemory.mention_count)).limit(5).all()  # noqa: E712
    favs += [m.content.split(":", 1)[-1].strip() for m in media if (m.mention_count or 1) >= 2]
    seen, out = set(), []
    for f in favs:
        if f and f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out[:8]


def build_personal_context(db: Session, recipient_id: int, user_text: str = "", full_name: str = "",
                           now: Optional[dt.datetime] = None) -> dict:
    now_local = now or dt.datetime.now()
    now_utc = dt.datetime.utcnow() if now is None else now
    prof = get_or_create_profile(db, recipient_id)
    mems = select_memories(db, recipient_id, user_text, now=now_utc)
    fus = due_followups(db, recipient_id, now_utc)
    safety = recent_safety_events(db, recipient_id, now=now_utc)
    return {
        "name": address_name(prof, full_name),
        "profile": profile_to_dict(prof),
        "routine": routine_context(prof, now_local),
        "upcoming_dates": upcoming_dates(prof, now_local),
        "memories": [{"id": m.id, "category": m.category.value, "content": m.content} for m in mems],
        "followup": ({"id": fus[0].id, "content": fus[0].content,
                      "since": fus[0].first_mentioned_at.strftime("%A") if fus[0].first_mentioned_at else ""}
                     if fus else None),
        "favourite_media": _favourite_media(db, recipient_id, prof),
        "safety": [{"id": s.id, "when": s.created_at.strftime("%a %I:%M %p") if s.created_at else "",
                    "type": s.fall_type or s.event_type, "status": s.status.value if s.status else "",
                    "response": s.response_text} for s in safety],
    }


def personal_prompt_block(p: dict) -> str:
    if not p:
        return ""
    prof = p.get("profile", {})
    L: List[str] = []
    name = p.get("name") or "them"
    L.append(f"WHO {name.upper()} IS (weave in naturally — never recite this like a list):")
    L.append(f'- Address them as "{name}".')
    bio = [x for x in [prof.get("hometown") and f"from {prof['hometown']}",
                       prof.get("former_occupation") and f"used to be {prof['former_occupation']}",
                       prof.get("native_language") and f"mother tongue {prof['native_language']}"] if x]
    if bio:
        L.append("- " + "; ".join(bio))
    if prof.get("faith"):
        L.append(f"- Faith / practice: {prof['faith']}")
    if prof.get("favorite_foods"):
        L.append(f"- Loves eating: {', '.join(prof['favorite_foods'][:5])}"
                 + (f" (diet: {prof['dietary_notes']})" if prof.get("dietary_notes") else ""))
    elif prof.get("dietary_notes"):
        L.append(f"- Diet: {prof['dietary_notes']}")
    if prof.get("disliked_foods"):
        L.append(f"- Dislikes: {', '.join(prof['disliked_foods'][:4])}")
    fav = p.get("favourite_media") or []
    if fav:
        L.append(f"- Their music/bhajans: {', '.join(fav[:6])} — when suggesting music, offer THESE first, not generic songs")
    if prof.get("favorite_shows"):
        L.append(f"- Shows they love: {', '.join(prof['favorite_shows'][:4])}")
    if prof.get("hobbies"):
        L.append(f"- Hobbies: {', '.join(prof['hobbies'][:5])}")
    fam = []
    for f in (prof.get("family_members") or [])[:6]:
        if isinstance(f, dict) and f.get("name"):
            s = f"{f['name']} ({f.get('relation', '')}"
            s += f", {f['location']}" if f.get("location") else ""
            s += ")"
            s += f" — {f['notes']}" if f.get("notes") else ""
            fam.append(s)
    if fam:
        L.append("- Family: " + "; ".join(fam))
    if prof.get("life_stories"):
        L.append("- Stories they love telling: " + " | ".join(prof["life_stories"][:3]))
    if prof.get("conversation_style"):
        L.append(f"- How to talk with them: {prof['conversation_style']}")
    if prof.get("topics_to_avoid"):
        L.append(f"- NEVER bring up: {', '.join(prof['topics_to_avoid'])}")

    r = p.get("routine") or {}
    now_bits = []
    if r.get("current"):
        now_bits.append(f"it is around their usual time for \"{r['current']['activity']}\" ({r['current']['time']})")
    if r.get("meal_window"):
        now_bits.append(f"it is {r['meal_window']} time")
    if r.get("next"):
        now_bits.append(f"next in their day: {r['next']['activity']} at {r['next']['time']}")
    if now_bits:
        L.append("RIGHT NOW: " + "; ".join(now_bits) + ".")
    dates = p.get("upcoming_dates") or []
    if dates:
        def _when(n):
            return "TODAY" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"
        L.append("COMING UP: " + "; ".join(f"{d['label']} {_when(d['in_days'])}" for d in dates[:3]) + ".")
    mems = p.get("memories") or []
    if mems:
        L.append("YOU REMEMBER FROM EARLIER CHATS (bring up at most one, only if it fits):")
        for m in mems[:8]:
            L.append(f"- {m['content']}")
    fu = p.get("followup")
    if fu:
        L.append(f"FOLLOW UP: earlier ({fu.get('since') or 'recently'}) they told you: \"{fu['content']}\". "
                 "If the moment allows, ask how it went / how it is now — warmly, once.")
    safety = p.get("safety") or []
    if safety:
        s = safety[0]
        resp = f' and said "{s["response"]}"' if s.get("response") else ""
        L.append(f"RECENT SAFETY EVENT: a {s['type'].replace('_', ' ')} was detected {s['when']}{resp}. "
                 "Gently check how they feel now (pain, dizziness) without frightening them.")
    L.append("PERSONALISE: when it fits, connect what you say to something you know about them "
             "(their food, family, bhajans, stories) — that is what makes you feel like family, not a bot.")
    return "\n".join(L) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations from THEIR favourites
# ─────────────────────────────────────────────────────────────────────────────
def personalize_recommendation(mood: str, p: dict) -> Optional[dict]:
    favs = list((p or {}).get("favourite_media") or [])
    if not favs:
        return None
    spiritual = [f for f in favs if any(w in f.lower() for w in SPIRITUAL_WORDS)]
    other = [f for f in favs if f not in spiritual]
    faith = bool(((p or {}).get("profile") or {}).get("faith"))
    if mood == "spiritual":
        pool = spiritual or favs
    elif mood in ("sad", "lonely", "anxious", "distressed", "angry"):
        pool = (spiritual + other) if faith else (other + spiritual)
    elif mood in ("happy", "relaxed", "bored"):
        pool = other + spiritual
    else:
        return None
    pool = pool[:3]
    name = p.get("name") or ""
    first = pool[0]
    return {
        "type": "choice",
        "category": "music",
        "personal": True,
        "message": f"{name}, aapka pasandida \"{first}\" lagaun? Ya inmein se koi aur?",
        "choices": pool,
        "queries": pool,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Proactive check-ins (Saathi starts the conversation)
# ─────────────────────────────────────────────────────────────────────────────
def next_proactive_checkin(db: Session, recipient_id: int, full_name: str = "", force: bool = False,
                           now: Optional[dt.datetime] = None) -> Optional[dict]:
    now = now or dt.datetime.now()
    prof = get_or_create_profile(db, recipient_id)
    state: Dict[str, str] = dict(prof.proactive_state or {})
    today = now.date().isoformat()
    name = address_name(prof, full_name)

    def fresh(key):
        return key not in state

    # quiet hours
    sleep_t, wake_t = _parse_hhmm(prof.sleep_time or "22:00"), _parse_hhmm(prof.wake_time or "06:00")
    cur = now.hour * 60 + now.minute
    asleep = sleep_t and wake_t and (cur >= _minutes(sleep_t) or cur < _minutes(wake_t))
    if asleep and not force:
        return None

    # 1. safety follow-up (a fall in the last day that they said was fine)
    for s in recent_safety_events(db, recipient_id, hours=30, now=dt.datetime.utcnow()):
        key = f"safety:{s.id}"
        age_h = (dt.datetime.utcnow() - s.created_at).total_seconds() / 3600 if s.created_at else 0
        if fresh(key) and age_h >= 2:
            return {"key": key, "reason": "post_fall_followup",
                    "instruction": f"Earlier ({s.created_at.strftime('%a %I:%M %p') if s.created_at else 'recently'}) "
                                   f"a {(s.fall_type or 'fall').replace('_', ' ')} was detected. Start by gently asking "
                                   f"{name} how they are feeling now — any pain in the knee/hip/back, any dizziness. "
                                   "Be warm, not alarming."}
    # 2. important dates
    for d in upcoming_dates(prof, now, days=1):
        key = f"date:{d['label']}:{d['date']}"
        if fresh(key):
            when = "today" if d["in_days"] == 0 else "tomorrow"
            return {"key": key, "reason": "important_date",
                    "instruction": f"{d['label']} is {when}. Bring it up joyfully and personally "
                                   "(e.g. suggest calling them, or reminisce). One short question."}
    # 3. memory follow-ups
    fus = due_followups(db, recipient_id, dt.datetime.utcnow())
    if fus:
        m = fus[0]
        key = f"mem:{m.id}"
        if fresh(key):
            return {"key": key, "reason": "memory_followup", "memory_id": m.id,
                    "instruction": f"Earlier they told you: \"{m.content}\". Start by asking about it warmly, "
                                   "like a friend who remembered. One question."}
    # 4. routine moments
    r = routine_context(prof, now)
    if r.get("current") and r["current"].get("checkin", True):
        key = f"routine:{r['current']['time']}:{today}"
        if fresh(key):
            foods = ", ".join((prof.favorite_foods or [])[:2])
            hint = f" (they love {foods})" if foods and any(w in r["current"]["activity"].lower()
                                                            for w in ("chai", "tea", "lunch", "breakfast", "dinner",
                                                                      "nashta", "khana", "meal", "snack")) else ""
            return {"key": key, "reason": "routine",
                    "instruction": f"It's {now.strftime('%I:%M %p')} — usually their time for "
                                   f"\"{r['current']['activity']}\"{hint}. Start the conversation by bringing this up "
                                   "in a caring, personal way. One short question."}
    # 5. long silence during the day
    try:
        from tables.conversation_history import ConversationMessage, SenderEnum
        last = db.query(ConversationMessage).filter(ConversationMessage.care_recipient_id == recipient_id,
                                                    ConversationMessage.sender == SenderEnum.user) \
            .order_by(desc(ConversationMessage.created_at)).first()
        # only "we haven't talked in a while" if we HAVE talked before
        silent_h = ((dt.datetime.utcnow() - last.created_at).total_seconds() / 3600) if last and last.created_at else 0
    except Exception:
        silent_h = 0
    if silent_h >= 3 and not asleep:
        key = f"silence:{today}:{now.hour // 3}"
        if fresh(key):
            mems = select_memories(db, recipient_id, "", limit=3)
            hook = f" You could connect it to: \"{mems[0].content}\"." if mems else ""
            return {"key": key, "reason": "long_silence",
                    "instruction": f"You haven't talked for a few hours. Check in on {name}'s day warmly.{hook} "
                                   "One short question."}
    # 6. greeting on open
    if force:
        key = f"greet:{today}:{period_of_day(now)}"
        return {"key": key, "reason": "greeting",
                "instruction": f"Greet {name} for this time of day ({period_of_day(now)}) in a personal way — "
                               "use something you know about them or their day. One short question."}
    return None


def mark_proactive_done(db: Session, recipient_id: int, key: str, now: Optional[dt.datetime] = None):
    prof = get_or_create_profile(db, recipient_id)
    state = dict(prof.proactive_state or {})
    state[key] = (now or dt.datetime.now()).isoformat(timespec="minutes")
    if len(state) > 200:  # keep it bounded
        for k in sorted(state, key=lambda k: state[k])[: len(state) - 200]:
            state.pop(k, None)
    prof.proactive_state = state
    db.commit()


def learn_from_reply(db: Session, recipient_id: int, user_text: str, remember, now: Optional[dt.datetime] = None):
    """
    Memories now come back INSIDE the chat reply (field "remember"), so learning
    costs no extra Gemini call. If the reply had no usable field (parse failure,
    LLM offline) fall back to the offline Hindi/Hinglish/English rules.
    """
    now = now or dt.datetime.utcnow()
    items: List[dict] = []
    if isinstance(remember, list):
        for m in remember[:3]:
            if not isinstance(m, dict) or not str(m.get("content", "")).strip():
                continue
            it = {"category": m.get("category", "other"), "content": str(m["content"])[:240],
                  "key": m.get("key"), "importance": m.get("importance", 3)}
            try:
                it["importance"] = int(it["importance"])
            except (TypeError, ValueError):
                it["importance"] = 3
            fu = m.get("follow_up_in_days")
            if isinstance(fu, (int, float)) and fu >= 0:
                it["follow_up_at"] = now + dt.timedelta(days=float(fu), hours=2)
            items.append(it)
    else:
        items = extract_memories_rules(user_text, now)
    saved = []
    for it in items:
        m = upsert_memory(db, recipient_id, it.get("category", "other"), it.get("content", ""), key=it.get("key"),
                          importance=it.get("importance", 3), follow_up_at=it.get("follow_up_at"), now=now)
        if m is not None:
            saved.append(m)
    return saved
