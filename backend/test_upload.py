import requests

url = "http://127.0.0.1:8000/api/ingest/upload"
files = {"files": open("sales.csv", "rb")}  # put sales.csv in the same folder
resp = requests.post(url, files=files)
print(resp.status_code)
print(resp.json())