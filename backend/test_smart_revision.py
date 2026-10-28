
import requests
from getpass import getpass

BASE_URL = "http://127.0.0.1:8000"

username = input("Username: ").strip()
password = getpass("Password: ")

login_response = requests.post(
    f"{BASE_URL}/api/auth/login/",
    json={
        "username": username,
        "password": password,
    },
    timeout=30,
)

print("Login status:", login_response.status_code)

if login_response.status_code != 200:
    print(login_response.text)
    raise SystemExit("Login failed.")

token = login_response.json()["access"]

response = requests.get(
    f"{BASE_URL}/api/learning/revision/",
    headers={
        "Authorization": f"Bearer {token}",
    },
    timeout=30,
)

print("Smart Revision status:", response.status_code)
print(response.text)
