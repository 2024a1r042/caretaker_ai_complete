# Audio Monitoring Analytics Dashboard

## Overview
Successfully integrated comprehensive audio analytics into the CareTaker profile dashboard, providing visual insights into cough and sneeze detection patterns.

## Features Implemented

### 1. **Real-Time Statistics Cards**
- **Total Coughs (7d)**: Displays cough count with red gradient styling
- **Total Sneezes (7d)**: Displays sneeze count with amber gradient styling
- **Total Events (7d)**: Shows combined audio events with blue gradient styling
- All cards update dynamically based on selected time range and recipient

### 2. **Time Range Selector**
- Dropdown to select analysis period:
  - Last 7 Days (default)
  - Last 14 Days
  - Last 30 Days
  - Last 90 Days
- Refresh button to manually reload analytics

### 3. **Detection Trend Chart** (Line Chart)
- **Purpose**: Shows daily frequency of coughs and sneezes over time
- **Visualization**: Dual-line chart with filled areas
  - Red line for coughs
  - Amber line for sneezes
- **Insights**: Identify trends, spikes, or patterns in respiratory events

### 4. **Hourly Distribution Chart** (Bar Chart)
- **Purpose**: Displays peak detection times throughout the day
- **Visualization**: 24-hour bar chart (0:00 to 23:00)
- **Insights**: Identify when coughs/sneezes occur most frequently (e.g., morning, night)

### 5. **Event Distribution Chart** (Doughnut Chart)
- **Purpose**: Shows breakdown of event types
- **Categories**:
  - Coughs (red)
  - Sneezes (amber)
  - Talking (blue)
  - Noise (gray)
- **Insights**: Understand the composition of detected audio events

### 6. **Recent Detections List**
- **Purpose**: Display latest 10 audio events
- **Information Shown**:
  - Event type icon (🤧 for cough/sneeze, 🔊 for others)
  - Event type name
  - Date and time of detection
  - Confidence score percentage
- **Styling**: Color-coded borders (red for cough, amber for sneeze)
- **Interaction**: Hover effects for better UX

## Technical Implementation

### Frontend Components

#### HTML Structure (`profile.html`)
```html
<!-- Quick Stats -->
<div class="control-row">
    <div class="stat-pill">Total Coughs (7d): <strong id="totalCoughs">0</strong></div>
    <div class="stat-pill">Total Sneezes (7d): <strong id="totalSneezes">0</strong></div>
    <div class="stat-pill">Total Events (7d): <strong id="totalAudioEvents">0</strong></div>
</div>

<!-- Time Range Selector -->
<select id="audioTimeRange">
    <option value="7">Last 7 Days</option>
    <option value="14">Last 14 Days</option>
    <option value="30">Last 30 Days</option>
    <option value="90">Last 90 Days</option>
</select>

<!-- Charts -->
<canvas id="audioTrendChart"></canvas>
<canvas id="audioHourlyChart"></canvas>
<canvas id="audioTypeChart"></canvas>

<!-- Recent Events -->
<div id="recentAudioEvents"></div>
```

#### CSS Styling
- **Chart Cards**: Glassmorphism effect with hover animations
- **Event Items**: Color-coded with smooth transitions
- **Responsive Design**: Grid layout adapts to screen size

#### JavaScript Functions

**`fetchAudioAnalytics()`**
- Fetches statistics from `/api/audio-events/stats`
- Fetches detailed events from `/api/audio-events`
- Updates all charts and statistics
- Called on page load, recipient change, and time range change

**`renderAudioCharts(events, stats)`**
- Processes raw event data into chart-ready format
- Creates/updates three Chart.js instances:
  - Trend chart (daily aggregation)
  - Hourly distribution (24-hour bins)
  - Type distribution (pie chart)

**`renderRecentEvents(events)`**
- Generates HTML for recent event list
- Formats dates and times
- Applies appropriate styling based on event type

### Backend Integration

#### API Endpoints Used
1. **GET `/api/audio-events/stats`**
   - Query params: `days`, `care_recipient_id` (optional)
   - Returns: `{ cough_count, sneeze_count, talking_count, noise_count, total_events, date_range }`

2. **GET `/api/audio-events`**
   - Query params: `days`, `limit`, `care_recipient_id` (optional)
   - Returns: Array of event objects with `{ id, event_type, confidence, detected_at, ... }`

#### Data Flow
```
User Action (page load / recipient change / time range change)
    ↓
fetchAudioAnalytics()
    ↓
API Calls (stats + events)
    ↓
Data Processing (daily/hourly aggregation)
    ↓
Chart Rendering (Chart.js)
    ↓
UI Update (stats cards + recent events)
```

## User Experience

### Navigation
1. User opens profile dashboard
2. Scrolls to "Audio Monitoring & Analytics" section
3. Views current statistics and charts
4. Can:
   - Change time range to see historical trends
   - Click "Refresh" to reload data
   - Click "Open Live Monitor" to start real-time detection
   - Select different recipients to filter data

### Visual Hierarchy
1. **Top**: Quick stats and controls (most important)
2. **Middle**: Trend and hourly charts (analysis)
3. **Bottom**: Recent events and type distribution (details)

### Color Coding
- **Red (#fb7185)**: Coughs
- **Amber (#f6c23e)**: Sneezes
- **Blue (#4A90E2)**: General/Talking
- **Gray (#94a3b8)**: Noise

## Benefits for Caregivers

### 1. **Early Detection**
- Identify sudden increases in cough frequency
- Spot patterns that may indicate illness onset

### 2. **Pattern Recognition**
- See if coughs occur at specific times (e.g., night coughs)
- Correlate with environmental factors or activities

### 3. **Long-Term Tracking**
- Monitor respiratory health over weeks/months
- Compare different time periods
- Track improvement or deterioration

### 4. **Data-Driven Decisions**
- Share concrete data with healthcare providers
- Make informed decisions about care adjustments
- Document health trends for medical records

### 5. **Peace of Mind**
- Visual confirmation that monitoring is working
- Quick overview of respiratory health status
- Easy-to-understand charts and statistics

## Future Enhancements

### Potential Additions
1. **Export Functionality**
   - Download charts as images
   - Export data as CSV/PDF reports
   - Email reports to healthcare providers

2. **Alerts & Notifications**
   - Set thresholds for cough frequency
   - Email/SMS alerts when exceeded
   - Weekly summary emails

3. **Correlation Analysis**
   - Overlay weather data
   - Compare with medication schedules
   - Link to vital signs data

4. **Predictive Analytics**
   - ML-based trend prediction
   - Anomaly detection
   - Health risk scoring

5. **Comparative Views**
   - Compare multiple recipients
   - Week-over-week comparisons
   - Seasonal pattern analysis

## Testing Checklist

- [ ] Charts render correctly on page load
- [ ] Time range selector updates all charts
- [ ] Recipient filter works properly
- [ ] Recent events list displays correctly
- [ ] Hover effects work on all interactive elements
- [ ] Responsive design works on mobile/tablet
- [ ] Empty state displays when no data
- [ ] Error handling for API failures
- [ ] Chart animations are smooth
- [ ] Colors match design system

## Files Modified

1. **`frontend/profile.html`**
   - Added HTML structure for analytics section
   - Added CSS styles for charts and events
   - Added JavaScript for data fetching and rendering
   - Integrated Chart.js library

2. **Integration Points**
   - `selectRecipient()`: Calls `fetchAudioAnalytics()` on recipient change
   - Page load: Initial call to `fetchAudioAnalytics()`
   - Time range change: Event listener triggers refresh
   - Refresh button: Manual reload of analytics

## Dependencies

- **Chart.js 4.4.1**: For rendering all charts
- **Backend API**: Audio events endpoints
- **Authentication**: JWT token from localStorage

## Performance Considerations

- Charts are destroyed and recreated on data updates (prevents memory leaks)
- API calls are debounced through user actions (not auto-polling)
- Limited to 100 events per fetch (configurable)
- Charts use `maintainAspectRatio: false` for better responsiveness

## Conclusion

The audio analytics dashboard provides caregivers with powerful insights into respiratory health patterns. The combination of real-time statistics, trend analysis, and detailed event logs creates a comprehensive monitoring solution that's both informative and easy to use.
