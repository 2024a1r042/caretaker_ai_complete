# Caretaker.ai

**Modern Elderly Care** — A full-stack platform for caregivers to monitor and support care recipients through video monitoring, audio analytics, vital signs, medical reports, voice assistance, and proactive alerts.

---

## Features

- **Authentication & profiles** — Sign up, login, face registration, and care recipient management
- **Video monitoring** — Live monitoring, fall detection, inactivity alerts, and video upload analysis
- **Audio analytics** — Cough/sneeze detection, event logging, and analytics dashboards (trends, hourly distribution, event types)
- **Vital signs** — Record and view latest vitals per care recipient
- **Medical history** — Conditions, medications, allergies, lab values, medical alerts, and report ingestion (PDF/DOCX)
- **Voice bot** — AI-powered chat with context (vitals, conditions, mood), reminders, and proactive triggers
- **Insights & alerts** — Recipient insights, disease progression/detection, and emergency alerts
- **Environment** — Temperature/humidity (and optional weather) for recipient locations
- **Weather widget** — Current weather (optional, via API key)

> **New:** personalized Saathi (profile + long-term memory + proactive check-ins, works even without
> Gemini) and an explainable, multi-signal fall engine linked to a spoken voice check-in — verified on real
> video and end-to-end in the browser. See **[SAATHI_UPGRADE.md](SAATHI_UPGRADE.md)**.
>
> **Quick start (Windows):** `.\setup_windows.ps1` once, add `GEMINI_API_KEY` to `backend\.env`, then
> `.\run_windows.ps1`. Health check: http://127.0.0.1:8000/api/health/ai

---

## Tech Stack

| Layer      | Stack |
|-----------|--------|
| **Backend** | Python 3, FastAPI, SQLAlchemy, PostgreSQL, Uvicorn, python-socketio |
| **Frontend** | HTML/CSS/JS, Chart.js, static frontend (e.g. `serve`) |
| **AI/ML** | TensorFlow, DeepFace, Gemini API (summarization, voice bot, insights), acoustic/cough–sneeze models |
| **Other**   | JWT auth, FastAPI-Mail, PyPDF2/pdfplumber, WebSockets |

---

## Project Structure

```
caretaker.ai/
├── backend/                 # FastAPI + Socket.IO API
│   ├── main.py              # App entry, CORS, routers, Socket.IO
│   ├── config.py            # DB, JWT, audio config (from .env)
│   ├── requirements.txt     # Python dependencies
│   ├── routes/              # API routes (users, recipients, voice_bot, video_monitoring, etc.)
│   ├── services/            # Business logic (voice_bot_engine, insights_engine, alert_engine, etc.)
│   ├── tables/              # SQLAlchemy models
│   ├── utils/               # Summarizer, email, audio model helpers
│   ├── coughandsneezedetection/  # Cough/sneeze detection (Flask + SocketIO)
│   └── VideoMonitoring/     # Fall detection, body movement, live monitor
├── frontend/                # Web UI
│   ├── index.html           # Landing
│   ├── login.html, register.html, dashboard.html, profile.html
│   ├── video_monitoring.html, audio_monitoring.html, voice_bot.html
│   ├── medical_reports.html, insights.html, settings.html
│   ├── js/, static/         # Scripts and assets
│   └── package.json         # e.g. "serve" for local dev
├── model/                   # ML model assets (e.g. model.json, metadata.json)
└── sdk/                     # SDK/model assets served by backend
```

---

## Prerequisites

- **Python 3.10+** (for backend)
- **PostgreSQL** (database)
- **Node.js** (optional, for frontend `npm run dev` with `serve`)
- **API keys** (optional): Gemini, weather, mail (see Environment variables)

---

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

Create a **`.env`** file in the project root (or `backend/`, depending on where `load_dotenv` looks) with at least:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/caretaker
SECRET_KEY=your-secret-key-for-jwt
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Optional (for full functionality):

```env
GEMINI_API_KEY=...
GEMINI_API_ENDPOINT=...
WEATHER_API_KEY=...
DEFAULT_CITY=...
MAIL_SERVER=...
MAIL_PORT=587
MAIL_USERNAME=...
MAIL_PASSWORD=...
MAIL_FROM=...
ADMIN_EMAIL=...
```

Run the API (from `backend/`):

```bash
python main.py
```

Server runs at **http://0.0.0.0:8000**. The app combines FastAPI with Socket.IO (single process, port 8000).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

This typically serves the frontend (e.g. with `serve`) so you can open the app in the browser. Point the frontend’s API base URL to `http://localhost:8000` (or your backend URL).

### 3. Database

Ensure PostgreSQL is running and the database in `DATABASE_URL` exists. Tables are created on startup via SQLAlchemy `create_all` in `main.py`.

---

## Environment Variables (summary)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | No | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `30` |
| `GEMINI_API_KEY` | For AI | Summarization, voice bot, insights |
| `GEMINI_API_ENDPOINT` | For AI | Gemini API endpoint |
| `WEATHER_API_KEY` | Optional | Weather widget |
| `DEFAULT_CITY` | Optional | Default city for weather |
| `MAIL_*` | Optional | Email (notifications, alerts) |
| `ADMIN_EMAIL` | Optional | Fallback for emergency alerts |

---

## API Overview

- **`/`** — Health/welcome
- **`/api`** — Auth (signup, login, profile), users, recordings, recipients, emergency, elderly (face), video-monitoring, audio-events, voice-bot, vitals, environment, weather
- **Medical history** routes are mounted without `/api` prefix (see `main.py`).
- **Socket.IO** is used for real-time features (e.g. audio/video pipelines).

See `backend/routes/` and `backend/main.py` for exact prefixes and tags.

---

## License

ISC (see `frontend/package.json`). Adjust as needed for your project.
