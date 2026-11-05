from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import json
from datetime import datetime

# Import database and models
from config import get_db
import tables.users as user_tables
from utils.email import send_fall_alert_email

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Helper function to verify JWT token
def verify_token(token: str, db: Session):
    # This is a simplified example - you should replace this with your actual token verification logic
    # and user retrieval from the database
    from jose import JWTError, jwt
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    
    # Get user from database
    user = db.query(user_tables.User).filter(user_tables.User.email == username).first()
    if not user:
        return None
    return user

@router.post("/emergency/alert", status_code=200)
async def send_emergency_alert(
    alert_data: Dict[str, Any],
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        # Verify the token and get the user
        user = verify_token(token, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get the caregiver's email (in a real app, you'd get this from the user's relationship)
        # For now, we'll use the admin email or the user's email
        caregiver_email = os.getenv("ADMIN_EMAIL", user.email)
        
        # Prepare fall data for email
        fall_data = {
            "timestamp": alert_data.get("timestamp", datetime.utcnow().isoformat()),
            "fall_count": alert_data.get("fallCount", 1),
            "fall_details": alert_data.get("fallDetails", []),
            "location": alert_data.get("location", "Unknown"),
            "video_url": alert_data.get("videoUrl", "")
        }
        
        # Send the email
        await send_fall_alert_email(caregiver_email, fall_data)
        
        # Log the alert (you can also save this to a database)
        print(f"Fall alert sent to {caregiver_email} at {datetime.utcnow().isoformat()}")
        
        return {
            "status": "success",
            "message": "Emergency alert sent successfully",
            "recipient": caregiver_email
        }
        
    except Exception as e:
        print(f"Error sending emergency alert: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send emergency alert: {str(e)}"
        )
