import requests

url = "http://127.0.0.1:8000/api/doctor/patients/45/ai_chat"
payload = {
    "message": "What is the patient's risk score and current SpO2?",
    "history": []
}

response = requests.post(url, json=payload)
print(response.status_code)
try:
    print(response.json())
except Exception as e:
    print(response.text)
