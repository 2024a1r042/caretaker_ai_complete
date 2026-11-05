import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

url = f'https://generativelanguage.googleapis.com/v1beta/models?key={api_key}'

try:
    resp = requests.get(url)
    print(f"Status: {resp.status_code}")
    print(data := resp.json())
    if 'models' in data:
        for m in data['models']:
            print(m['name'])
except Exception as e:
    print(f"Error: {e}")
