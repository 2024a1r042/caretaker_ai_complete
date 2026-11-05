import requests
import json

url = "http://127.0.0.1:8000/api/doctor/patients/45/prescribe"
data = {
    "medicine_name": "Amoxicillin",
    "dosage": "250mg",
    "frequency": "Twice daily",
    "schedule_time": "08:00",
    "duration_days": 5,
    "notes": "Take after meals.",
    "current_stock": 10,
    "doses_per_day": 2
}

try:
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
