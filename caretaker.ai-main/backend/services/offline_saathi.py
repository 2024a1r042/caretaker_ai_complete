"""
offline_saathi.py — Saathi keeps talking when Gemini can't answer.

Used when the LLM is unavailable (no key, quota used up, no internet, slow
network). Before this, Saathi replied "Maaf kijiye, dikkat aa rahi hai" — the
conversation died, which is the worst possible moment in a demo or for a
lonely person.

It is deliberately simple and SAFE (no medical advice), but still personal:
it uses their name, their own bhajans/songs, the follow-up Saathi remembered,
their routine, and responds to mood, music/story requests, medicine
confirmations and emergencies with the same intents the frontend already
understands.
"""

from __future__ import annotations

import datetime as dt
import random
import re
from typing import Optional

from services.sentiment_engine import quick_mood

_HELP = re.compile(r"\b(help|madad|bachao|gir gay[ia]|fell|chot|saans nahi|can'?t breathe|chest pain|seene mein dard|"
                   r"ambulance)\b|मदद|बचाओ|गिर गय|चोट|सांस नहीं|सीने में दर्द", re.I)
_MUSIC = re.compile(r"\b(gaana|gana|gaane|song|songs|music|bhajan|bhajans|aarti|kirtan|sunao|bajao|lagao|play)\b|गाना|गाने|भजन|आरती|सुनाओ|बजाओ|लगाओ", re.I)
_STORY = re.compile(r"\b(kahani|kahaani|story|katha|kissa)\b|कहानी|कथा|किस्सा", re.I)
_STOP = re.compile(r"\b(stop|band karo|bandh karo|ruk jao|bas karo|pause)\b|बंद करो|रुको|बस करो", re.I)
_MED_TAKEN = re.compile(r"\b(dawa|dawai|dava|medicine|tablet|goli)\b.*\b(le li|kha li|li hai|taken|took|kha liya|le liya)\b|"
                        r"\b(le li|kha li|took)\b.*\b(dawa|dawai|medicine|tablet|goli)\b|दवा.*(ले ली|खा ली)", re.I)
_GREET = re.compile(r"^\s*(hi|hello|hey|namaste|namaskar|pranam|ram ram|jai shri krishna|good morning|good evening|suprabhat)\b|"
                    r"^\s*(नमस्ते|नमस्कार|प्रणाम|राम राम)", re.I)
_HOW_ARE_YOU = re.compile(r"\b(kaise ho|kaisa hai|kaisi ho|how are you|aap kaise)\b|कैसे हो|कैसी हो", re.I)


def _period(now: dt.datetime) -> str:
    h = now.hour
    return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 21 else "night"


def _pick(seq, seed):
    return seq[seed % len(seq)] if seq else None


def _t(lang: str, hi: str, en: str) -> str:
    return en if lang == "en" else hi


def offline_reply(user_text: str, personal: dict, lang: str = "hi", now: Optional[dt.datetime] = None) -> dict:
    """Returns the same JSON shape as the LLM reply (reply, intent, search_query, mood, urgency, recommendation)."""
    now = now or dt.datetime.now()
    p = personal or {}
    name = p.get("name") or "ji"
    prof = p.get("profile") or {}
    favs = p.get("favourite_media") or []
    fam = [f for f in (prof.get("family_members") or []) if isinstance(f, dict) and f.get("name")]
    first_contact = next((f["name"] for f in fam if f.get("is_emergency_contact")), fam[0]["name"] if fam else None)
    text = user_text or ""
    mood, urgency = quick_mood(text)
    seed = len(text) + now.minute
    out = {"reply": "", "intent": "chat", "search_query": "", "mood": mood, "urgency": urgency,
           "recommendation": None, "remember": None, "offline": True}

    if _HELP.search(text):
        who = first_contact or _t(lang, "आपके परिवार", "your family")
        out.update(intent="emergency", urgency="high", mood="distressed", reply=_t(
            lang,
            f"{name}, घबराइए मत, मैं यहीं हूँ। मैं अभी {who} को खबर कर रहा हूँ। हिलने की कोशिश मत कीजिए, आराम से रहिए।",
            f"{name}, don't worry, I'm right here. I'm alerting {who} now. Please try not to move."))
        return out

    if _STOP.search(text):
        out.update(intent="stop", reply=_t(lang, f"ठीक है {name}, बंद कर दिया।", f"Okay {name}, stopped."))
        return out

    if _MED_TAKEN.search(text):
        out.update(intent="medicine_taken", reply=_t(
            lang, f"बहुत अच्छा {name}! मैंने लिख लिया कि आपने दवा ले ली है।", f"Well done, {name}! I've noted that you took your medicine."))
        return out

    if _MUSIC.search(text):
        spiritual = re.search(r"bhajan|aarti|kirtan|भजन|आरती", text, re.I)
        # a specific artist/song named? ("Kishore Kumar ke gaane", "play Lag Jaa Gale")
        artist = re.search(r"([A-Za-z][A-Za-z .']{2,40}?)\s+(?:ke|ki|ka)\s+(?:gaane|gane|gaana|gana|songs?|bhajans?)", text, re.I)
        title = (re.search(r"(?:play|sunao|bajao|lagao)\s+([A-Za-z][A-Za-z .']{2,40})", text, re.I)
                 or re.search(r"([A-Za-z][A-Za-z .']{2,40}?)\s+(?:sunao|bajao|lagao|chalao)", text, re.I))
        subject = (artist or title).group(1).strip() if (artist or title) else ""
        subject = re.sub(r"^(mujhe|mere|meri|mera|aap|please|zara|jara)\s+", "", subject, flags=re.I)
        generic = {"koi", "kuch", "ek", "achha", "accha", "acha", "purane", "purana", "old", "nice", "some", "a", "the",
                   "bhajan", "bhajans", "gaana", "gaane", "gana", "gane", "song", "songs", "music", "sa", "si", "se",
                   "mujhe", "mere", "aur", "dusra", "doosra", "another", "aarti", "kirtan"}
        if subject and all(w.lower() in generic for w in subject.split()):
            subject = ""
        likes = re.search(r"pasand|love|like|achha lag|acha lag|पसंद", text, re.I)
        if subject and likes and not re.search(r"sunao|bajao|lagao|play|chalao|सुनाओ|बजाओ|लगाओ", text, re.I):
            q = f"{subject} songs"
            out.update(intent="chat", reply=_t(lang, f"वाह {name}, {subject} के गाने तो लाजवाब हैं! अभी लगाऊँ?",
                                                f"Oh {name}, {subject} songs are wonderful! Shall I play some now?"),
                       recommendation={"type": "choice", "category": "music", "choices": [q] + favs[:2],
                                       "message": _t(lang, "सुनना चाहेंगे?", "Would you like to listen?")})
            out["remember"] = [{"category": "preference", "content": f"Loves {subject} songs", "importance": 3}]
            return out
        if subject:
            q = f"{subject} songs" if artist else subject     # "X ke gaane" → artist; "play X" → a title
            out.update(intent="play_music", search_query=q, reply=_t(lang, f"ज़रूर {name}! {subject} लगा रहा हूँ।",
                                                                    f"Of course, {name}! Playing {subject}."))
            return out
        pick = None
        if favs:
            pool = [f for f in favs if re.search(r"bhajan|aarti|keshavam|krishna|ram|shiv|hanuman|भजन", f, re.I)] if spiritual else favs
            pick = _pick(pool or favs, seed)
        query = pick or ("soothing bhajan" if spiritual else "old hindi songs Lata Kishore")
        out.update(intent="play_music", search_query=query, reply=_t(
            lang, f"ज़रूर {name}! आपका पसंदीदा \"{query}\" लगा रहा हूँ।" if pick else f"ज़रूर {name}! कुछ प्यारे गाने लगा रहा हूँ।",
            f"Of course, {name}! Playing your favourite \"{query}\"." if pick else f"Of course, {name}! Playing some lovely old songs."))
        return out

    if _STORY.search(text):
        q = "akbar birbal kahani" if mood in ("bored", "happy", "neutral") else "prerak prasang hindi"
        out.update(intent="tell_story", search_query=q, reply=_t(
            lang, f"चलिए {name}, एक अच्छी सी कहानी सुनाता हूँ।", f"Let me find you a nice story, {name}."))
        return out

    fu = p.get("followup")
    if (_GREET.search(text) or _HOW_ARE_YOU.search(text)) and fu:
        out["reply"] = _t(lang, f"नमस्ते {name}! मैं ठीक हूँ, आप बताइए। और हाँ — आपने बताया था: \"{fu['content']}\"। वो कैसा रहा?",
                          f"Hello {name}! I'm well — and you? You told me earlier: \"{fu['content']}\". How did it go?")
        out["used_followup"] = fu.get("id")
        return out

    if _GREET.search(text) or _HOW_ARE_YOU.search(text):
        per = _period(now)
        r = (p.get("routine") or {}).get("current")
        hi_g = {"morning": "सुप्रभात", "afternoon": "नमस्ते", "evening": "शुभ संध्या", "night": "नमस्ते"}[per]
        en_g = {"morning": "Good morning", "afternoon": "Good afternoon", "evening": "Good evening", "night": "Hello"}[per]
        tail = (_t(lang, f" {r['activity']} का समय हो गया है — हो गया?", f" It's time for {r['activity']} — done yet?") if r else
                _t(lang, " आज आपका दिन कैसा जा रहा है?", " How is your day going?"))
        out["reply"] = _t(lang, f"{hi_g} {name}!", f"{en_g}, {name}!") + tail
        return out

    if mood in ("sad", "lonely", "anxious", "distressed", "angry"):
        offer = _pick(favs, seed)
        call = _t(lang, f" क्या {first_contact} को फ़ोन लगाऊँ?", f" Shall I call {first_contact}?") if first_contact and mood == "lonely" else ""
        song = _t(lang, f" या आपका \"{offer}\" लगाऊँ?", f" Or shall I play \"{offer}\"?") if offer else ""
        lines_hi = {"sad": f"{name}, मैं समझ सकता हूँ। मैं यहीं आपके पास हूँ।",
                    "lonely": f"{name}, आप अकेली/अकेले नहीं हैं — मैं हूँ ना आपके साथ।",
                    "anxious": f"{name}, गहरी साँस लीजिए… धीरे-धीरे। सब ठीक हो जाएगा।",
                    "distressed": f"{name}, मैं यहीं हूँ, आराम से बताइए क्या हुआ।",
                    "angry": f"{name}, आपकी बात बिल्कुल समझ रहा हूँ। थोड़ा आराम कीजिए।"}
        lines_en = {"sad": f"{name}, I understand. I'm right here with you.",
                    "lonely": f"{name}, you're not alone — I'm here with you.",
                    "anxious": f"{name}, take a slow, deep breath with me. It will be okay.",
                    "distressed": f"{name}, I'm here. Tell me slowly what happened.",
                    "angry": f"{name}, I hear you. Let's take a moment to rest."}
        out["reply"] = _t(lang, lines_hi[mood], lines_en[mood]) + (call or song)
        if offer:
            out["recommendation"] = {"type": "choice", "category": "music", "choices": favs[:3],
                                     "message": _t(lang, f"{name}, आपके पसंदीदा:", f"{name}, your favourites:")}
        return out

    if mood in ("happy", "relaxed"):
        out["reply"] = _t(lang, f"वाह {name}, सुनकर बहुत अच्छा लगा! और बताइए, आज क्या-क्या किया?",
                          f"That's lovely to hear, {name}! What else did you do today?")
        return out

    # default: reflect + one warm question, tied to something we know about them
    mems = p.get("memories") or []
    hook = _pick([m["content"] for m in mems if m.get("category") in ("person", "preference", "life_story")], seed)
    if hook:
        out["reply"] = _t(lang, f"अच्छा {name}, और बताइए। वैसे मुझे याद है — {hook}। उसके बारे में कुछ सुनाइए?",
                          f"I see, {name} — tell me more. I remember: {hook}. Tell me about that?")
    else:
        out["reply"] = _t(lang, f"अच्छा {name}, और बताइए — मैं सुन रहा हूँ।", f"I see, {name} — tell me more, I'm listening.")
    return out


def offline_opener(item: dict, personal: dict, lang: str = "hi", now: Optional[dt.datetime] = None) -> str:
    """Proactive conversation starter without the LLM."""
    now = now or dt.datetime.now()
    p = personal or {}
    name = p.get("name") or "ji"
    reason = (item or {}).get("reason", "greeting")
    if reason == "post_fall_followup":
        return _t(lang, f"{name}, अब कैसा लग रहा है? कहीं दर्द या चक्कर तो नहीं?", f"{name}, how are you feeling now? Any pain or dizziness?")
    if reason == "important_date":
        d = (p.get("upcoming_dates") or [{}])[0]
        when = _t(lang, "आज" if d.get("in_days") == 0 else "कल", "today" if d.get("in_days") == 0 else "tomorrow")
        return _t(lang, f"{name}, याद है? {when} {d.get('label', '')} है! क्या फ़ोन करके बधाई देंगे?",
                  f"{name}, remember? {d.get('label', '')} is {when}! Shall we call to wish them?")
    if reason == "memory_followup" and p.get("followup"):
        return _t(lang, f"{name}, आपने बताया था: \"{p['followup']['content']}\"। वो कैसा रहा?",
                  f"{name}, you told me: \"{p['followup']['content']}\". How did it go?")
    if reason == "routine":
        r = (p.get("routine") or {}).get("current") or {}
        return _t(lang, f"{name}, {r.get('activity', 'आराम')} का समय हो गया! हो गया क्या?",
                  f"{name}, it's time for {r.get('activity', 'a little break')}! Done yet?")
    if reason == "long_silence":
        return _t(lang, f"{name}, बहुत देर से बात नहीं हुई — आप कैसे हैं? क्या कर रहे हैं अभी?",
                  f"{name}, we haven't talked in a while — how are you? What are you up to?")
    per = _period(now)
    hi_g = {"morning": "सुप्रभात", "afternoon": "नमस्ते", "evening": "शुभ संध्या", "night": "नमस्ते"}[per]
    en_g = {"morning": "Good morning", "afternoon": "Good afternoon", "evening": "Good evening", "night": "Hello"}[per]
    return _t(lang, f"{hi_g} {name}! आज आप कैसा महसूस कर रहे हैं?", f"{en_g}, {name}! How are you feeling today?")
