from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add parent dir to path
sys.path.append(os.getcwd())

from config import Base
from tables.video_analysis import VideoAnalysis

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)

try:
    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='video_analysis';"))
        table_exists = result.fetchone()
        
        if table_exists:
            print("✅ Table 'video_analysis' exists.")
            # Check row count
            result = conn.execute(text("SELECT count(*) FROM video_analysis;"))
            count = result.scalar()
            print(f"✅ Table row count: {count}")
        else:
            print("❌ Table 'video_analysis' DOES NOT EXIST.")
            
except Exception as e:
    print(f"❌ Error checking DB: {e}")
