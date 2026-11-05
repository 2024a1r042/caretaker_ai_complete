# Audio Events Database Integration

## Overview
Successfully integrated cough and sneeze detection data into the CareTaker database for long-term analysis and tracking.

## Database Schema

### New Table: `audio_events`
```sql
CREATE TABLE audio_events (
    id SERIAL PRIMARY KEY,
    caretaker_id INTEGER NOT NULL REFERENCES caretakers(id) ON DELETE CASCADE,
    care_recipient_id INTEGER REFERENCES care_recipients(id) ON DELETE CASCADE,
    event_type VARCHAR NOT NULL,  -- 'Cough', 'Sneeze', 'Talking', 'Noise'
    confidence FLOAT NOT NULL,     -- 0.0 to 100.0
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    duration_ms INTEGER,           -- Duration of audio chunk
    notes VARCHAR,                 -- Optional metadata
    INDEX idx_caretaker (caretaker_id),
    INDEX idx_recipient (care_recipient_id),
    INDEX idx_event_type (event_type),
    INDEX idx_detected_at (detected_at)
);
```

## API Endpoints

### 1. Create Audio Event
**POST** `/api/audio-events`

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
    "care_recipient_id": 1,  // Optional
    "event_type": "Cough",   // "Cough", "Sneeze", "Talking", "Noise"
    "confidence": 85.5,      // 0.0 to 100.0
    "duration_ms": 500,      // Optional
    "notes": "Morning detection"  // Optional
}
```

**Response:**
```json
{
    "id": 123,
    "caretaker_id": 1,
    "care_recipient_id": 1,
    "event_type": "Cough",
    "confidence": 85.5,
    "detected_at": "2026-02-14T00:55:00Z",
    "duration_ms": 500,
    "notes": "Morning detection"
}
```

### 2. Get Audio Events
**GET** `/api/audio-events`

**Query Parameters:**
- `care_recipient_id` (optional): Filter by recipient
- `event_type` (optional): Filter by type (Cough, Sneeze, etc.)
- `days` (default: 7): Number of days to look back
- `limit` (default: 100): Maximum events to return

**Example:**
```
GET /api/audio-events?care_recipient_id=1&event_type=Cough&days=30&limit=50
```

**Response:**
```json
[
    {
        "id": 123,
        "caretaker_id": 1,
        "care_recipient_id": 1,
        "event_type": "Cough",
        "confidence": 85.5,
        "detected_at": "2026-02-14T00:55:00Z",
        "duration_ms": 500,
        "notes": null
    },
    ...
]
```

### 3. Get Statistics
**GET** `/api/audio-events/stats`

**Query Parameters:**
- `care_recipient_id` (optional): Filter by recipient
- `days` (default: 7): Analysis period

**Example:**
```
GET /api/audio-events/stats?care_recipient_id=1&days=7
```

**Response:**
```json
{
    "total_events": 45,
    "cough_count": 23,
    "sneeze_count": 12,
    "talking_count": 8,
    "noise_count": 2,
    "date_range": "Last 7 days"
}
```

### 4. Delete Audio Event
**DELETE** `/api/audio-events/{event_id}`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:**
```json
{
    "message": "Audio event deleted successfully"
}
```

## How It Works

### 1. Real-Time Detection
When the audio monitoring app (`app.py`) detects a cough or sneeze:
1. The event is emitted to the client via Socket.IO
2. Simultaneously, it's logged to the database via the API
3. The logging is non-blocking to avoid disrupting real-time detection

### 2. Authentication Flow
1. Client connects to the audio monitoring server
2. Client sends authentication token via `authenticate` socket event
3. Server stores the token for subsequent database API calls
4. All detected events are automatically logged with the authenticated user

### 3. Database Logging
```python
# In app.py when cough/sneeze detected:
log_audio_event_to_db(predicted, round(confidence, 2))

# Function makes API call to backend:
POST /api/audio-events
{
    "event_type": "Cough",
    "confidence": 85.5,
    "duration_ms": 500
}
```

## Files Modified/Created

### New Files:
1. `backend/tables/audio_events.py` - Database model
2. `backend/routes/audio_events.py` - API routes
3. `backend/AUDIO_EVENTS_INTEGRATION.md` - This documentation

### Modified Files:
1. `backend/main.py` - Added audio_events table and router
2. `backend/coughandsneezedetection/app.py` - Added database logging
3. `backend/coughandsneezedetection/static/js/main.js` - Added auth token sending

## Usage Examples

### Frontend Integration (JavaScript)
```javascript
// Fetch recent cough events for a recipient
const response = await fetch(
    'http://localhost:8000/api/audio-events?care_recipient_id=1&event_type=Cough&days=7',
    {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    }
);
const events = await response.json();

// Get statistics
const statsResponse = await fetch(
    'http://localhost:8000/api/audio-events/stats?care_recipient_id=1&days=30',
    {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    }
);
const stats = await statsResponse.json();
console.log(`Total coughs in last 30 days: ${stats.cough_count}`);
```

### Python Integration
```python
import requests

# Get events
response = requests.get(
    'http://localhost:8000/api/audio-events',
    headers={'Authorization': f'Bearer {token}'},
    params={
        'care_recipient_id': 1,
        'event_type': 'Cough',
        'days': 7
    }
)
events = response.json()

# Get statistics
stats_response = requests.get(
    'http://localhost:8000/api/audio-events/stats',
    headers={'Authorization': f'Bearer {token}'},
    params={'care_recipient_id': 1, 'days': 30}
)
stats = stats_response.json()
```

## Long-Term Analysis Possibilities

With this data, you can now:

1. **Track Respiratory Health Trends**
   - Monitor cough frequency over time
   - Identify patterns (time of day, seasonal)
   - Correlate with other health metrics

2. **Generate Reports**
   - Weekly/monthly summaries
   - Compare different recipients
   - Export data for medical professionals

3. **Predictive Analytics**
   - Detect early signs of respiratory issues
   - Alert when cough frequency exceeds baseline
   - Identify triggers or environmental factors

4. **Visualizations**
   - Time-series charts of cough/sneeze frequency
   - Heatmaps showing peak times
   - Comparison dashboards

## Next Steps

To fully utilize this integration:

1. **Add UI Components** to display statistics in the profile dashboard
2. **Create Reports** showing trends over time
3. **Add Alerts** when cough frequency exceeds thresholds
4. **Export Functionality** for medical reports
5. **Analytics Dashboard** with charts and visualizations

## Testing

The database table will be automatically created when you restart the backend server. To test:

1. Restart the backend: `python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`
2. Open the audio monitor: `http://localhost:5001`
3. Start monitoring and make cough sounds
4. Check the database or call the API to see logged events

## Notes

- Events are logged asynchronously to avoid blocking real-time detection
- Failed database logs are silently ignored to maintain detection performance
- Authentication is required for all API endpoints
- Events are automatically linked to the authenticated caretaker
- Care recipient ID is optional (can be null for general monitoring)
