# Audio Events Database Integration - Complete Setup

## Overview
Successfully integrated audio event detection with database storage, linking cough and sneeze detections to specific care recipients for long-term analysis.

## Changes Made

### 1. Sample Data Generation
**File**: `backend/scripts/add_sample_audio_data.py`

Created a script to populate the database with realistic sample audio events:
- **30 days** of historical data
- **2-8 events per day** with realistic time distribution
- **Event types**: 60% coughs, 25% sneezes, 10% talking, 5% noise
- **Confidence scores**: Vary by event type (65-98%)
- **Peak times**: Morning (6-10am) and evening (6-10pm)
- Automatically links to the first caretaker and recipient in the database

**Usage**:
```bash
cd backend
python scripts/add_sample_audio_data.py
```

### 2. Frontend Integration (profile.html)

#### Dynamic Audio Monitor Link
- Changed from static `http://localhost:5001` to dynamic link with recipient ID
- Link updates when a recipient is selected
- Format: `http://localhost:5001?recipient_id=X&name=RecipientName`

**Code Added**:
```javascript
// Update audio monitor link with recipient ID
const audioMonitorLink = document.getElementById('audioMonitorLink');
if (audioMonitorLink) {
    if (id) {
        audioMonitorLink.href = `http://localhost:5001?recipient_id=${id}&name=${encodeURIComponent(name || '')}`;
    } else {
        audioMonitorLink.href = 'http://localhost:5001';
    }
}
```

### 3. Audio Monitor Client (main.js)

#### URL Parameter Extraction
- Extracts `recipient_id` and `name` from URL query parameters
- Sends recipient ID to server during authentication
- Updates UI to show recipient name in header

**Code Added**:
```javascript
// Get recipient ID from URL parameters
const urlParams = new URLSearchParams(window.location.search);
const recipientId = urlParams.get('recipient_id');
const recipientName = urlParams.get('name');

// Send authentication token for database logging
socket.on('connect', () => {
    const token = localStorage.getItem('token');
    if (token) {
        socket.emit('authenticate', { 
            token: token,
            recipient_id: recipientId ? parseInt(recipientId) : null
        });
    }
    
    // Update UI if recipient name is provided
    if (recipientName) {
        const header = document.querySelector('.header-left .logo');
        if (header) {
            header.innerHTML = `⚡ SonicGuard <span style="font-size: 0.85em; opacity: 0.7;">— ${recipientName}</span>`;
        }
    }
});
```

### 4. Audio Monitor Server (app.py)

#### Global Variables
Added `RECIPIENT_ID` to store the selected recipient:
```python
AUTH_TOKEN = None  # Will be set when client connects with auth
RECIPIENT_ID = None  # Will be set when client connects with recipient info
```

#### Updated Authentication Handler
Modified to receive and store recipient ID:
```python
@socketio.on("authenticate")
def handle_authenticate(data):
    """Receive authentication token and recipient ID from client for database logging."""
    global AUTH_TOKEN, RECIPIENT_ID
    AUTH_TOKEN = data.get("token")
    RECIPIENT_ID = data.get("recipient_id")
    if AUTH_TOKEN:
        print(f"  [AUTH] Token received for database logging")
        if RECIPIENT_ID:
            print(f"  [AUTH] Recipient ID: {RECIPIENT_ID}")
    emit("auth_ack", {"status": "ok"})
```

#### Updated Event Logging
Pass recipient ID when logging events:
```python
# Log to database for long-term analysis
log_audio_event_to_db(predicted, round(confidence, 2), RECIPIENT_ID)
```

## Data Flow

### Complete Flow from Detection to Database

1. **User selects a recipient** in profile.html
   - `selectRecipient(id, name)` is called
   - Audio monitor link is updated with `?recipient_id=X&name=Y`

2. **User clicks "Open Live Monitor"**
   - Opens audio monitor in new tab
   - URL includes recipient parameters

3. **Audio monitor loads** (main.js)
   - Extracts `recipient_id` from URL
   - Connects to Socket.IO server
   - Sends authentication with token + recipient_id

4. **Server receives authentication** (app.py)
   - Stores `AUTH_TOKEN` and `RECIPIENT_ID` globally
   - Logs recipient info to console

5. **Audio detection occurs**
   - Cough or sneeze detected with high confidence
   - `log_audio_event_to_db()` called with recipient_id

6. **Event saved to database**
   - API POST to `/api/audio-events`
   - Event linked to:
     - Caretaker (from auth token)
     - Care recipient (from recipient_id)
   - Includes: type, confidence, timestamp, duration

7. **Analytics dashboard displays data**
   - Charts filtered by selected recipient
   - Shows trends, hourly distribution, recent events

## Database Schema

### audio_events Table
```sql
CREATE TABLE audio_events (
    id SERIAL PRIMARY KEY,
    caretaker_id INTEGER NOT NULL,
    care_recipient_id INTEGER,  -- Now properly populated!
    event_type VARCHAR NOT NULL,  -- 'Cough', 'Sneeze', 'Talking', 'Noise'
    confidence FLOAT NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW(),
    duration_ms INTEGER,
    notes VARCHAR,
    FOREIGN KEY (caretaker_id) REFERENCES caretakers(id),
    FOREIGN KEY (care_recipient_id) REFERENCES care_recipients(id)
);
```

## Testing the Integration

### Step 1: Add Sample Data
```bash
cd backend
python scripts/add_sample_audio_data.py
```

Expected output:
```
✅ Successfully added 150+ sample audio events!
   📊 Breakdown:
      🤧 Coughs: 90
      🤧 Sneezes: 38
      🗣️  Talking: 15
      🔊 Noise: 7
   👤 Linked to recipient: John Doe
   📅 Date range: 2026-01-15 to 2026-02-14
```

### Step 2: View Analytics
1. Open `http://localhost:5500/profile.html`
2. Login with your credentials
3. Select a recipient from the list
4. Scroll to "Audio Monitoring & Analytics" section
5. See populated charts and statistics

### Step 3: Test Live Detection
1. Click "Open Live Monitor" button
2. Notice recipient name in header: "⚡ SonicGuard — John Doe"
3. Click "Start Monitoring"
4. Cough or sneeze near microphone
5. Check server console for:
   ```
   [AUTH] Token received for database logging
   [AUTH] Recipient ID: 1
   [ALERT] Cough detected (confidence: 87.5%)
   ```
6. Return to profile.html and refresh analytics
7. See new event in "Recent Detections" list

### Step 4: Verify Database
```sql
SELECT 
    ae.id,
    ae.event_type,
    ae.confidence,
    ae.detected_at,
    cr.full_name as recipient_name,
    ct.username as caretaker_name
FROM audio_events ae
JOIN care_recipients cr ON ae.care_recipient_id = cr.id
JOIN caretakers ct ON ae.caretaker_id = ct.id
ORDER BY ae.detected_at DESC
LIMIT 10;
```

## Benefits

### For Caregivers
1. **Recipient-Specific Tracking**: Each recipient's respiratory events are tracked separately
2. **Historical Analysis**: View trends over days, weeks, or months
3. **Pattern Recognition**: Identify peak times for coughs/sneezes
4. **Data-Driven Care**: Make informed decisions based on concrete data

### For the System
1. **Proper Data Attribution**: Events correctly linked to recipients
2. **Scalable**: Supports multiple recipients per caretaker
3. **Flexible Filtering**: Analytics can filter by recipient
4. **Complete Audit Trail**: Full history of detections with timestamps

## Troubleshooting

### Issue: No events showing in analytics
**Solution**: 
1. Run the sample data script
2. Check if recipient is selected
3. Verify time range selector (default: 7 days)

### Issue: Live detections not saving
**Solution**:
1. Check browser console for authentication errors
2. Verify token in localStorage
3. Check server console for "[AUTH]" messages
4. Ensure recipient_id is in URL

### Issue: Events saved without recipient_id
**Solution**:
1. Ensure you're opening monitor from profile.html link
2. Check URL has `?recipient_id=X` parameter
3. Verify server receives recipient_id in auth message

## Future Enhancements

1. **Multi-Recipient Monitoring**: Monitor multiple recipients simultaneously
2. **Alert Thresholds**: Set custom thresholds per recipient
3. **Export Reports**: Generate PDF reports for healthcare providers
4. **Medication Correlation**: Link events to medication schedules
5. **Environmental Factors**: Correlate with weather, air quality data

## Files Modified

1. ✅ `backend/scripts/add_sample_audio_data.py` - Created
2. ✅ `frontend/profile.html` - Updated audio monitor link logic
3. ✅ `backend/coughandsneezedetection/static/js/main.js` - URL parameter handling
4. ✅ `backend/coughandsneezedetection/app.py` - Recipient ID storage and logging

## Conclusion

The audio events database integration is now complete with proper recipient tracking. All detected coughs and sneezes are:
- ✅ Saved to the database
- ✅ Linked to the correct care recipient
- ✅ Linked to the authenticated caretaker
- ✅ Displayed in analytics dashboard
- ✅ Filterable by recipient and time range

The system is ready for prototype demonstration! 🎉
