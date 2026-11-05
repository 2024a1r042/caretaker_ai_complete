"""Saathi keeps a personal conversation going when Gemini is unavailable."""
import datetime as dt

from services.offline_saathi import offline_opener, offline_reply

P = {"name": "Amma",
     "profile": {"family_members": [{"name": "Rahul", "relation": "son", "is_emergency_contact": True}]},
     "favourite_media": ["Achyutam Keshavam", "Lag Jaa Gale"],
     "followup": {"id": 7, "content": "Aarav has a maths exam on Friday"},
     "memories": [{"category": "person", "content": "Grandson Aarav loves cricket"}],
     "routine": {"current": {"activity": "chai", "time": "16:00"}},
     "upcoming_dates": [{"label": "Aarav's birthday", "in_days": 1}]}


def test_help_is_emergency():
    r = offline_reply("madad karo, main gir gayi", P)
    assert r["intent"] == "emergency" and r["urgency"] == "high" and "Rahul" in r["reply"]


def test_music_uses_her_bhajan():
    r = offline_reply("koi bhajan sunao", P)
    assert r["intent"] == "play_music" and r["search_query"] == "Achyutam Keshavam" and "Amma" in r["reply"]


def test_greeting_asks_the_followup():
    r = offline_reply("namaste saathi", P)
    assert "maths exam" in r["reply"] and r["used_followup"] == 7


def test_lonely_offers_family_or_song():
    r = offline_reply("aaj bahut akela lag raha hai", P)
    assert r["mood"] == "lonely" and "Rahul" in r["reply"]


def test_medicine_and_stop_intents():
    assert offline_reply("maine dawa le li", P)["intent"] == "medicine_taken"
    assert offline_reply("gaana band karo", P)["intent"] == "stop"


def test_english_and_openers():
    assert offline_reply("I feel sad today", P, lang="en")["reply"].startswith("Amma")
    assert "birthday" in offline_opener({"reason": "important_date"}, P)
    assert "chai" in offline_opener({"reason": "routine"}, P)
    assert offline_opener({"reason": "greeting"}, P, now=dt.datetime(2026, 1, 1, 8)).startswith("सुप्रभात Amma")
