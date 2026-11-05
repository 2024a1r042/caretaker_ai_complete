from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio
import json
import time
from sqlalchemy.orm import Session
from config import get_db
from tables.users import CareRecipient, CareTaker
from repository.users import UsersRepo
from utils.gemini_client import call_gemini, safe_json_parse
from utils.tts_handler import generate_speech_base64, is_hindi

from tables.conversation_history import MoodEnum, SenderEnum, TriggerTypeEnum
from services.voice_bot_engine import (
    build_conversation_context, generate_system_prompt,
    save_message, check_depression_risk, get_content_recommendation, set_last_user_mood
)
from services.sentiment_engine import analyze_sentiment_with_history
from services import personalization as P
from services.safety_bridge import safety_bridge
from services.offline_saathi import offline_reply, offline_opener

router = APIRouter(tags=["VoiceBot WS"])


def _get_username_from_token(token: str):
    try:
        from repository.users import JWTRepo
        decoded = JWTRepo.decode_token(token)
        return decoded.get('sub') if isinstance(decoded, dict) else None
    except Exception:
        return None


VALID_MOODS = {m.value for m in MoodEnum}

# One Gemini call per message: JSON mode, no "thinking", bounded by a 20 s budget
GEN_CONFIG = {"maxOutputTokens": 700, "temperature": 0.7, "responseMimeType": "application/json"}
REPLY_BUDGET_S = 20


def _parse_ai(ai_text: str) -> dict:
    parsed = safe_json_parse(ai_text) or {}
    return {
        "mood": parsed.get("mood") if parsed.get("mood") in VALID_MOODS else None,
        "urgency": parsed.get("urgency") if parsed.get("urgency") in ("low", "medium", "high") else None,
        "remember": parsed.get("remember") if "remember" in parsed else None,
        "reply": parsed.get("reply") or parsed.get("message") or ai_text,
        "intent": parsed.get("intent", "chat") if parsed else "chat",
        "search_query": parsed.get("search_query", "") if parsed else "",
        "action_param": parsed.get("action_param") if parsed else None,
        "recommendation": parsed.get("recommendation") if parsed else None,
    }


def _owned_recipient(db: Session, caretaker, rid: int):
    return db.query(CareRecipient).filter(CareRecipient.id == rid, CareRecipient.caretaker_id == caretaker.id).first()


@router.websocket("/ws/voice-chat")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    safety_bridge.set_loop(asyncio.get_running_loop())

    caretaker = None
    registered_for = None

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON payload"})
                continue

            token = payload.get("token")
            if token and not caretaker:
                username = _get_username_from_token(token)
                if username:
                    caretaker = UsersRepo.find_by_username(db, CareTaker, username)
            if not caretaker:
                await websocket.send_json({"error": "Unauthorized. Please provide a valid token."})
                continue

            action = payload.get("type", "chat")
            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if action == "interrupt":
                continue

            try:
                recipient_id = int(payload.get("recipient_id") or 1)
            except (TypeError, ValueError):
                recipient_id = 1
            recipient = _owned_recipient(db, caretaker, recipient_id)
            if recipient is None:
                await websocket.send_json({"error": "Recipient not found for this account."})
                continue

            # This screen is where Saathi can talk to this person → the safety bridge
            # uses it to check on them the moment a fall is detected.
            if registered_for != recipient_id:
                if registered_for is not None:
                    safety_bridge.unregister(websocket)
                safety_bridge.register(recipient_id, websocket)
                registered_for = recipient_id

            session_id = payload.get("session_id", "ws_session")
            lang = payload.get("language", "hi")

            if action == "hello":
                await websocket.send_json({"type": "hello_ack", "recipient_id": recipient_id})
                continue

            # ── The person's answer to a fall check-in ──
            if action == "safety_response":
                try:
                    res = await safety_bridge.handle_response(int(payload.get("event_id")), payload.get("text", ""))
                except Exception as e:
                    res = {"status": "error", "reply": "", "error": str(e)}
                await websocket.send_json({"type": "safety_update", "event_id": payload.get("event_id"),
                                           "status": res.get("status"), "text": res.get("reply", ""),
                                           "audio_base64": res.get("audio_base64", ""),
                                           "keep_listening": res.get("keep_listening", False),
                                           "verdict": res.get("verdict")})
                continue

            # ── Saathi starts the conversation (greeting / routine / follow-up / date / post-fall) ──
            if action == "proactive":
                try:
                    item = P.next_proactive_checkin(db, recipient_id, recipient.full_name,
                                                    force=bool(payload.get("force")))
                    if not item:
                        await websocket.send_json({"type": "proactive_none"})
                        continue
                    context = build_conversation_context(recipient_id, db)
                    prompt = generate_system_prompt(recipient.full_name, context, lang, None,
                                                    proactive_instruction=item["instruction"])
                    data = await asyncio.to_thread(call_gemini, {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": dict(GEN_CONFIG, temperature=0.8)},
                        REPLY_BUDGET_S, "[voice_bot_ws/proactive]", None, True)
                    if data and data.get("candidates"):
                        ai = _parse_ai(data["candidates"][0]["content"]["parts"][0]["text"].strip())
                    else:   # LLM unavailable → Saathi still starts the conversation, personally
                        ai = {"reply": offline_opener(item, context.get("personal") or {}, lang), "intent": "chat",
                              "search_query": "", "action_param": None, "recommendation": None}
                    P.mark_proactive_done(db, recipient_id, item["key"])
                    if item.get("memory_id"):
                        P.mark_followed_up(db, item["memory_id"])
                    save_message(recipient_id, SenderEnum.bot, ai["reply"], MoodEnum.neutral,
                                 TriggerTypeEnum.proactive_checkin, session_id, db)
                    lang_code = "hi-IN" if is_hindi(ai["reply"]) else "en-US"
                    await websocket.send_json({
                        "type": "bot_response", "proactive": True, "proactive_reason": item["reason"],
                        "reply": ai["reply"], "intent": ai["intent"], "search_query": ai["search_query"],
                        "action_param": ai["action_param"], "recommendation": ai["recommendation"],
                        "audio_base64": await asyncio.to_thread(generate_speech_base64, ai["reply"], lang_code),
                        "mood_detected": "neutral", "depression_risk": False,
                        "sentiment": {"trend": "stable", "summary": ""}})
                except Exception as e:
                    print(f"[voice_bot_ws] proactive error: {e}")
                    await websocket.send_json({"type": "proactive_none"})
                continue

            # ── Regular chat ──
            try:
                user_text = payload.get("text")
                if not user_text:
                    continue
                trigger_type = TriggerTypeEnum.user_initiated

                t_start = time.monotonic()
                # Mood for Saathi's tone: instant local estimate. The reply call below
                # returns the real mood, so there is no second Gemini call per message.
                sentiment = await asyncio.to_thread(analyze_sentiment_with_history, user_text, recipient_id, db, 10, False)
                mood_str = sentiment.get("current_mood", "neutral")
                mood_enum = MoodEnum(mood_str) if mood_str in VALID_MOODS else MoodEnum.neutral

                context = await asyncio.to_thread(build_conversation_context, recipient_id, db, user_text)
                save_message(recipient_id, SenderEnum.user, user_text, mood_enum, trigger_type, session_id, db)

                system_prompt = generate_system_prompt(recipient.full_name, context, lang, sentiment)

                data = await asyncio.to_thread(call_gemini, {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser says: {user_text}"}]}],
                    "generationConfig": GEN_CONFIG},
                    REPLY_BUDGET_S, "[voice_bot_ws]", None, True)
                t_llm = time.monotonic()

                personal = context.get("personal") or {}

                offline = not (data and data.get('candidates'))
                if not offline:
                    ai = _parse_ai(data['candidates'][0]['content']['parts'][0]['text'].strip())
                else:
                    # Gemini unavailable (no key / quota / network): keep the conversation alive
                    ai = offline_reply(user_text, personal, lang)
                    ai.setdefault("action_param", None)
                    if ai.get("used_followup"):
                        P.mark_followed_up(db, ai["used_followup"])
                reply_text, intent = ai["reply"], ai["intent"]
                save_message(recipient_id, SenderEnum.bot, reply_text, MoodEnum.neutral, trigger_type, session_id, db)

                # mood + urgency came back with the reply
                if ai["mood"]:
                    mood_str = ai["mood"]
                    set_last_user_mood(recipient_id, session_id, mood_str, db)
                if ai["urgency"]:
                    sentiment["urgency"] = ai["urgency"]
                is_at_risk = check_depression_risk(recipient_id, db) or sentiment.get("urgency") == "high"
                # durable facts came back with the reply too (rules if the field was missing)
                try:
                    P.learn_from_reply(db, recipient_id, user_text, ai["remember"])
                except Exception as _le:
                    print(f"[voice_bot_ws] memory save failed: {_le}")

                # the follow-up we put in the prompt has now had its chance
                if personal.get("followup") and not offline:
                    P.mark_followed_up(db, personal["followup"]["id"])
                # what they choose to hear teaches us their taste
                if intent in ("play_music", "play_video", "tell_story") and ai["search_query"]:
                    P.record_media_interest(db, recipient_id, ai["search_query"],
                                            "story" if intent == "tell_story" else "music")

                recommendation = ai["recommendation"]
                if not recommendation and mood_str not in ("neutral",):
                    recommendation = (P.personalize_recommendation(mood_str, personal)
                                      or get_content_recommendation(mood_str))

                lang_code = "hi-IN" if is_hindi(reply_text) else "en-US"
                audio_base64 = await asyncio.to_thread(generate_speech_base64, reply_text, lang_code)
                t_done = time.monotonic()
                print(f"[voice_bot_ws] timing: prep {t_llm - t_start:.2f}s (LLM incl.) · "
                      f"tts {t_done - t_llm:.2f}s · total {t_done - t_start:.2f}s")

                await websocket.send_json({
                    "type": "bot_response",
                    "offline": offline,
                    "timing_ms": {"llm_and_prep": int((t_llm - t_start) * 1000),
                                  "tts": int((t_done - t_llm) * 1000)},
                    "reply": reply_text,
                    "intent": intent,
                    "search_query": ai["search_query"],
                    "action_param": ai["action_param"],
                    "audio_base64": audio_base64,
                    "mood_detected": mood_str,
                    "depression_risk": is_at_risk,
                    "recommendation": recommendation,
                    "sentiment": {
                        "trend": sentiment.get("trend", "stable"),
                        "summary": sentiment.get("summary", "")
                    }
                })

            except Exception as e:
                print(f"[voice_bot_ws] Message processing error: {e}")
                try:
                    await websocket.send_json({"error": str(e)})
                except Exception:
                    pass

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except ConnectionResetError:
        pass
    except Exception as e:
        print(f"[WS] Unhandled error: {e}")
    finally:
        safety_bridge.unregister(websocket)
