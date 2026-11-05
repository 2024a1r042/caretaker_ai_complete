# Video Monitoring System - Integration Guide

## 🎯 Overview

The Video Monitoring System is now fully integrated into the CareTaker platform with industry-grade features including:

- ✅ **Dual Functionality**: Upload video analysis & Live camera monitoring
- ✅ **Email Alerts**: Automatic notifications to logged-in caretakers
- ✅ **Real-time Processing**: Background video analysis with status tracking
- ✅ **Session Management**: Track live monitoring sessions
- ✅ **Auto-refresh**: Dashboard refreshes after sending alerts
- ✅ **Unified Detection**: Fall detection + Inactivity monitoring in one system

## 📋 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend Dashboard                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │Upload Video  │  │Live Monitor  │  │   History    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend API Routes                        │
│  /api/video-monitoring/upload-video                         │
│  /api/video-monitoring/status/{process_id}                  │
│  /api/video-monitoring/start-live-monitoring                │
│  /api/video-monitoring/stop-live-monitoring/{session_id}    │
│  /api/video-monitoring/alert/{session_id}                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Video Processing Engine                         │
│  ┌──────────────────────────────────────────────────┐       │
│  │         united_monitor.py                        │       │
│  │  ┌──────────────┐      ┌──────────────────┐     │       │
│  │  │Fall Detection│  +   │Inactivity Monitor│     │       │
│  │  └──────────────┘      └──────────────────┘     │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Email Alert System                        │
│  - Fall detection alerts (URGENT)                           │
│  - Inactivity alerts (WARNING)                              │
│  - Detailed fall information                                │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Access Video Monitoring

Navigate to: `http://localhost:5500/video_monitoring.html`

Or add a link from your dashboard:
```html
<a href="video_monitoring.html" class="btn btn-primary">
    <i class="fas fa-video"></i> Video Monitoring
</a>
```

### 2. Upload Video Analysis

1. **Select Tab**: Click on "Upload Video" tab
2. **Choose File**: Drag & drop or click to browse
3. **Wait for Processing**: Progress bar shows analysis status
4. **View Results**: 
   - Green alert = No falls detected
   - Red alert = Fall detected (email sent automatically)

### 3. Live Monitoring

1. **Start Session**: Click "Start Monitoring" button
2. **Get Session ID**: Copy the displayed session ID
3. **Launch Desktop App**: Run the monitoring script with session ID
4. **Monitor Alerts**: Real-time alerts appear in the dashboard
5. **Stop Session**: Click "Stop Monitoring" when done

## 🔧 Backend Setup

### API Routes Added

File: `backend/routes/video_monitoring.py`

**Endpoints:**
- `POST /api/video-monitoring/upload-video` - Upload video for analysis
- `GET /api/video-monitoring/status/{process_id}` - Check processing status
- `GET /api/video-monitoring/download/{process_id}` - Download processed video
- `POST /api/video-monitoring/start-live-monitoring` - Start live session
- `POST /api/video-monitoring/stop-live-monitoring/{session_id}` - Stop session
- `POST /api/video-monitoring/alert/{session_id}` - Report alert from live feed
- `GET /api/video-monitoring/session/{session_id}` - Get session info

### Email Integration

File: `backend/utils/email.py`

Enhanced `send_fall_alert_email()` function with:
- **Urgency Detection**: Different alerts for live vs uploaded videos
- **Detailed Information**: Fall timestamp, confidence, details
- **Professional Formatting**: HTML email with tables
- **Action Items**: Clear instructions for caretakers

## 📱 Frontend Features

### Modern UI Components

File: `frontend/video_monitoring.html`

**Features:**
- 🎨 Beautiful gradient design
- 📊 Real-time statistics
- 🔄 Drag & drop upload
- 📈 Progress tracking
- 🔔 Alert notifications
- 📱 Responsive layout

### JavaScript Functionality

File: `frontend/video_monitoring.js`

**Capabilities:**
- Drag & drop file upload
- Real-time status polling
- Session management
- Alert sound playback
- Auto-refresh on alerts
- Error handling

## 🎯 Industry-Grade Features

### 1. **Robust Error Handling**
```python
try:
    # Process video
    await process_video_analysis(...)
except Exception as e:
    # Log error
    # Update status
    # Notify user
```

### 2. **Background Processing**
- Videos process asynchronously
- Non-blocking API responses
- Status polling for updates

### 3. **Security**
- JWT authentication required
- User ownership verification
- Secure file handling
- Automatic cleanup

### 4. **Performance Optimization**
- Frame skipping for live feeds
- GPU acceleration support
- Efficient video encoding
- Caching mechanisms

### 5. **Email Notifications**
```python
# Automatic email on fall detection
await send_fall_alert_email(
    recipient_email=user.email,
    fall_data={
        "timestamp": datetime.now().isoformat(),
        "fall_count": len(falls_detected),
        "fall_details": falls_detected,
        "location": "Live Camera/Video Upload",
        "video_url": download_link
    }
)
```

### 6. **Session Management**
- Track active monitoring sessions
- Prevent duplicate sessions
- Session history
- Alert aggregation

## 📧 Email Alert System

### Alert Types

**1. Live Monitoring Alert (URGENT)**
- Subject: "🚨 FALL DETECTED: IMMEDIATE ATTENTION REQUIRED"
- Red color scheme
- Immediate action required
- Real-time notification

**2. Video Upload Alert (Review)**
- Subject: "🚨 FALL DETECTED: Please Review"
- Orange color scheme
- Review requested
- Includes video link

### Email Content

```html
<h2>🚨 Fall Detected</h2>
<p><strong>Time:</strong> 2026-02-13 13:45:23</p>
<p><strong>Location:</strong> Live Camera Monitoring</p>
<p><strong>Total Falls Detected:</strong> 1</p>

<h3>Fall Details:</h3>
<table>
  <tr>
    <th>Time</th>
    <th>Confidence</th>
    <th>Details</th>
  </tr>
  <tr>
    <td>13:45:23</td>
    <td>95.2%</td>
    <td>Fall detected - high confidence</td>
  </tr>
</table>

<div class="action-box">
  <strong>Action Required: IMMEDIATE ATTENTION REQUIRED</strong>
  <p>This is a LIVE alert. Please check on the person immediately!</p>
</div>
```

## 🔄 Dashboard Auto-Refresh

After sending an alert email, the system:

1. **Updates UI**: Shows alert notification
2. **Plays Sound**: Audio alert for attention
3. **Refreshes Stats**: Updates monitoring statistics
4. **Logs Event**: Records in session history

## 🛠️ Configuration

### Environment Variables

Add to `.env` file:
```env
# Email Configuration (already set)
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_FROM=your_email@gmail.com
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587

# Video Processing
MAX_VIDEO_SIZE_MB=100
TEMP_UPLOAD_DIR=backend/temp_uploads
PROCESSED_VIDEO_DIR=backend/processed_videos
OUTPUT_VIDEO_DIR=backend/output_videos
```

### Video Monitor Settings

Adjust in `united_monitor.py`:
```python
# Sensitivity levels
--sensitivity low|medium|high

# Inactivity threshold
--threshold 30  # seconds

# Frame skip (performance)
--frame-skip 2  # process every 2nd frame
```

## 📊 Usage Examples

### Example 1: Upload Video via API

```javascript
const formData = new FormData();
formData.append('file', videoFile);

const response = await fetch('/api/video-monitoring/upload-video', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`
    },
    body: formData
});

const { process_id } = await response.json();
// Poll status endpoint for updates
```

### Example 2: Start Live Monitoring

```javascript
const response = await fetch('/api/video-monitoring/start-live-monitoring', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`
    }
});

const { session_id } = await response.json();
// Use session_id to launch desktop app
```

### Example 3: Desktop App with Session

```bash
cd backend/VideoMonitoring
python run_live_monitor.py --session-id YOUR_SESSION_ID
```

## 🎨 Customization

### Modify Alert Thresholds

Edit `backend/routes/video_monitoring.py`:
```python
# Change fall detection sensitivity
fall_detector = FallDetector(sensitivity="high")

# Change inactivity threshold
inactivity_threshold = 45  # seconds
```

### Customize Email Templates

Edit `backend/utils/email.py`:
```python
# Modify email subject
subject = f"🚨 CUSTOM ALERT: {urgency_text}"

# Add custom HTML content
body = f"""
<div class="custom-section">
    <!-- Your custom content -->
</div>
"""
```

### Adjust UI Colors

Edit `frontend/video_monitoring.html`:
```css
:root {
    --primary: #4e73df;  /* Change primary color */
    --danger: #e74a3b;   /* Change alert color */
    --success: #1cc88a;  /* Change success color */
}
```

## 🐛 Troubleshooting

### Issue: Video Upload Fails

**Solution:**
1. Check file size (max 100MB)
2. Verify video format (MP4, AVI, MOV)
3. Check backend logs for errors
4. Ensure temp directory exists

### Issue: Email Not Sending

**Solution:**
1. Verify `.env` email configuration
2. Check SMTP credentials
3. Enable "Less secure app access" (Gmail)
4. Check spam folder

### Issue: Live Monitoring Not Starting

**Solution:**
1. Check if camera is accessible
2. Verify session ID is correct
3. Ensure desktop app is running
4. Check firewall settings

### Issue: Slow Processing

**Solution:**
1. Increase `--frame-skip` value
2. Enable GPU acceleration
3. Reduce video resolution
4. Close other applications

## 📈 Performance Metrics

### Expected Performance

**CPU Only:**
- Upload Processing: ~2-5 FPS
- Live Monitoring: 8-12 FPS (frame-skip=3)

**With GPU (CUDA):**
- Upload Processing: ~15-25 FPS
- Live Monitoring: 25-30 FPS (frame-skip=1)

### Optimization Tips

1. **Use GPU**: Install CUDA-enabled PyTorch
2. **Frame Skipping**: Adjust based on hardware
3. **Resolution**: Lower resolution = faster processing
4. **Batch Processing**: Process multiple videos sequentially

## 🔐 Security Considerations

1. **Authentication**: All endpoints require JWT token
2. **File Validation**: Check file type and size
3. **Path Sanitization**: Prevent directory traversal
4. **Automatic Cleanup**: Remove temporary files
5. **Session Isolation**: Users can only access their sessions

## 📝 API Response Examples

### Upload Video Response
```json
{
    "status": "success",
    "process_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "message": "Video uploaded successfully. Processing started."
}
```

### Status Check Response
```json
{
    "status": "completed",
    "progress": 100,
    "falls_detected": [
        {
            "timestamp": "2026-02-13T13:45:23",
            "message": "Fall detected - high confidence"
        }
    ],
    "has_falls": true,
    "output_filename": "analyzed_video.mp4",
    "elapsed_seconds": 45.2
}
```

### Live Session Response
```json
{
    "status": "success",
    "session_id": "x9y8z7w6-v5u4-3210-tuvw-xyz9876543210",
    "message": "Live monitoring session started."
}
```

## 🎓 Best Practices

1. **Always authenticate**: Include JWT token in all requests
2. **Handle errors gracefully**: Show user-friendly messages
3. **Poll status regularly**: Check every 2-3 seconds during processing
4. **Clean up sessions**: Stop live monitoring when done
5. **Test email alerts**: Verify email configuration before deployment
6. **Monitor performance**: Track FPS and adjust settings
7. **Log events**: Keep audit trail of all alerts

## 📞 Support

For issues or questions:
1. Check console logs for errors
2. Review this integration guide
3. Test with sample videos
4. Verify email configuration
5. Check system requirements

## 🎉 Success Checklist

- [ ] Backend API routes working
- [ ] Frontend dashboard accessible
- [ ] Video upload functional
- [ ] Email alerts sending
- [ ] Live monitoring starting
- [ ] Alerts displaying correctly
- [ ] Session management working
- [ ] Auto-refresh after alerts
- [ ] Error handling robust
- [ ] Performance optimized

---

**Congratulations!** Your Video Monitoring System is now fully integrated with industry-grade features! 🚀
