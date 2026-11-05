import requests
import time
import uuid

base_url = "http://127.0.0.1:8000/api/signup"

unique_username = f"testuser_{uuid.uuid4().hex[:8]}"
unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"

# 1. Test FRESH registration
print(f"Testing FRESH registration with {unique_email}...")
payload_fresh = {
    "username": unique_username,
    "email": unique_email,
    "phone_number": f"9{uuid.uuid4().hex[:9]}",
    "password": "Password@123",
    "full_name": "Test User",
    "care_recipients": []
}
try:
    r = requests.post(base_url, json=payload_fresh)
    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {r.json()}")
except Exception as e:
    print(f"ERROR: {e}")

# 2. Test DUPLICATE email (Unique Phone)
existing_email = "duplicate-test@example.com"
unique_phone = f"8{uuid.uuid4().hex[:9]}"
print(f"\nTesting DUPLICATE email (Unique Phone): {existing_email} / {unique_phone}")
payload_dupe_email = {
    "username": f"user_{uuid.uuid4().hex[:8]}",
    "email": existing_email,
    "phone_number": unique_phone,
    "password": "Password@123",
    "full_name": "Dupe Email User",
    "care_recipients": []
}
try:
    r = requests.post(base_url, json=payload_dupe_email)
    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {r.json()}")
except Exception as e:
    print(f"ERROR: {e}")

# 3. Test DUPLICATE phone (Unique Email)
existing_phone = "7051345437"
unique_email_2 = f"test_{uuid.uuid4().hex[:8]}@example.com"
print(f"\nTesting DUPLICATE phone (Unique Email): {unique_email_2} / {existing_phone}")
payload_dupe_phone = {
    "username": f"user_{uuid.uuid4().hex[:8]}",
    "email": unique_email_2,
    "phone_number": existing_phone,
    "password": "Password@123",
    "full_name": "Dupe Phone User",
    "care_recipients": []
}
try:
    r = requests.post(base_url, json=payload_dupe_phone)
    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {r.json()}")
except Exception as e:
    print(f"ERROR: {e}")

# 4. Test DUPLICATE username
existing_username = "test_user_22" # ID 1 from caretakers table
print(f"\nTesting DUPLICATE username: {existing_username}")
payload_dupe_user = {
    "username": existing_username,
    "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
    "phone_number": f"7{uuid.uuid4().hex[:9]}",
    "password": "Password@123",
    "full_name": "Dupe Username User",
    "care_recipients": []
}
try:
    r = requests.post(base_url, json=payload_dupe_user)
    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {r.json()}")
except Exception as e:
    print(f"ERROR: {e}")
