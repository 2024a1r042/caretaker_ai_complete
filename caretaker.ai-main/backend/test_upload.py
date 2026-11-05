import requests

url = "http://127.0.0.1:8000/api/recipients/1/reports"

payload = {}
files=[
  ('file',('report.txt',b'The patient has anaemia','text/plain'))
]
headers = {
  'Authorization': 'Bearer placeholder'
}

response = requests.request("POST", url, headers=headers, data=payload, files=files)

print(response.text)
