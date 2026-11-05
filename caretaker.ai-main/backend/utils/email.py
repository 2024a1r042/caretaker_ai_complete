from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from typing import List
from pydantic import EmailStr
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Email is OPTIONAL. Before, missing MAIL_* settings crashed the whole backend at
# import time (pydantic rejects None). Now: configured → real emails; not
# configured → alerts are logged to the console and everything else keeps working.
MAIL_ENABLED = all(os.getenv(k) for k in ("MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM", "MAIL_SERVER"))

conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME") or "not-configured",
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") or "not-configured",
    MAIL_FROM = os.getenv("MAIL_FROM") or "noreply@example.com",
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER = os.getenv("MAIL_SERVER") or "localhost",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True
)

if not MAIL_ENABLED:
    print("[email] MAIL_* not set in .env — emails will be printed to the console instead of sent.")


async def _send(message: "MessageSchema"):
    """Send if configured; otherwise log what would have been sent."""
    if not MAIL_ENABLED:
        print(f"[email:not-sent] to={message.recipients} subject={message.subject!r}")
        return
    await _send(message)

async def send_registration_email(email: EmailStr, username: str):
    message = MessageSchema(
        subject="Welcome to CareTaker!",
        recipients=[email],
        body=f"""
        <html>
            <body>
                <h1>Welcome to CareTaker, {username}!</h1>
                <p>Thank you for registering with CareTaker. Your account has been successfully created.</p>
                <p>You can now log in to your account and start managing care for your loved ones.</p>
                <p>Best regards,<br>The CareTaker Team</p>
            </body>
        </html>
        """,
        subtype="html"
    )

    await _send(message)


async def send_fall_alert_email(recipient_email: EmailStr, fall_data: dict):
    """
    Send an email notification when a fall is detected.
    
    Args:
        recipient_email: Email address of the caregiver
        fall_data: Dictionary containing fall detection details with keys:
            - timestamp: When the fall was detected
            - fall_count: Number of falls detected
            - fall_details: List of dictionaries with fall details
            - location: Where the fall was detected
            - video_url: Optional URL to view the video
    """
    # Format fall details into a table
    fall_details_html = ""
    if fall_data.get('fall_details'):
        fall_details_html = """
        <h3>Fall Details:</h3>
        <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Time</th>
                    <th>Confidence</th>
                    <th>Angle</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for fall in fall_data['fall_details']:
            fall_details_html += f"""
                <tr>
                    <td>{fall.get('timestamp', 'N/A')}</td>
                    <td>{fall.get('confidence', 'N/A')}%</td>
                    <td>{fall.get('angle', 'N/A')}°</td>
                </tr>
            """
        
        fall_details_html += """
            </tbody>
        </table>
        """
    
    video_link = f""
    if fall_data.get('video_url'):
        video_link = f"""
        <p><strong>Video:</strong> <a href="{fall_data['video_url']}">View Recording</a></p>
        """

    message = MessageSchema(
        subject="🚨 FALL DETECTED: Immediate Attention Required",
        recipients=[recipient_email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0;">
                    <h2 style="color: #d32f2f;">🚨 Fall Detected</h2>
                    <p><strong>Time:</strong> {fall_data.get('timestamp', 'N/A')}</p>
                    <p><strong>Location:</strong> {fall_data.get('location', 'Unknown')}</p>
                    <p><strong>Total Falls Detected:</strong> {fall_data.get('fall_count', 0)}</p>
                    {video_link}
                    
                    {fall_details_html}
                    
                    <div style="margin-top: 20px; padding: 15px; background-color: #fff3e0; border-left: 4px solid #ff9800;">
                        <p><strong>Action Required:</strong> Please check on the person immediately.</p>
                    </div>
                    
                    <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                        This is an automated message from CareTaker. Please do not reply to this email.
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )

    await _send(message)

async def send_safety_email(recipient_email: EmailStr, subject: str, html_body: str, image_bytes: bytes = None):
    """Generic safety notification (fall check-in outcome / escalation)."""
    attachments = []
    if image_bytes:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(image_bytes)
        tmp.close()
        attachments = [tmp.name]
    message = MessageSchema(subject=subject, recipients=[recipient_email], body=html_body,
                            subtype="html", attachments=attachments)
    await _send(message)
