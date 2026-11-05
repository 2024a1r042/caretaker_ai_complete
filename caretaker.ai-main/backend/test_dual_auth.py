import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_registration_and_login():
    # 1. Register a Doctor
    doctor_data = {
        "full_name": "Dr. Smith",
        "email": "drsmith@example.com",
        "username": "drsmith",
        "phone_number": "1234567890",
        "password": "password123",
        "role": "doctor",
        "specialization": "Cardiology",
        "care_recipients": []
    }
    
    print("\nRegistering Doctor...")
    res = requests.post(f"{BASE_URL}/signup", json=doctor_data)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
    
    # 2. Login as Doctor
    login_data = {"username": "drsmith", "password": "password123"}
    print("\nLogging in as Doctor...")
    res = requests.post(f"{BASE_URL}/login", json=login_data)
    print(f"Status: {res.status_code}")
    login_json = res.json()
    print(f"Response: {login_json}")
    
    if res.status_code == 200:
        role = login_json['result']['user']['role']
        print(f"Detected Role: {role}")
        assert role == 'doctor'
    
    # 3. Register a Caretaker
    caretaker_data = {
        "full_name": "John Doe",
        "email": "john@example.com",
        "username": "johndoe",
        "phone_number": "0987654321",
        "password": "password123",
        "role": "caretaker",
        "care_recipients": [
            {
                "full_name": "Grandpa Joe",
                "email": "joe@example.com",
                "phone_number": "1112223333",
                "age": 80,
                "gender": "Male",
                "respiratory_condition_status": False
            }
        ]
    }
    
    print("\nRegistering Caretaker...")
    res = requests.post(f"{BASE_URL}/signup", json=caretaker_data)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
    
    # 4. Login as Caretaker
    login_data = {"username": "johndoe", "password": "password123"}
    print("\nLogging in as Caretaker...")
    res = requests.post(f"{BASE_URL}/login", json=login_data)
    print(f"Status: {res.status_code}")
    login_json = res.json()
    print(f"Response: {login_json}")
    
    if res.status_code == 200:
        role = login_json['result']['user']['role']
        print(f"Detected Role: {role}")
        assert role == 'caretaker'

if __name__ == "__main__":
    test_registration_and_login()
