-- Add sample audio events for recipient 45
-- Run this in your PostgreSQL terminal

-- First, check if recipient 45 exists
SELECT id, full_name, caretaker_id FROM care_recipients WHERE id = 45;

-- If the above returns a row, proceed with inserting sample data
-- Clear any existing audio events for recipient 45
DELETE FROM audio_events WHERE care_recipient_id = 45;

-- Insert sample cough events (last 7 days)
INSERT INTO audio_events (caretaker_id, care_recipient_id, event_type, confidence, detected_at, duration_ms)
SELECT 
    (SELECT caretaker_id FROM care_recipients WHERE id = 45),
    45,
    'Cough',
    65 + random() * 30,  -- Random confidence between 65-95
    NOW() - (random() * interval '7 days'),
    500
FROM generate_series(1, 50);  -- 50 cough events

-- Insert sample sneeze events (last 7 days)
INSERT INTO audio_events (caretaker_id, care_recipient_id, event_type, confidence, detected_at, duration_ms)
SELECT 
    (SELECT caretaker_id FROM care_recipients WHERE id = 45),
    45,
    'Sneeze',
    70 + random() * 28,  -- Random confidence between 70-98
    NOW() - (random() * interval '7 days'),
    500
FROM generate_series(1, 20);  -- 20 sneeze events

-- Insert sample talking events (last 7 days)
INSERT INTO audio_events (caretaker_id, care_recipient_id, event_type, confidence, detected_at, duration_ms)
SELECT 
    (SELECT caretaker_id FROM care_recipients WHERE id = 45),
    45,
    'Talking',
    60 + random() * 25,  -- Random confidence between 60-85
    NOW() - (random() * interval '7 days'),
    500
FROM generate_series(1, 10);  -- 10 talking events

-- Insert sample noise events (last 7 days)
INSERT INTO audio_events (caretaker_id, care_recipient_id, event_type, confidence, detected_at, duration_ms)
SELECT 
    (SELECT caretaker_id FROM care_recipients WHERE id = 45),
    45,
    'Noise',
    55 + random() * 20,  -- Random confidence between 55-75
    NOW() - (random() * interval '7 days'),
    500
FROM generate_series(1, 5);  -- 5 noise events

-- Verify the data was inserted
SELECT 
    event_type, 
    COUNT(*) as count,
    ROUND(AVG(confidence)::numeric, 2) as avg_confidence
FROM audio_events 
WHERE care_recipient_id = 45
GROUP BY event_type
ORDER BY count DESC;

-- Show total count
SELECT COUNT(*) as total_events FROM audio_events WHERE care_recipient_id = 45;

-- Show latest 5 events
SELECT 
    event_type, 
    ROUND(confidence::numeric, 2) as confidence,
    detected_at
FROM audio_events 
WHERE care_recipient_id = 45
ORDER BY detected_at DESC
LIMIT 5;
