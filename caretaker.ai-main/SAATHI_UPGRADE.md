# Saathi upgrade — personalization and explainable fall detection

This upgrade covers the two things the Director asked for: **human, personalized,
context-aware care** (the X-factor), and **real detection and inference from the
camera** rather than high/medium/low labels. They are joined in one flow:
*the camera sees a fall → Saathi talks to the person by name → their answer decides
whether the family is alerted.*

---

## 1. Fall detection — what was wrong and what replaced it

### Problems found in the old code
| Where | Problem |
|---|---|
| `frontend/fall_detection_tfjs.js` (the **live webcam demo**) | The angle check was **inverted**. `angleDeg` returns 0° for upright, yet the code counted `angle < 35°` (standing) as a fall cue and `angle > 50°` (lying) as "was standing". The live demo misfires on fast movement and can miss real falls. It also never used the trained BiGRU. |
| same | Speed measured in raw px/s, so the result depends on how far the person is from the camera. No "stayed down", no "got up", no "lying still". |
| `/api/video-monitoring/log-event` | Called by the live page, but **the route did not exist** (404). Live falls were never saved. |
| `united_monitor.py` (uploads + IP cameras) | Single hard gate: nothing happened unless BiGRU > 0.90 for N frames. No explanation of why an alert fired. |
| Docs vs code | Chapter 4 says 98.42% acc / F1 97.50 and threshold 0.92 × 10 frames. `metrics.txt` says 98.31% / F1 99.14. The code used 0.90 × 7. Pick one set of numbers before the review. |

### New: `FallInferenceEngine` (Python `backend/VideoMonitoring/fall_inference.py`, JS twin `frontend/static/js/fall-inference-engine.js`)
The engine reasons about what physically happens in a fall, over time:

```
NORMAL ──fast drop──▶ DESCENT ──ends on the floor──▶ ON-GROUND CHECK ──stays down──▶ FALL CONFIRMED
   │                    └ didn't end low → "sat down / bent over" (rejected)          │        │
   └─ on the floor after being up (slow slide) ─────▶ ON-GROUND CHECK                 ▼        ▼
                                                                         RECOVERED (got up)   LONG LIE (still on floor → critical)
```

**Signals.** All are scale-free (relative to the person's own standing height), so they work at any distance and frame rate:
head/hip height above the floor · peak downward speed (body-heights/s) · size of the drop · torso rotation ·
body collapse (handles falls toward/away from the camera) · time on the floor · stillness · bed/sofa zones ·
the BiGRU probability, used as **one weighted input** rather than a gate.

**Fall types.** `hard_fall`, `fall`, `slow_collapse` (sliding off a chair, common in elderly people), `out_of_view` (drops
behind a bed or sofa), `found_on_floor` (camera starts with the person already down).

**Every alert explains itself.** For example:
> *Hard fall: Head dropped 94% of standing height in 0.5 s; Peak downward speed 1.77 body-heights/s (fast, uncontrolled);
> Torso rotated 90°; Body is at floor level (hips at 4% of standing height).*

The same evidence is shown on the video overlay, in the live alert list, in the caregiver email, and on Saathi's screen.

### How it was tested (be precise about this in the review)
* `backend/VideoMonitoring/fall_scenarios.py` is a **synthetic test bench**. It poses a 3D skeleton, projects it through a
  camera, and adds pose-model noise. It covers 20 scenarios (9 look-alikes such as sitting fast, flopping on a sofa, bending, squatting,
  kneeling, lying in bed with/without a zone, and walking out of view; 11 falls / floor events) × 3 frame-rates × 3 distances × 2 seeds.
* Result at **medium** and **high** sensitivity: **360/360 runs as expected, 0 false alarms**. Typical alert latency ≈ 1.5 s after
  hitting the floor. **Low** sensitivity deliberately misses some borderline falls (recall 0.92).
* Under heavy noise (5 px jitter, 12% keypoints dropped, 10% frames dropped): 537/540.
* `frontend/tests/fall_engine_parity.test.js`: the browser engine makes **identical decisions** to the Python engine on all 20 scenarios.
* ⚠️ **Synthetic numbers are a correctness check, not real-world accuracy.** For the review, run
  `evaluate_on_videos.py` on UR Fall / Le2i plus 10–20 clips recorded in the actual demo room, and present *those*
  event-level numbers (falls caught, false alarms, seconds to alert).

---

## 2. Personalization — the X-factor

### What Saathi now knows
* **Family-entered profile** (`saathi_profile.html` → `/api/personalization/{id}/profile`): what to call them ("Amma"),
  language and mother tongue, hometown, former job, faith, favourite foods and diet limits, their own songs and bhajans, shows, hobbies,
  family (with a first contact), daily routine, important dates, life stories, and **topics to never bring up**.
* **Long-term memory learned from conversation** (`RecipientMemory`). After every message, durable facts are extracted
  (Gemini, with an offline Hindi/Hinglish/English rule fallback): *"likes Kishore Kumar songs"*, *"grandson Aarav has an exam on
  Friday"*, *"knee hurts on stairs"*. Duplicates are merged and mentions counted. The family can see and delete every memory.
* **Situation awareness:** time of day, where they are in their routine ("it's chai time"), dates coming up, and **falls in the last few
  days** ("a fall was detected yesterday and they said they were fine, so ask gently about pain").

### What Saathi does with it
* Calls them by their name. (The old WebSocket path literally said "User ji"; that's fixed.)
* Every reply gets a compact *who they are + what you remember + what's happening now* brief, with only the memories relevant to what they just said.
* **Follow-ups on the right day:** "Aarav ka exam kaisa gaya?" the day after the exam.
* **Saathi starts conversations** (`type: "proactive"`) for a reason, in this priority order: post-fall check → birthday/anniversary →
  memory follow-up → routine moment (chai, aarti) → long silence → greeting. It stays quiet during sleep hours and never repeats a nudge.
* **Music from their favourites first.** When they're low, their bhajan; when happy, their Kishore Kumar. It also learns from what they
  ask to play.
* `saathi_profile.html` includes a **"Saathi's notebook"** panel that shows exactly what Saathi knows and what it will say next.
  This is useful for the demo and for family trust.

---

## 3. Fall → Saathi → family (`backend/services/safety_bridge.py`)
1. A fall is confirmed (browser camera, IP-camera session, or `POST /api/safety/simulate/{id}` for rehearsal).
2. A `SafetyEvent` is stored with its evidence. Saathi's screen shows a large check-in and **speaks**:
   *"Amma, kya aap theek hain? Mujhe laga aap gir gaye. Agar aap theek hain toh boliye 'main theek hoon'. Madad chahiye toh 'madad'
   boliye — main turant Rahul ko bulaunga."* The microphone opens hands-free, with two big buttons as backup.
3. "main theek hoon" leads to *resolved*, and the family gets a low-urgency note. "dard / madad / uth nahi pa rahi" alerts the family **immediately**.
   **No answer in 30 s** (60 s for a slow collapse) also alerts the family. If no Saathi screen is open, the family is alerted at once.
4. The camera keeps watching. If the person **gets up**, Saathi says so and still asks about pain. If they are **lying still**, the alert
   becomes **critical** even if they said they were fine.
5. Next conversation, Saathi remembers the fall and checks how they feel.

---

## 4. Running it

```bash
# backend tests (SQLite, no Postgres / GPU / API keys needed) — 90 tests
cd backend && pip install pytest httpx && python -m pytest tests -q

# fall engine bench + export fixtures for the JS parity test
cd backend/VideoMonitoring && python evaluate_fall_engine.py --export-fixtures ../../frontend/tests/fixtures/fall_scenarios.json
node ../../frontend/tests/fall_engine_parity.test.js

# real-video evaluation (needs ultralytics + yolov8n-pose.pt + a labelled folder)
python evaluate_on_videos.py --videos /data/urfall --labels labels.csv

# give the demo person a real profile
cd backend && python scripts/seed_saathi_demo.py --recipient-id <id>
```
New tables (`recipient_profiles`, `recipient_memories`, `safety_events`) are created automatically on startup.

## 5. Suggested 5-minute demo
1. **Profile page:** show what the family entered and Saathi's notebook ("next, it will bring up Aarav's birthday").
2. **Open Saathi:** it greets her as *Amma* and brings up the birthday. Mention the knee; tomorrow it asks about the knee.
3. **Say "kuch gaana sunao"** and it offers *her* bhajan first.
4. **Live camera:** mark the bed as a zone and lie down on it (no alert). Sit down fast on a chair (no alert). Then do a controlled fall onto a mat. The
   overlay shows the drop, speed, rotation, and time on the floor, and the alert carries the explanation.
5. **Saathi asks "Amma, kya aap theek hain?"** Say "madad", and the family alert email arrives with the evidence. Re-run, say "main theek hoon", and you get the
   low-urgency note.
6. **`fall_engine_replay.html`:** step through the look-alikes vs. falls to show the inference, not just a label.

## 6. Files
New: `VideoMonitoring/fall_inference.py`, `fall_scenarios.py`, `evaluate_fall_engine.py`, `evaluate_on_videos.py`,
`services/personalization.py`, `services/safety_bridge.py`, `routes/personalization.py`, `routes/safety.py`,
`tables/personalization.py`, `tables/safety_events.py`, `scripts/seed_saathi_demo.py`, `tests/*`,
`frontend/static/js/fall-inference-engine.js`, `frontend/saathi_profile.html`, `frontend/fall_engine_replay.html`,
`frontend/tests/*`.
Changed: `united_monitor.py`, `stream_manager.py`, `routes/video_monitoring.py`, `routes/voice_bot_ws.py`,
`routes/voice_bot.py`, `services/voice_bot_engine.py`, `utils/email.py`, `main.py`, `frontend/fall_detection_tfjs.js`,
`frontend/video_monitoring.html|.js`, `frontend/voice_bot.html`.

## 7. Known limits (say these before someone else does)
* Single-camera 2D pose: falls fully hidden from the start, or in very dark rooms, can't be seen. Bed zones must be marked per camera.
* Only the *monitored* person is checked for falls; visitors are tracked but not analysed.
* The memory extractor is best with Gemini. The offline rules cover common Hindi/Hinglish/English phrasings only.
* Routine and greeting times use the server clock, so run the backend in IST.

---

## 8. Backend reliability, API key and Saathi latency

### What was wrong
| Symptom | Cause |
|---|---|
| Saathi takes ~40 s, then says "Maaf kijiye…" | Two Gemini calls per message (mood, then reply), and `call_gemini()` retried 3 models × 3 attempts with 2 s + 4 s sleeps on every 429. A used-up **daily** free-tier quota can't recover in seconds, so it measured **18 s / 9 requests per call** before failing. |
| Whole dashboard stops loading while Saathi talks | `/voice-bot/chat` (and two other routes) were `async def` but called Gemini synchronously, which freezes FastAPI's event loop so every other request waits. |
| Pages go empty after a while | Login tokens expired after 30 min and most pages silently ignored the 401. Opening the site at `localhost` vs `127.0.0.1` also "loses" the login (separate storage). |
| "API key problems" | One free-tier key shared by Saathi, reports, insights and recommendations, so the daily quota runs out. `GEMINI_API_ENDPOINT` made all fallback models hit the same URL. A rejected key was retried like a busy server. |
| Voice slow / missing | Cloud TTS needs `GOOGLE_APPLICATION_CREDENTIALS` (not the Gemini key). Without it, each reply searched for credentials before failing, and a new client was created per message. |
| Misc | `elderly` routes were mounted at `/api/api/elderly/...`. DB connections weren't health-checked. DB password and a real email were committed in scripts. |

### What changed
* **`utils/gemini_client.py`** reads Google's 429 details: on a **daily** limit the model is skipped until the quota resets (midnight Pacific ≈ 1:30 PM IST), and on a **per-minute** limit it honours `retryDelay`. A rejected key → fails immediately with a clear log line. One total time budget per call. Keep-alive HTTPS session. `fast=True` turns off 2.5-Flash "thinking" for chat. Exhausted quota: **18 s → 0 s**, and later calls make **zero** requests.
* **One Gemini call per Saathi message.** The reply JSON now also returns `mood`, `urgency` and `remember` (memories), so the separate sentiment call and the extra memory call are gone. That halves quota use and removes a full round-trip. The tone is set instantly by an offline Hindi/Hinglish/English mood detector. JSON mode (`responseMimeType`) cuts parse failures.
* **No more server freezes:** blocking routes run in the thread pool. The WebSocket offloads DB, sentiment, LLM and TTS work.
* **TTS:** one client, credentials checked once, off for the session on auth/billing errors, 6 s timeout, and cached phrases. Without credentials it returns instantly and the browser voice speaks.
* **Logins:** `js/auth-guard.js` on every signed-in page. An expired session shows a message and returns the user to the page after login. Token lifetime is now 12 h (`ACCESS_TOKEN_EXPIRE_MINUTES`).
* **`GET /api/health/ai`** tells you in plain words whether the key is missing or rejected, which models are out of quota and for how long, the last Gemini latency, TTS status and DB status. Open it first whenever Saathi misbehaves.
* `backend/.env.example` added; committed credentials removed; `pool_pre_ping` on the DB.
* Saathi's screen stops "typing…" after 28 s with a polite retry message. Every reply logs `timing: prep … tts … total …` in the backend console.

### For the demo
1. Use a **billed** Gemini key (or a fresh key that hasn't been used that day). Free daily quotas are tiny.
2. Open `http://127.0.0.1:8000/api/health/ai` before starting. It should say "All good."
3. Always open the frontend at the same address you logged in on (pick `127.0.0.1`).

---

## 9. Verified end-to-end (real server, real browser, real video)

Everything below was run against the **actual backend** (`uvicorn main:app`, every route,
Socket.IO, scheduler) and the **actual frontend pages** in Chromium:

| Check | Result |
|---|---|
| Sign up → log in through `login.html` → dashboard loads | ✅ |
| Family profile page saves; "Saathi's notebook" updates | ✅ |
| Saathi greets "सुप्रभात Amma!" and replies to "aaj bahut akela lag raha hai" by offering to call Rahul | ✅ (offline mode — no key in the test) |
| Fall reported by the live camera page → spoken check-in overlay → "मैं ठीक हूँ" → resolved, family notified | ✅ |
| Memory learned from chat ("Likes Kishore Kumar…") | ✅ |
| Real fall video uploaded through `video_monitoring.html` → analysed in 34 s on CPU → playable annotated video + evidence | ✅ |
| 111 automated tests (fresh install from the slim requirements) | ✅ |

### Bugs found only by running it for real (all fixed)
* **Backend crashed on the first uploaded video**: TensorFlow (loaded at startup for an
  *untrained* audio network) + PyTorch in one process → segfault. TensorFlow is no longer
  loaded in the server; if trained audio weights are added it runs in a helper process.
* **Backend would not start without email settings** (`MAIL_*` "optional" in the README
  but required by the code). Email is now genuinely optional (alerts are logged instead).
* **`pip install -r requirements.txt` could not work**: `fastapi==0.68.2` vs `pydantic==2.12.5`.
  Requirements fixed and slimmed (TensorFlow, TF-Hub, DeepFace, pandas, joblib were unused —
  about 2 GB less), plus a tested lock file `requirements-windows-py311.lock.txt`.
* **Dashboard JS crashed on load** (`audioTimeRange` element no longer exists).
* **Pages depended on CDNs** — and Saathi on an unpinned `lucide@latest`. All libraries are now
  pinned and served from `frontend/vendor/` (works on venue Wi-Fi that blocks CDNs;
  only Google Fonts and the MoveNet model download still need internet).
* **Analysed videos wouldn't play on Windows without ffmpeg** → bundled `imageio-ffmpeg` fallback.
* **Real-footage fall-detection fixes**: see `backend/VideoMonitoring/real_clips/README.md`
  (BiGRU saturates at ~1.0 on normal activity → demoted to one input; yolov8n-pose misses lying
  people → yolov8s-pose default; falls that slide out of view now alert).

### Saathi without Gemini
If the key is missing, the quota is used up, or the internet drops, Saathi now **keeps the
conversation going** (`services/offline_saathi.py`) — by name, with her own bhajans, the
follow-up it remembered, mood-aware comfort, music/story/medicine/emergency intents —
instead of "Maaf kijiye, dikkat aa rahi hai". Replies are marked `offline: true`.
With a working key, Gemini is used as before (one call per message).

## 10. Quick start (Windows)
```powershell
.\setup_windows.ps1      # once: Python 3.11 venv + packages + backend\.env (SQLite quick-start)
notepad backend\.env     # add GEMINI_API_KEY (and PostgreSQL DATABASE_URL for real use)
.\run_windows.ps1        # starts backend :8000 + frontend :5500, prints AI health, opens the app
```
Always use `http://127.0.0.1:5500` (not `localhost`) — they keep separate logins.
