"""
Medication Dose Confirmation Routes

Provides:
  POST /api/confirm-dose          — Dashboard-driven confirmation (JWT required)
  GET  /api/confirm-dose-email    — Email-link confirmation (token-gated, no JWT)
  GET  /api/pending-doses         — List of PENDING dose logs for the caretaker (JWT required)
"""

import datetime
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_db
from repository.users import JWTRepo

router = APIRouter(tags=["medications"])

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DOSE_TOKEN_EXPIRY_HOURS = 24


# ─────────────────────────────────────────────
# Auth helper (reuses existing JWT pattern)
# ─────────────────────────────────────────────

def _get_current_caretaker(token: str = Depends(
    lambda: None
), db: Session = Depends(get_db)):
    """Re-usable auth dependency — extracts caretaker from Bearer token."""
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    raise NotImplementedError("Use the token-based dependency below directly.")


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
_bearer = HTTPBearer()

def get_current_caretaker(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
):
    from tables.users import CareTaker
    payload = JWTRepo.decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = payload.get("sub")
    caretaker = db.query(CareTaker).filter(CareTaker.username == username).first()
    if not caretaker:
        raise HTTPException(status_code=401, detail="Caretaker not found")
    return caretaker


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class ConfirmDoseRequest(BaseModel):
    dose_log_id: int
    action: str  # "TAKEN" | "MISSED"


# ─────────────────────────────────────────────
# Shared confirmation logic
# ─────────────────────────────────────────────

def _apply_confirmation(dose_log, action: str, source_enum, db: Session) -> Optional[int]:
    """
    Core idempotent confirmation logic shared by all three channels
    (dashboard, email, voice).

    Returns the new stock value if action=TAKEN, else None.
    Raises HTTPException(409) if the log is already confirmed.
    """
    from tables.medication_dose_logs import DoseStatusEnum
    from tables.medications import Medication

    if dose_log.status != DoseStatusEnum.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Dose already recorded as {dose_log.status.value}. No changes made."
        )

    action_upper = action.upper()
    if action_upper not in ("TAKEN", "MISSED"):
        raise HTTPException(status_code=400, detail="action must be 'TAKEN' or 'MISSED'")

    new_status = DoseStatusEnum.TAKEN if action_upper == "TAKEN" else DoseStatusEnum.MISSED
    dose_log.status             = new_status
    dose_log.confirmation_source = source_enum
    dose_log.confirmed_at        = datetime.datetime.utcnow()

    new_stock = None
    if action_upper == "TAKEN":
        med = db.query(Medication).filter(
            Medication.medication_id == dose_log.medication_id
        ).with_for_update().first()   # row-level lock prevents double-decrement
        if med:
            old_stock = med.current_stock or 0
            daily     = med.doses_per_day or 1
            new_stock = max(0, old_stock - daily)
            med.current_stock = new_stock

    db.commit()
    return new_stock


def _push_socketio(dose_log_id: int, action: str, new_stock):
    """Push a Socket.IO dose_confirmed event to all connected dashboard clients."""
    try:
        import asyncio
        from socket_manager import sio_server
        loop = asyncio.get_event_loop()
        payload = {"dose_log_id": dose_log_id, "action": action, "new_stock": new_stock}
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                sio_server.emit("dose_confirmed", payload), loop
            )
        else:
            loop.run_until_complete(sio_server.emit("dose_confirmed", payload))
    except Exception as e:
        print(f"[medications] Socket.IO push failed: {e}")


# ─────────────────────────────────────────────
# POST /api/confirm-dose  (Dashboard)
# ─────────────────────────────────────────────

@router.post("/confirm-dose")
def confirm_dose_dashboard(
    body: ConfirmDoseRequest,
    db: Session = Depends(get_db),
    caretaker=Depends(get_current_caretaker),
):
    """
    Confirm (TAKEN/MISSED) a pending dose from the caretaker dashboard.

    Idempotent: if the dose is already confirmed, returns 409.
    On TAKEN: decrements medication.current_stock using a row-level lock.
    Emits Socket.IO 'dose_confirmed' to sync all connected clients.
    """
    from tables.medication_dose_logs import MedicationDoseLog, ConfirmationSourceEnum
    from tables.users import CareRecipient

    dose_log = db.query(MedicationDoseLog).filter(
        MedicationDoseLog.id == body.dose_log_id
    ).first()
    if not dose_log:
        raise HTTPException(status_code=404, detail="Dose log not found")

    # ── Ownership check: caretaker may only confirm their own recipients' doses ──
    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == dose_log.care_recipient_id
    ).first()
    if not recipient or recipient.caretaker_id != caretaker.id:
        raise HTTPException(status_code=403, detail="Not authorised to confirm this dose")

    new_stock = _apply_confirmation(
        dose_log, body.action, ConfirmationSourceEnum.DASHBOARD, db
    )
    _push_socketio(dose_log.id, body.action.upper(), new_stock)

    return {
        "success":   True,
        "message":   f"Dose marked as {body.action.upper()}",
        "new_stock": new_stock,
    }


# ─────────────────────────────────────────────
# GET /api/confirm-dose-email  (Email links)
# ─────────────────────────────────────────────

def _html_page(title: str, icon: str, heading: str, body_html: str, color: str) -> str:
    """Return a styled standalone HTML confirmation page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  body{{font-family:'Outfit',sans-serif;min-height:100vh;display:flex;align-items:center;
        justify-content:center;background:#f8fafc;margin:0;padding:20px;}}
  .card{{background:white;border-radius:24px;padding:40px 36px;max-width:440px;width:100%;
         text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.08);border:1px solid #e2e8f0;}}
  .icon{{font-size:64px;margin-bottom:16px;display:block;}}
  h1{{color:{color};font-size:1.5rem;font-weight:800;margin:0 0 10px;}}
  p{{color:#475569;font-size:1rem;line-height:1.6;margin:0 0 6px;}}
  .sub{{color:#94a3b8;font-size:0.85rem;margin-top:20px;}}
</style>
</head>
<body>
  <div class="card">
    <span class="icon">{icon}</span>
    <h1>{heading}</h1>
    {body_html}
    <p class="sub">You can close this tab.</p>
  </div>
</body>
</html>"""


@router.get("/confirm-dose-email", response_class=HTMLResponse)
def confirm_dose_email(
    token: str = Query(..., description="UUID token from confirmation email"),
    action: str = Query(..., description="TAKEN or MISSED"),
    db: Session = Depends(get_db),
):
    """
    Token-gated email confirmation endpoint.
    No JWT required — the UUID token authenticates the request.
    Returns a human-readable HTML page (works when opened in any browser).

    Security:
      - Token is a UUID4 tied to exactly one MedicationDoseLog row.
      - Tokens expire 24 hours after the scheduled_time.
      - Once used (status != PENDING), the token is permanently inert.
    """
    from tables.medication_dose_logs import MedicationDoseLog, DoseStatusEnum, ConfirmationSourceEnum
    from tables.medications import Medication

    dose_log = db.query(MedicationDoseLog).filter(
        MedicationDoseLog.unique_token == token
    ).first()

    # ── Token not found ──
    if not dose_log:
        return HTMLResponse(
            content=_html_page(
                "Invalid Link", "❌", "Invalid Confirmation Link",
                "<p>This confirmation link is invalid or has expired.</p>",
                "#ef4444",
            ),
            status_code=404,
        )

    # ── Token expired (> 24 h after scheduled time) ──
    expiry = dose_log.scheduled_time + datetime.timedelta(hours=DOSE_TOKEN_EXPIRY_HOURS)
    if datetime.datetime.utcnow() > expiry:
        return HTMLResponse(
            content=_html_page(
                "Link Expired", "⏰", "Confirmation Link Expired",
                "<p>This confirmation link expired 24 hours after the dose was scheduled.</p>"
                "<p>Please use the CareTaker dashboard to update this record.</p>",
                "#f59e0b",
            ),
        )

    # ── Already confirmed (idempotent — show friendly page, don't error) ──
    if dose_log.status != DoseStatusEnum.PENDING:
        icon    = "✅" if dose_log.status == DoseStatusEnum.TAKEN else "⚠️"
        color   = "#10b981" if dose_log.status == DoseStatusEnum.TAKEN else "#f59e0b"
        heading = "Already Recorded"
        src     = dose_log.confirmation_source.value if dose_log.confirmation_source else "the system"
        return HTMLResponse(
            content=_html_page(
                "Already Confirmed", icon, heading,
                f"<p>This dose was already confirmed as <strong>{dose_log.status.value}</strong> "
                f"via {src}.</p><p>No changes have been made.</p>",
                color,
            ),
        )

    # ── Apply confirmation ──
    action_upper = action.upper()
    try:
        new_stock = _apply_confirmation(
            dose_log, action_upper, ConfirmationSourceEnum.EMAIL, db
        )
    except HTTPException as exc:
        # 409 from idempotency guard — race condition: dashboard confirmed first
        return HTMLResponse(
            content=_html_page(
                "Already Recorded", "✅", "Already Recorded",
                f"<p>{exc.detail}</p>", "#10b981"
            ),
        )

    _push_socketio(dose_log.id, action_upper, new_stock)

    # ── Success page ──
    med = db.query(Medication).filter(
        Medication.medication_id == dose_log.medication_id
    ).first()
    med_name = med.medicine_name if med else "Medicine"

    if action_upper == "TAKEN":
        stock_line = (
            f"<p>Remaining stock: <strong>{new_stock} doses</strong></p>"
            if new_stock is not None else ""
        )
        return HTMLResponse(
            content=_html_page(
                "Dose Confirmed", "✅", "Dose Confirmed!",
                f"<p><strong>{med_name}</strong> has been marked as <strong>TAKEN</strong>.</p>"
                + stock_line,
                "#10b981",
            ),
        )
    else:
        return HTMLResponse(
            content=_html_page(
                "Dose Missed", "⚠️", "Dose Marked as Not Taken",
                f"<p><strong>{med_name}</strong> has been recorded as <strong>NOT TAKEN</strong>.</p>"
                "<p>The caretaker has been notified.</p>",
                "#f59e0b",
            ),
        )


# ─────────────────────────────────────────────
# GET /api/pending-doses  (Dashboard polling)
# ─────────────────────────────────────────────

@router.get("/pending-doses")
def get_pending_doses(
    recipient_id: Optional[int] = Query(None, description="Filter by care recipient"),
    db: Session = Depends(get_db),
    caretaker=Depends(get_current_caretaker),
):
    """
    Return all PENDING dose logs for the authenticated caretaker's recipients.
    Optionally filter by a single recipient_id.

    Called by the dashboard every 30 seconds (fallback to Socket.IO push).
    """
    from tables.medication_dose_logs import MedicationDoseLog, DoseStatusEnum
    from tables.medications import Medication
    from tables.users import CareRecipient

    # Resolve recipient IDs owned by this caretaker
    recipients_q = db.query(CareRecipient).filter(
        CareRecipient.caretaker_id == caretaker.id
    )
    if recipient_id:
        recipients_q = recipients_q.filter(CareRecipient.id == recipient_id)
    recipient_ids = [r.id for r in recipients_q.all()]

    if not recipient_ids:
        return []

    pending = (
        db.query(MedicationDoseLog)
        .filter(
            MedicationDoseLog.care_recipient_id.in_(recipient_ids),
            MedicationDoseLog.status == DoseStatusEnum.PENDING,
        )
        .order_by(MedicationDoseLog.scheduled_time)
        .all()
    )

    results = []
    for log in pending:
        med = db.query(Medication).filter(
            Medication.medication_id == log.medication_id
        ).first()
        recip = db.query(CareRecipient).filter(
            CareRecipient.id == log.care_recipient_id
        ).first()
        results.append({
            "dose_log_id":    log.id,
            "medicine_name":  med.medicine_name if med else "Unknown",
            "dosage":         med.dosage if med else "",
            "scheduled_time": log.scheduled_time.isoformat(),
            "recipient_name": recip.full_name if recip else "",
            "recipient_id":   log.care_recipient_id,
        })

    return results


# ─────────────────────────────────────────────
# GET /api/dose-history  (Optional — for audit log view)
# ─────────────────────────────────────────────

@router.get("/dose-history/{recipient_id}")
def get_dose_history(
    recipient_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    caretaker=Depends(get_current_caretaker),
):
    """
    Return the last N dose logs (any status) for a given recipient.
    Used for displaying a compliance history table on the dashboard.
    """
    from tables.medication_dose_logs import MedicationDoseLog
    from tables.medications import Medication
    from tables.users import CareRecipient

    # Ownership guard
    recip = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
    if not recip or recip.caretaker_id != caretaker.id:
        raise HTTPException(status_code=403, detail="Not authorised")

    logs = (
        db.query(MedicationDoseLog)
        .filter(MedicationDoseLog.care_recipient_id == recipient_id)
        .order_by(MedicationDoseLog.scheduled_time.desc())
        .limit(limit)
        .all()
    )

    results = []
    for log in logs:
        med = db.query(Medication).filter(
            Medication.medication_id == log.medication_id
        ).first()
        results.append({
            "dose_log_id":         log.id,
            "medicine_name":       med.medicine_name if med else "Unknown",
            "dosage":              med.dosage if med else "",
            "scheduled_time":      log.scheduled_time.isoformat(),
            "status":              log.status.value,
            "confirmation_source": log.confirmation_source.value if log.confirmation_source else None,
            "confirmed_at":        log.confirmed_at.isoformat() if log.confirmed_at else None,
        })

    return results
