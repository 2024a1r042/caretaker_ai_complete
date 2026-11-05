from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# Get database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set. Copy backend/.env.example to backend/.env and fill it in "
                     "(e.g. postgresql://postgres:<password>@localhost:5432/caretaker).")

# pool_pre_ping: drop dead connections (PostgreSQL restarts / laptop sleep) instead of
# failing the next request with "server closed the connection unexpectedly".
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        print("DB session failed:", e)
        raise  # re-raise so FastAPI knows
    finally:
        db.close()

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in backend/.env (any long random string).")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
# 30 min was far too short for a care dashboard / an elder's Saathi tablet left open all day:
# pages silently stopped loading data once the token expired. Override in .env if needed.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

# Audio Pipeline Config
AUDIO_CHUNK_SIZE = 4096
AUDIO_CHANNELS = 1
AUDIO_RATE = 44100
AUDIO_FORMAT = "paInt16"
AUDIO_VAD_THRESHOLD = 800
AUDIO_MAX_SILENCE_CHUNKS = 30
AUDIO_TARGET_SR = 16000