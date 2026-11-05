# CARETAKER.AI — COMPLETE VERIFIED PROJECT DOCUMENT (INTERVIEW READY)

> **Every detail below is verified directly from the source code.**  
> Corrections from your original draft are marked ⚠️ **CORRECTED**.

---

## 🔷 1. PROJECT TITLE

**Caretaker.ai — AI-Powered Elderly Safety and Monitoring System**

---

## 🔷 2. INTRODUCTION

Caretaker.ai is a full-stack, AI-driven elderly care platform that ensures safety and delivers continuous, intelligent assistance to elderly individuals — especially those living alone or in care homes.

The system combines:
- **Real-time computer vision** (fall detection, inactivity monitoring)
- **Ambient audio monitoring** (cough/sneeze detection)
- **Conversational AI companion** ("Saathi" voice bot)
- **Medical intelligence** (report ingestion, lab tracking, disease progression)
- **IoT hardware integration** (vitals collection via ESP8266)
- **Automated notifications** (email alerts, medicine reminders, auto-reorder)

---

## 🔷 3. PROBLEM STATEMENT

Falls and medical emergencies among elderly individuals are often undetected for extended periods. The core gaps are:

- Inability to call for help after a fall
- Delayed caregiver response
- Reliance on manual monitoring and wearables
- No emotionally intelligent companion layer

Caretaker.ai addresses all of these through autonomous, AI-powered monitoring.

---

## 🔷 4. OBJECTIVES

- Detect falls in real-time using hybrid deep learning (no wearables required)
- Provide instant multi-channel alerts to caregivers
- Enable ambient audio monitoring for respiratory events
- Deliver an emotionally aware AI companion that speaks Hindi/English
- Automate medical tracking — from report upload to disease progression alerts
- Manage medication schedules with auto-reminders and auto-reorder
- Integrate IoT hardware to collect biometric vitals
- Build a scalable, role-based, secure web platform

---

## 🔷 5. SYSTEM OVERVIEW

Caretaker.ai has **7 integrated modules:**

| Module | Core Technology |
|---|---|
| ⭐ Fall Detection | YOLOv8n-pose + BiGRU + Self-Attention |
| Audio Monitoring | CRNN (TensorFlow) + Acoustic Rule Engine |
| Voice Bot "Saathi" | Google Gemini API + Sentiment Engine |
| Medical Intelligence | Gemini API + OCR (Tesseract/pdfplumber) |
| Notifications | SMTP Email + Background Scheduler Thread |
| IoT Vitals | ESP8266 + MAX30102 + MLX90614 → FastAPI |
| Face Recognition | DeepFace (ArcFace backend) |

---

## 🔷 6. SYSTEM ARCHITECTURE

```
User's Camera → Frame Capture → YOLOv8n-pose (17 COCO keypoints)
                                     ↓
                          normalize_keypoints()
                          [Hip-centred, torso-scaled]
                                     ↓
                       FallSequenceBuffer (30 frames)
                                     ↓
                    BiGRU (Bidirectional GRU, 128 hidden, 2 layers)
                                     ↓
                    Self-Attention Layer (additive attention)
                                     ↓
                    Classifier → [Normal | Fall]
                                     ↓
                  Confirmation Engine (N consecutive frames threshold)
                                     ↓
                    Alert → Socket.IO → Frontend + Email
```

---

## 🔥 7. CORE MODULE — FALL DETECTION SYSTEM (EXACT TECHNICAL DETAILS)

### ⚠️ 7.1 MAJOR CORRECTION: The Model is Called `FallLSTM` but Uses **BiGRU**

> Your original document said "YOLOv8 + BiGRU" which is **correct at the concept level**, but there are many additional true details from the actual code you should know.

The class is named `FallLSTM` (file: `fall_lstm_model.py`), but internally it uses a **Bidirectional GRU** — not a standard LSTM layer. The confusion is intentional naming from development.

---

### 7.2 YOLO STAGE — Pose Estimation

- **Model:** `yolov8n-pose.pt` (nano variant — extremely fast)
- **Output:** 17 COCO keypoints per person (x, y coordinates + confidence per joint)
- **Function call:** `results[0].keypoints.xy` and `.conf` from Ultralytics API

**COCO Keypoints detected (all 17):**
> Nose, Eyes (L/R), Ears (L/R), Shoulders (L/R), Elbows (L/R), Wrists (L/R), Hips (L/R), Knees (L/R), Ankles (L/R)

---

### 7.3 KEYPOINT NORMALIZATION (`normalize_keypoints`)

This is a crucial step — raw pixel coordinates are **not fed directly** to the model.

**Process:**
1. Calculate **hip midpoint** (avg of left hip + right hip keypoints)
2. Calculate **shoulder midpoint**  
3. Calculate **torso length** = Euclidean distance (hip_mid → shoulder_mid)
4. **Subtract hip_mid** from all 34 coordinates (centers the skeleton)
5. **Divide by torso** (scales to body size — works for any camera distance)
6. Zero out low-confidence keypoints (threshold: 0.2)

**Output:** A **34-dimensional float32 vector** per frame (17 keypoints × 2 coordinates)

**Why this matters in interview:** *"We make the model scale-invariant and position-invariant. Whether the camera is close or far, the normalized keypoint vector looks the same for the same pose. This is critical for generalizing across different room setups."*

---

### 7.4 SEQUENCE BUFFER (`FallSequenceBuffer`)

- **Type:** Rolling ring buffer using Python `deque(maxlen=30)`
- **Sequence length:** **30 frames** per inference window
- **Sliding window stride:** 15 frames (50% overlap during training)
- **Frame skip during extraction:** every 2nd frame (`FRAME_SKIP=2`)
- **Buffer ready flag:** triggers inference when buffer fills up

---

### 7.5 MODEL ARCHITECTURE (`FallLSTM` class)

```python
Input: (batch, 30, 34)  # 30-frame sequence, 34 features each

BatchNorm1d(34)          # Input normalization per frame

BiGRU:
  - input_size  = 34
  - hidden_size = 128
  - num_layers  = 2
  - bidirectional = True
  - dropout = 0.4

Output of BiGRU: (batch, 30, 256)  # 128×2 because bidirectional

Self-Attention Layer:
  - nn.Linear(256, 1) → scores over 30 frames
  - softmax → attention weights
  - weighted sum → context vector (batch, 256)

Classifier Head:
  - Linear(256 → 64) → ReLU → Dropout(0.4) → Linear(64 → 2)

Output: logits [Normal, Fall]  → softmax for probability
```

**Constants (exact values from code):**
| Parameter | Value |
|---|---|
| `DEFAULT_SEQ_LEN` | 30 frames |
| `INPUT_FEATURES` | 34 (17 keypoints × 2) |
| `HIDDEN_SIZE` | 128 |
| `NUM_LAYERS` | 2 |
| `DROPOUT` | 0.4 |

---

### 7.6 WHY BIDIRECTIONAL? (Self-Attention detail)

**Bidirectional GRU** processes the 30-frame sequence in **both forward and backward** directions — the output is 256-dimensional (128 forward + 128 backward) per frame.

**Self-Attention Layer** then learns to **assign different weights** to each of the 30 frames — important frames (the fall moment) get higher attention weight. This is better than just using the last hidden state.

*"We use additive (Bahdanau-style) self-attention. So if the model is looking at a fall event where the actual collapse happens at frame 22, the attention mechanism will focus there — not average everything."*

---

### 7.7 TRAINING DETAILS (EXACT from `train_lstm.py`)

| Setting | Value |
|---|---|
| Optimizer | **Adam** (lr=1e-3, weight_decay=1e-4) |
| Loss Function | **Weighted CrossEntropyLoss** (handles class imbalance) |
| Epochs | **50** |
| Batch Size | **32** |
| Scheduler | **CosineAnnealingLR** (T_max=50) |
| Gradient Clipping | `clip_grad_norm_` max 1.0 |
| Val Split | **80/20 GroupShuffleSplit** |
| Best Checkpoint | Saved by **highest F1 score** |

**Metrics tracked:**
- Accuracy, Precision, **Recall**, **F1 Score** (all per epoch)
- Best model saved when F1 improves
- Checkpoint stores: val_accuracy, val_f1, val_precision, val_recall

---

### 7.8 ⚠️ CORRECTED: DATASETS USED

Your original document mentioned "UR Fall Detection Dataset" and "Le2i Fall Detection Dataset."

**From the actual code (`extract_keypoints.py`):**

The dataset folder is `C:\Users\hp\Downloads\Dataset` with:
- **`Fall/`** folder — fall videos (`.avi` and `.mp4`)
- **`Normal activities/`** folder — normal ADL videos

The filename patterns handled reveal the actual datasets:
- **`cNNcamM.avi` pattern** (e.g. `c18cam3.avi`) → **Le2i Fall Detection Dataset** ✅
- **`fall-NN-camM.mp4` pattern** (e.g. `fall-03-cam0.mp4`) → **UR Fall Detection Dataset** ✅
- **`adl-NN-camM.mp4` pattern** (e.g. `adl-01-cam0.mp4`) → **UR Fall Detection Dataset (ADL sequences)** ✅

Both datasets include **multiple camera angles per event** — which is why GroupShuffleSplit is used to prevent data leakage (all camera angles of the same fall event stay in the same train/val split).

---

### 7.9 DATA PREPROCESSING PIPELINE (Complete)

```
Video file (.avi / .mp4)
    ↓ cv2.VideoCapture
Every 2nd frame examined (FRAME_SKIP=2)
    ↓ yolov8n-pose inference
17 COCO keypoints extracted per person
    ↓ normalize_keypoints()
34-dim float32 vector
    ↓ Sliding window (seq_len=30, stride=15)
Sequences: shape (N, 30, 34)
    ↓ Saved as .npy files
sequences.npy, labels.npy, groups.npy
    ↓ GroupShuffleSplit (by event, no leakage)
Train 80% / Val 20%
    ↓ Weighted CrossEntropyLoss training
Saved checkpoint: fall_lstm.pth
```

---

### 7.10 LIVE INFERENCE — REAL-TIME PIPELINE (`UnitedMonitor`)

The `UnitedMonitor` class combines fall detection + inactivity tracking:

**Sensitivity Presets (exact values from code):**

| Mode | `lstm_thresh` | `confirm_frames` | Live `lstm_thresh` | Live `confirm_frames` |
|---|---|---|---|---|
| Low | 0.85 | 5 | 0.95 | 12 |
| **Medium (default)** | **0.80** | **4** | **0.92** | **10** |
| High | 0.72 | 3 | 0.88 | 6 |

**Why stricter thresholds in live mode?**  
*"Webcam angles differ from training data. We use stricter thresholds — requiring 10 consecutive high-confidence frames before alerting — to suppress false positives from real-world scenarios."*

**Inactivity module:**  
A separate `InactivityMonitor` tracks the centroid of the person's bounding box. If the person hasn't moved for N seconds (default 30s), an inactivity alert fires.

**Fall hold logic:**  
A confirmed fall state persists for **5 seconds** after the last LSTM trigger, then auto-resets and clears the sequence buffer — requiring fresh evidence for the next alert.

---

### 7.11 CHALLENGES (Accurate Version)

1. **Distinguishing falls from lying/sitting:** Temporal sequence analysis (BiGRU) catches the *transition*, not just the final posture
2. **False positives in live mode:** Stricter thresholds + confirmation frames counter
3. **Dataset imbalance:** Weighted CrossEntropyLoss balances fall vs. normal samples
4. **Camera angle generalization:** Hip-centered, torso-scaled normalization = scale/position invariant
5. **Group leakage:** GroupShuffleSplit ensures all camera angles of one event stay together
6. **Real-time latency:** YOLOv8n (nano model) + frame skipping maintains throughput

---

## 🔷 8. AUDIO MONITORING MODULE — "SonicGuard"

**Files:** `backend/services/audio_detection.py`, `backend/coughandsneezedetection/`

### Architecture: Dual-Engine

**Engine 1: Acoustic Feature Analyzer** (primary, always active)
- **Rule-based** signal processing
- Uses Zero-Crossing Rate, energy, spectral features
- Classifies into: **Cough**, **Sneeze**, **Talking**, **Noise**

**Engine 2: CRNN Model** (secondary, optional confidence boost)
- **Convolutional Recurrent Neural Network** built with TensorFlow/Keras
- Input: **64×101×1 mel-spectrogram** (log-mel features)
- Only activates if acoustic analyzer ALREADY suspects Cough/Sneeze
- **Blend ratio:** 70% acoustic + 30% CRNN (acoustic is more reliable)

**Parameters:**
- Confidence threshold: **60%**
- Chunk duration: **500ms** sliding windows
- Overlap ratio: **50%** (slide = 250ms)
- Sample rate: configurable (`AUDIO_TARGET_SR = 16000 Hz`)

**There is ALSO a separate Face Detection Model (`/model/` folder):**
- Trained via **Teachable Machine v2 (TensorFlow.js)**
- Labels: `Background Noise`, `cough`, `snore`
- Served from backend at `/api/model` as `model.json + weights.bin`

---

## 🔷 9. VOICE BOT — "SAATHI" AI COMPANION

**Files:** `backend/services/voice_bot_engine.py`, `backend/routes/voice_bot.py`

**Saathi** is an emotionally intelligent conversational AI for the elderly person.

### Key Features:

**1. Mood Detection (10 moods):**
> happy, sad, anxious, angry, neutral, distressed, lonely, bored, relaxed, spiritual

Uses **Google Gemini API** to analyze text → returns mood + confidence JSON.

**2. Sentiment Engine (`sentiment_engine.py`):**
- Pulls last 10 user messages from DB
- Computes: **trend** (improving/worsening/stable), **stability score**, **dominant mood**
- Sends full conversation arc to Gemini for deep analysis
- Returns `SentimentContext` dict fed into system prompt

**3. Content Recommendations:**
- Mood → Music (YouTube queries) or Story (YouTube queries)
- Example: `sad` → queries like "soft emotional hindi songs", "soothing old bollywood songs"
- `bored` → story suggestions with category (historical, mythological, comedy, spiritual, horror, adventure, romantic)

**4. Language Support:**
- Hindi (Devanagari script — for correct TTS pronunciation)
- English
- System prompt dynamically switches language

**5. Emotional State Output:**
- `aaj bahut khush lag rahe hain!` — warm Hinglish summaries
- Trend emoji: 📈 improving, 📉 worsening, ➡️ stable

**6. Depression Risk Detection:**
- If 4+ messages in last 7 days are sad/anxious/distressed/lonely → triggers caregiver alert

**7. Google Cloud TTS:**
- Converts Saathi's text responses to audio (using `google-cloud-texttospeech`)

**8. Spotify Integration:**
- Music playback directly from `/frontend/frontend/js/spotify_player.js`
- Backend route: `backend/routes/spotify.py`

---

## 🔷 10. MEDICAL INTELLIGENCE

**Files:** `backend/services/`

### Report Ingestion (`report_ingestion.py`)
- Accepts `.pdf`, `.docx`, image uploads
- Libraries: **PyPDF2**, **pdfplumber**, **python-docx**, **Pillow**, **Pytesseract** (OCR)
- Extracts text → sends to Gemini for structured parsing

### Lab Value Extraction (`lab_value_extractor.py`)
- Extracts: HbA1c, Glucose, BP, Hemoglobin, Creatinine, eGFR, TSH, etc.
- Detects **critical thresholds** (e.g. Glucose < 40 or > 400 → CRITICAL alert)

### Disease Progression (`disease_progression.py`)
- Tracks lab values over time
- Detects status transitions: `active → controlled → improving → resolved → worsening`
- Computes `pct_change_from_previous` for each metric

### Alert Engine (`alert_engine.py`)
- **Alert throttling:** `cooldown_until` per condition (7-day default, disease-specific)
- **Change threshold:** alerts only when % change ≥ disease-specific threshold
- **Monitoring gap detection:** alerts if lab not checked in `freq_months` interval
- Alert types: worsening, improving, resolved, monitoring_gap, critical

### Disease Dictionary
- Seeded on startup with disease codes, monitoring frequencies, metrics, alert cooldowns

### Medical History AI (`medical_history_ai.py`)
- AI-generated summaries using Gemini API

### Insights Engine (`insights_engine.py`)
- Trends, patterns, predictive health insights shown on Doctor Dashboard

---

## 🔷 11. NOTIFICATION SYSTEM

**Files:** `backend/services/notification_scheduler.py`, `backend/services/email_notifications.py`

### Background Scheduler Thread
- Runs in a **daemon thread** (starts on FastAPI startup)
- Polls every **60 seconds**

### Jobs:
| Job | Frequency | Action |
|---|---|---|
| Medicine Reminders | Every minute | Email at schedule_time slots (HH:MM) |
| Medication Expiry | Once/day | Auto-mark `completed` if `end_date` passed |
| Report Reminders | Once/day | Email if no report for 30+ days |
| Stock Decrement | Once/day | Subtract `doses_per_day` from `current_stock` |
| Auto-Reorder | Once/day | Email Tata 1mg link if stock ≤ 7 days remaining |

### Email Service
- SMTP via **Gmail** (`smtp.gmail.com:587`, STARTTLS)
- Config via environment variables: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`
- Sends HTML-formatted branded emails

---

## 🔷 12. IoT HARDWARE INTEGRATION

**File:** `backend/esp8266_vitals_sender.ino`

### Hardware:
- **Board:** NodeMCU / Wemos D1 Mini (**ESP8266**)
- **Sensor 1:** MAX30102 — Heart Rate + SpO2 (blood oxygen)
- **Sensor 2:** MLX90614 — Non-contact infrared temperature

### How it works:
1. ESP8266 connects to WiFi
2. Every **30 seconds**: reads MAX30102 (100 samples, runs SparkFun algorithm) + MLX90614
3. Sends JSON via **HTTP POST** to `FastAPI /api/vitals/record`
4. Authentication: shared `ESP_SECRET_KEY` in request body
5. Validation: HR between 0-300 bpm, SpO2 between 70-100%, Temp between 25-45°C

---

## 🔷 13. CAREGIVER INTERFACE

**File:** `frontend/dashboard.html`, `frontend/video_monitoring.html`

- **Real-time video feed** via WebSocket/Socket.IO
- Fall alerts surface immediately with LSTM confidence score
- Inactivity timer displayed
- Fall history, audio event log
- Medication management panel
- Medical reports upload
- Live vitals dashboard (from ESP8266 data)
- Weather widget (location-aware)

---

## 🔷 14. DOCTOR DASHBOARD

**File:** `frontend/doctor_dashboard.html`, `backend/routes/doctor.py`

- Role-based access (Doctor vs. CareTaker roles via JWT)
- View patient lab history and trends
- Disease progression timeline
- Insights Engine visualizations
- Write doctor remarks
- Upload/view medical reports

---

## 🔷 15. FACE RECOGNITION (Bonus Feature)

- **Library:** `DeepFace` (ArcFace backend) — listed in `requirements.txt`
- Registration flow: `register_emotion_user.py`, `frontend/face-registration.js`
- Used for: elderly person identity verification, emotion detection

---

## 🔷 16. COMPLETE TECHNOLOGY STACK

### Backend
| Layer | Technology |
|---|---|
| Framework | **FastAPI** (Python) |
| ASGI Server | **Uvicorn** |
| Real-time | **Socket.IO** (python-socketio) — `socket_manager.py` |
| ORM | **SQLAlchemy** |
| Database | **PostgreSQL** (primary, via `DATABASE_URL` env var) + **SQLite** (caretaker.db, sql_app.db for dev) |
| Auth | **JWT** (python-jose, HS256 algorithm) |
| Email | **smtplib** / SMTP Gmail |

### AI / ML
| Model | Technology |
|---|---|
| Fall Detection (YOLO) | **Ultralytics YOLOv8n-pose** |
| Fall Detection (sequence) | **PyTorch BiGRU** + Self-Attention |
| Audio Detection | **TensorFlow/Keras CRNN** + Acoustic Analyzer |
| NLP / LLM | **Google Gemini API** (`google-generativeai`) |
| Text-to-Speech | **Google Cloud TTS** (`google-cloud-texttospeech`) |
| Face Recognition | **DeepFace** (ArcFace) |
| OCR | **Pytesseract** + **pdfplumber** + **pdf2image** |

### Frontend
| Layer | Technology |
|---|---|
| UI | **Vanilla HTML/CSS/JavaScript** (multi-page) |
| Real-time | **Socket.IO client** |
| Charts | JavaScript (dashboard charts) |
| Video streaming | WebRTC / MediaStream API |
| Music | **Spotify SDK** integration |

### Hardware / IoT
| Component | Technology |
|---|---|
| Microcontroller | **ESP8266** (NodeMCU/Wemos D1 Mini) |
| Heart Rate + SpO2 | **MAX30102** sensor |
| Temperature | **MLX90614** (infrared, non-contact) |
| Protocol | **HTTP POST** (WiFiClient → FastAPI) |
| Data format | **JSON** (ArduinoJson v6) |

---

## 🔷 17. SECURITY

- **JWT Authentication** (Bearer tokens, 30-minute expiry by default)
- Role-based access: `CareTaker` vs. `Doctor` roles
- `verify_user_and_role` unified auth function
- ESP8266 uses shared `ESP_SECRET_KEY`
- `.env` file for all secrets (never hardcoded)
- CORS configured for `127.0.0.1:5500` (development)

---

## 🔷 18. DATABASE SCHEMA (Key Tables)

| Table | Purpose |
|---|---|
| `users` / `care_takers` | Auth accounts |
| `care_recipients` | Elder profile data |
| `recordings` | Video recording metadata |
| `vital_signs` | Biometric readings from ESP8266 |
| `audio_events` | Cough/sneeze detections |
| `medical_conditions` | Patient conditions & status |
| `lab_values` | Lab results from reports |
| `medical_alerts` | Generated alerts with cooldown |
| `medications` | Medication management |
| `allergies` | Allergy records |
| `conversation_history` | Voice bot messages + moods |
| `disease_dictionary` | Medical knowledge base |
| `environment` | Room sensor data |

---

## 🔷 19. FUTURE ENHANCEMENTS

- Multi-person fall detection (currently tracks primary person only)
- Wearable sensor fusion (accelerometer + camera)
- Predictive fall risk scoring (before falls occur)
- Smart home integration (lights, door sensors)
- Mobile app (Flutter) for caregivers
- Improved outdoor/nighttime camera performance

---

## 🔥 20. KEY INTERVIEW LINES

### On the Fall Detection Model:
> *"We use a hybrid architecture — YOLOv8n-pose extracts 17 COCO keypoints per frame, which we normalize to be hip-centred and torso-scaled, making the features scale and position invariant. These normalized 34-dimensional vectors are fed into a sliding 30-frame buffer, which is processed by a Bidirectional GRU with self-attention. The attention mechanism focuses on the critical transition frames — the actual fall moment — rather than averaging the entire sequence."*

### On Why BiGRU Over Single-Frame or CNN:
> *"A fall is not just a posture — it is a transition over time. A person lying on the floor looks the same as someone sleeping. What distinguishes a fall is the rapid vertical motion, the torso angle change, and the subsequent stillness. A BiGRU captures this temporal pattern from both directions. The bidirectionality is important because context after the event — the person lying still — helps confirm the fall."*

### On False Positive Prevention:
> *"In live mode, we use stricter thresholds — 0.92 probability and 10 consecutive confirming frames — so the system doesn't trigger from someone bending down to tie their shoelace. After a confirmed alert, we reset the sequence buffer and require fresh evidence for the next alert."*

### On the Full System:
> *"Beyond fall detection, the system has seven integrated modules — audio detection for coughs and sneezes using a CRNN model, an AI voice companion called Saathi powered by Gemini that tracks emotional state across conversations, a medical intelligence engine that reads lab reports using OCR and tracks disease progression, a background notification scheduler for medicine reminders and auto-reorder, and real-time vitals from an ESP8266 connected to a heart rate and temperature sensor — all serving role-based dashboards for caregivers and doctors."*

---

## 🔷 21. QUICK FACT SHEET (For Rapid Recall)

| Question | Answer |
|---|---|
| YOLO model used | `yolov8n-pose.pt` (nano, pose estimation) |
| Keypoints per frame | 17 COCO keypoints → 34 features (x,y per keypoint) |
| Normalization | Hip-centered, torso-scaled |
| Sequence window | **30 frames** |
| Sliding stride | **15 frames** (50% overlap) |
| GRU hidden size | **128** per direction (256 total) |
| GRU layers | **2** |
| Dropout | **0.4** |
| Loss function | **Weighted CrossEntropyLoss** |
| Optimizer | **Adam** (lr=1e-3) |
| LR scheduler | **CosineAnnealingLR** |
| Best model criterion | **Highest F1 Score** |
| Datasets | **Le2i** (cNNcamM format) + **UR Fall Detection** (fall-NN-camM, adl-NN-camM) |
| Backend framework | **FastAPI** |
| Database | **PostgreSQL** (+SQLite for dev) |
| Real-time protocol | **Socket.IO** |
| Voice bot LLM | **Google Gemini API** |
| TTS | **Google Cloud Text-to-Speech** |
| Audio model | **TensorFlow CRNN** + Acoustic rule engine |
| Face recognition | **DeepFace** (ArcFace) |
| IoT board | **ESP8266** (MAX30102 + MLX90614) |
| Auth | **JWT** (HS256) |
| Email | **SMTP / Gmail** |
| Music | **Spotify SDK** |
