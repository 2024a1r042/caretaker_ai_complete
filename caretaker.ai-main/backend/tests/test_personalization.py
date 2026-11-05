"""Personalization: profile → prompt, learning memories, follow-ups, proactive check-ins, personal music."""
import datetime as dt

from services import personalization as P
from services.voice_bot_engine import build_conversation_context, generate_system_prompt


def _profile(db, rid):
    return P.update_profile(db, rid, {
        "preferred_name": "Amma",
        "hometown": "Jammu", "former_occupation": "a school teacher",
        "faith": "Krishna bhakt, evening aarti",
        "favorite_foods": ["aloo paratha", "adrak chai"], "dietary_notes": "diabetic — no sugar",
        "favorite_music": ["Achyutam Keshavam", "Lag Jaa Gale"],
        "family_members": [{"name": "Rahul", "relation": "son", "location": "Bangalore", "notes": "calls on Sundays",
                            "is_emergency_contact": True},
                           {"name": "Aarav", "relation": "grandson"}],
        "daily_routine": [{"time": "16:00", "activity": "chai", "checkin": True},
                          {"time": "18:30", "activity": "evening aarti", "checkin": True}],
        "important_dates": [{"label": "Aarav's birthday", "date": "10-27"}],
        "topics_to_avoid": ["late husband's illness"],
        "wake_time": "06:00", "sleep_time": "22:00",
    })


def test_rule_extraction_hinglish_english_devanagari():
    now = dt.datetime(2026, 10, 26, 10, 0)
    got = P.extract_memories_rules("Mujhe aloo paratha bahut pasand hai. Mujhe karela pasand nahi.", now)
    cats = [(g["category"], g["content"]) for g in got]
    assert ("preference", "Likes aloo paratha") in cats
    assert ("dislike", "Does not like karela") in cats
    got = P.extract_memories_rules("My grandson Aarav has his maths exam on Friday", now)
    assert any(g["category"] == "person" for g in got)
    ev = next(g for g in got if g["category"] == "event")
    assert ev["follow_up_at"].date() == dt.date(2026, 10, 31)       # the day after Friday's exam
    got = P.extract_memories_rules("Aaj mere ghutne mein dard hai", now)
    assert got[0]["category"] == "health" and got[0]["follow_up_at"] > now
    got = P.extract_memories_rules("मुझे भजन बहुत पसंद है", now)
    assert got and got[0]["category"] == "preference"


def test_memories_dedupe_and_count(db, people):
    _, rec = people
    a = P.upsert_memory(db, rec.id, "preference", "Likes aloo paratha", key="like:aloo paratha")
    b = P.upsert_memory(db, rec.id, "preference", "Likes aloo paratha with butter", key="like:aloo paratha")
    assert a.id == b.id and b.mention_count == 2 and "butter" in b.content


def test_relevant_memory_selected_for_message(db, people):
    _, rec = people
    P.upsert_memory(db, rec.id, "preference", "Likes aloo paratha")
    P.upsert_memory(db, rec.id, "person", "Neighbour Mrs Gupta visits on Tuesdays")
    P.upsert_memory(db, rec.id, "health", "Knee hurts when climbing stairs", importance=4)
    top = P.select_memories(db, rec.id, "aaj nashte mein paratha khaya", limit=2)
    assert "paratha" in top[0].content


def test_learn_from_message_offline(db, people):
    _, rec = people
    saved = P.learn_from_message(db, rec.id, "I love Kishore Kumar songs. Tomorrow my daughter Priya is coming.",
                                 use_llm=False, now=dt.datetime(2026, 10, 26, 10))
    contents = " | ".join(m.content for m in saved)
    assert "Kishore Kumar" in contents and "Priya" in contents
    assert any(m.follow_up_at for m in saved)


def test_prompt_is_personal_and_uses_their_name(db, people):
    _, rec = people
    _profile(db, rec.id)
    P.upsert_memory(db, rec.id, "event", "Grandson Aarav had a maths exam", importance=4,
                    follow_up_at=dt.datetime.utcnow() - dt.timedelta(hours=1))
    ctx = build_conversation_context(rec.id, db, "kaise ho")
    prompt = generate_system_prompt("User", ctx, "hi", None)    # the WebSocket path used to pass "User"
    assert "User ji" not in prompt
    assert 'Address them as "Amma"' in prompt
    assert "aloo paratha" in prompt and "Achyutam Keshavam" in prompt
    assert "Rahul (son, Bangalore)" in prompt
    assert "NEVER bring up: late husband's illness" in prompt
    assert "FOLLOW UP" in prompt and "maths exam" in prompt


def test_routine_and_dates_context():
    class Prof: daily_routine = [{"time": "16:00", "activity": "chai"}, {"time": "18:30", "activity": "aarti"}]; important_dates = [{"label": "Aarav's birthday", "date": "10-27"}]
    r = P.routine_context(Prof, dt.datetime(2026, 10, 26, 16, 10))
    assert r["current"]["activity"] == "chai" and r["next"]["activity"] == "aarti" and r["meal_window"] == "evening tea"
    d = P.upcoming_dates(Prof, dt.datetime(2026, 10, 26, 9))
    assert d[0]["in_days"] == 1


def test_proactive_priorities(db, people):
    _, rec = people
    _profile(db, rec.id)
    at = dt.datetime(2026, 10, 26, 16, 5)
    # 1st: tomorrow is Aarav's birthday
    item = P.next_proactive_checkin(db, rec.id, rec.full_name, now=at)
    assert item["reason"] == "important_date"
    P.mark_proactive_done(db, rec.id, item["key"], at)
    # then: chai time from their routine — and it knows they love adrak chai
    item = P.next_proactive_checkin(db, rec.id, rec.full_name, now=at)
    assert item["reason"] == "routine" and "chai" in item["instruction"]
    P.mark_proactive_done(db, rec.id, item["key"], at)
    # never during sleep hours unless the screen was just opened
    assert P.next_proactive_checkin(db, rec.id, rec.full_name, now=dt.datetime(2026, 10, 26, 23, 30)) is None
    assert P.next_proactive_checkin(db, rec.id, rec.full_name, force=True,
                                    now=dt.datetime(2026, 10, 26, 23, 30))["reason"] == "greeting"


def test_music_from_their_favourites(db, people):
    _, rec = people
    _profile(db, rec.id)
    ctx = P.build_personal_context(db, rec.id, "", rec.full_name)
    rec_sad = P.personalize_recommendation("sad", ctx)
    assert rec_sad["choices"][0] == "Achyutam Keshavam"          # faith set → bhajan first when low
    rec_happy = P.personalize_recommendation("happy", ctx)
    assert rec_happy["choices"][0] == "Lag Jaa Gale"
    assert "Amma" in rec_sad["message"]


def test_media_interest_becomes_favourite(db, people):
    _, rec = people
    for _ in range(2):
        P.record_media_interest(db, rec.id, "Kishore Kumar hits", "music")
    ctx = P.build_personal_context(db, rec.id, "", rec.full_name)
    assert "Kishore Kumar hits" in ctx["favourite_media"]
