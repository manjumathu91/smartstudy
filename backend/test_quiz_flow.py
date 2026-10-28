
import getpass
import requests

BASE_URL = "http://127.0.0.1:8000/api"

username = input("Username: ")
password = getpass.getpass("Password: ")

# 1. Login
login_response = requests.post(
    f"{BASE_URL}/auth/login/",
    json={"username": username, "password": password},
    timeout=30,
)
print("Login status:", login_response.status_code)

if login_response.status_code != 200:
    print(login_response.text)
    raise SystemExit("Login failed")

token = login_response.json()["access"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Generate quiz
document_id = int(input("Your uploaded document ID: "))

quiz_response = requests.post(
    f"{BASE_URL}/learning/quiz/",
    headers=headers,
    json={
        "document_id": document_id,
        "page_offset": 0,
        "number_of_questions": 3,
        "language": "Tamil",
    },
    timeout=120,
)

print("Quiz status:", quiz_response.status_code)

if quiz_response.status_code != 201:
    print(quiz_response.text)
    raise SystemExit("Quiz generation failed")

quiz = quiz_response.json()
print("Attempt ID:", quiz["attempt_id"])
print("Questions received:", len(quiz["questions"]))

# Check that answer keys are not exposed
leaked_keys = any(
    "correct_answer" in question or "explanation" in question
    for question in quiz["questions"]
)
print("Answer keys exposed before submission:", leaked_keys)

# 3. Submit answers
answers = {}
for index, question in enumerate(quiz["questions"]):
    print(f"\nQ{index + 1}: {question['question']}")
    for key, value in question["options"].items():
        print(f"  {key}. {value}")

    choice = input("Your answer (A/B/C/D, or Enter to skip): ")
    answers[str(index)] = choice.strip().upper()

submit_response = requests.post(
    f"{BASE_URL}/learning/quiz/submit/",
    headers=headers,
    json={
        "attempt_id": quiz["attempt_id"],
        "answers": answers,
    },
    timeout=30,
)

print("\nSubmit status:", submit_response.status_code)
print(submit_response.text)
