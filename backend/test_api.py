

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rest_framework.test import APIClient

client = APIClient()

# Login as the second user
login_response = client.post(
    "/api/auth/login/",
    {
        "username": "smartstudy_test2",
        "password": "StudyTest2@12345",
    },
    format="json",
)

print("User 2 login status:", login_response.status_code)

if login_response.status_code == 200:
    token = login_response.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Try to access User 1's PDF
    

response = client.post(
    "/api/learning/ask/",
    {"question": "இந்த PDF-ல் என்ன இருக்கிறது?"},
    format="json",
)

print("Q&A status:", response.status_code)
print("Response:", response.data)
