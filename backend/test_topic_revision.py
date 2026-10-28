

import requests
from getpass import getpass

BASE_URL = "http://127.0.0.1:8000"


def login():
    """Log in and return the access token."""

    username = input("Username: ").strip()
    password = getpass("Password: ")

    response = requests.post(
        f"{BASE_URL}/api/auth/login/",
        json={
            "username": username,
            "password": password,
        },
        timeout=30,
    )

    print("\nLogin status:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        raise SystemExit("Login failed.")

    print("Login successful!")

    return response.json()["access"]


def create_revision_quiz(headers):
    """Create a topic-based revision quiz."""

    document_id = input(
        "\nDocument ID (e.g. 1): "
    ).strip()

    topic = input(
        "Revision topic (e.g. இன்பத்தமிழ்): "
    ).strip()

    if not document_id.isdigit() or not topic:
        raise SystemExit(
            "Enter a valid document ID and topic."
        )

    payload = {
        "document_id": int(document_id),
        "topic": topic,
        "number_of_questions": 3,
        "language": "Tamil",
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/learning/revision/quiz/",
            json=payload,
            headers=headers,
            timeout=120,
        )
    except requests.RequestException as error:
        raise SystemExit(
            f"Could not connect to the server: {error}"
        )

    print("\nRevision quiz status:", response.status_code)

    if response.status_code != 201:
        print(response.text)
        raise SystemExit("Quiz creation failed.")

    data = response.json()

    print("\nTopic:", data.get("topic"))
    print("Questions:", data.get("total_questions"))
    print("Message:", data.get("message"))

    return data


def conduct_quiz(quiz_data):
    """Display questions and collect the student's answers."""

    questions = quiz_data.get("questions", [])
    answers = {}

    if not questions:
        raise SystemExit("No questions were returned.")

    print("\n========== REVISION QUIZ ==========")

    for index, question in enumerate(questions):
        print(f"\nQuestion {index + 1}:")
        print(question["question"])

        for option, option_text in question["options"].items():
            print(f"  {option}. {option_text}")

        while True:
            selected = input(
                "Your answer (A/B/C/D): "
            ).strip().upper()

            if selected in ("A", "B", "C", "D"):
                answers[str(index)] = selected
                break

            print("Please enter A, B, C, or D.")

    return answers


def submit_quiz(headers, attempt_id, answers):
    """Submit answers to the backend and display the result."""

    submit_url = f"{BASE_URL}/api/learning/quiz/submit/"

    payload = {
        "attempt_id": attempt_id,
        "answers": answers,
    }

    try:
        response = requests.post(
            submit_url,
            json=payload,
            headers=headers,
            timeout=60,
        )
    except requests.RequestException as error:
        raise SystemExit(
            f"Could not submit quiz: {error}"
        )

    print("\nQuiz submit status:", response.status_code)

    try:
        result = response.json()
    except ValueError:
        print(response.text)
        raise SystemExit("Server returned an invalid response.")

    print("\n========== QUIZ RESULT ==========")
    print("Response:", result)

    if response.status_code == 200:
        print("\nCorrect answers:", result.get("correct_answers"))
        print("Total questions:", result.get("total_questions"))
        print("Score:", result.get("score"))
        print("Accuracy:", result.get("accuracy"), "%")

        print("\nWeak topics:")
        for topic in result.get("weak_topics", []):
            print("-", topic)

        print("\nQuestion-wise results:")
        for item in result.get("results", []):
            print("\nQuestion:", item.get("question"))
            print("Your answer:", item.get("selected_answer"))
            print("Correct answer:", item.get("correct_answer"))
            print("Correct:", item.get("is_correct"))
            print("Explanation:", item.get("explanation"))

    return response


def main():
    print("===== SMART STUDY AI =====")
    print("Topic-Based Revision Quiz")

    access_token = login()

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    quiz_data = create_revision_quiz(headers)

    print("\nQuiz attempt ID:", quiz_data["attempt_id"])

    answers = conduct_quiz(quiz_data)

    confirm = input(
        "\nSubmit your answers? (y/n): "
    ).strip().lower()

    if confirm != "y":
        print("Quiz submission cancelled.")
        return

    submit_quiz(
        headers=headers,
        attempt_id=quiz_data["attempt_id"],
        answers=answers,
    )


if __name__ == "__main__":
    main()
