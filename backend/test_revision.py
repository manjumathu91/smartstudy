
import getpass
import requests

BASE_URL = "http://127.0.0.1:8000/api"

username = input("Username: ")
password = getpass.getpass("Password: ")

# Login
login_response = requests.post(
    f"{BASE_URL}/auth/login/",
    json={
        "username": username,
        "password": password,
    },
    timeout=30,
)

print("Login status:", login_response.status_code)

if login_response.status_code != 200:
    print(login_response.text)
    raise SystemExit("Login failed")

token = login_response.json()["access"]

headers = {
    "Authorization": f"Bearer {token}",
}

# Smart Revision
response = requests.get(
    f"{BASE_URL}/learning/revision/",
    headers=headers,
    timeout=30,
)

print("Revision status:", response.status_code)
print(response.text)