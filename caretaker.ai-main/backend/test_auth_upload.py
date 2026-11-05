import requests
import json
import sqlite3

# Get a real user token bypassing auth endpoint checking
with sqlite3.connect("e:/model_test/caretaker/backend/caretaker.db") as conn:
    c = conn.cursor()
    c.execute("SELECT username FROM caretakers LIMIT 1")
    user = c.fetchone()[0]
    
login_data = {"username": user, "password": "password123"}
res = requests.post("http://127.0.0.1:8000/api/login", json=login_data)
token = res.json().get("token")

if token:
    print(f"Token: {token}")
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("mock_report.pdf", b"Patient is cured of anemia and has mild diabetes.", "application/pdf")}
    upload_res = requests.post("http://127.0.0.1:8000/api/recipients/1/reports", headers=headers, files=files)
    print("Upload:", upload_res.text)
else:
    print("Login failed:", res.text)
