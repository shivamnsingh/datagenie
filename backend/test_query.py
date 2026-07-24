import requests

BASE = "http://127.0.0.1:8000"
FILE_ID = "760d820e-7b9f-47da-b91e-d201f73a04f0"  # from your upload response

# 1. Create a SQL session, registering the uploaded file as table "sales"
session_resp = requests.post(f"{BASE}/api/sql/session", json={
    "tables": [
        {"file_id": FILE_ID, "table_name": "sales"}
    ]
})
print("SESSION STATUS:", session_resp.status_code)
session_data = session_resp.json()
print("SESSION BODY:", session_data)

if session_resp.status_code != 200:
    raise SystemExit("Session creation failed — stopping here.")

session_id = session_data["session_id"]

# 2. Ask a natural language question
query_resp = requests.post(f"{BASE}/api/sql/query", json={
    "session_id": session_id,
    "question": "Which product generated the highest total revenue?"
})
print("\nQUERY STATUS:", query_resp.status_code)
print("QUERY BODY:", query_resp.json())
