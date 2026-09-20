"""Course and lecture CRUD tests, including cross-user isolation."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

SETTINGS = Settings(app_env="test")


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def register_token(client: TestClient, email: str, role: str) -> str:
    """Register one account and return its access token."""

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "display_name": email.split("@")[0],
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def create_course(client: TestClient, token: str, title: str = "Deep Learning") -> str:
    """Create one course and return its id."""

    response = client.post(
        "/api/v1/courses",
        json={"title": title, "code": "CS-6420"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["course_id"]


def test_professor_can_create_and_list_courses() -> None:
    """Professors must be able to create and list their own courses."""

    client = build_test_client()
    professor_token = register_token(client, "prof@example.com", "professor")
    course_id = create_course(client, professor_token)

    listing = client.get("/api/v1/courses", headers=auth_headers(professor_token))
    assert listing.status_code == 200
    listed_ids = [course["course_id"] for course in listing.json()]
    assert course_id in listed_ids

    single = client.get(
        f"/api/v1/courses/{course_id}", headers=auth_headers(professor_token)
    )
    assert single.status_code == 200
    assert single.json()["code"] == "CS-6420"


def test_student_cannot_create_courses() -> None:
    """Student accounts must be forbidden from creating courses."""

    client = build_test_client()
    student_token = register_token(client, "student@example.com", "student")
    response = client.post(
        "/api/v1/courses",
        json={"title": "Deep Learning", "code": "CS-6420"},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 403


def test_cross_professor_course_access_is_forbidden() -> None:
    """Another professor must not read or delete someone else's course."""

    client = build_test_client()
    owner_token = register_token(client, "owner@example.com", "professor")
    stranger_token = register_token(client, "stranger@example.com", "professor")
    course_id = create_course(client, owner_token)

    forbidden_read = client.get(
        f"/api/v1/courses/{course_id}", headers=auth_headers(stranger_token)
    )
    assert forbidden_read.status_code == 403

    forbidden_delete = client.delete(
        f"/api/v1/courses/{course_id}", headers=auth_headers(stranger_token)
    )
    assert forbidden_delete.status_code == 403


def test_professor_can_manage_lectures_in_owned_course() -> None:
    """Lectures must be creatable, listable, readable, and deletable."""

    client = build_test_client()
    professor_token = register_token(client, "prof@example.com", "professor")
    course_id = create_course(client, professor_token)

    created = client.post(
        "/api/v1/lectures",
        json={"course_id": course_id, "title": "Attention Mechanisms"},
        headers=auth_headers(professor_token),
    )
    assert created.status_code == 201
    lecture_id = created.json()["lecture_id"]

    listing = client.get(
        "/api/v1/lectures",
        params={"course_id": course_id},
        headers=auth_headers(professor_token),
    )
    assert listing.status_code == 200
    assert [lecture["lecture_id"] for lecture in listing.json()] == [lecture_id]

    single = client.get(
        f"/api/v1/lectures/{lecture_id}", headers=auth_headers(professor_token)
    )
    assert single.status_code == 200
    assert single.json()["title"] == "Attention Mechanisms"

    deleted = client.delete(
        f"/api/v1/lectures/{lecture_id}", headers=auth_headers(professor_token)
    )
    assert deleted.status_code == 204
    missing = client.get(
        f"/api/v1/lectures/{lecture_id}", headers=auth_headers(professor_token)
    )
    assert missing.status_code == 404


def test_lecture_in_foreign_course_is_forbidden() -> None:
    """Lecture creation in a course owned by someone else must fail."""

    client = build_test_client()
    owner_token = register_token(client, "owner@example.com", "professor")
    stranger_token = register_token(client, "stranger@example.com", "professor")
    course_id = create_course(client, owner_token)

    response = client.post(
        "/api/v1/lectures",
        json={"course_id": course_id, "title": "Foreign Lecture"},
        headers=auth_headers(stranger_token),
    )
    assert response.status_code == 403


def test_lecture_in_unknown_course_is_not_found() -> None:
    """Lecture creation for a nonexistent course must fail with 404."""

    client = build_test_client()
    professor_token = register_token(client, "prof@example.com", "professor")
    response = client.post(
        "/api/v1/lectures",
        json={"course_id": "course_missing", "title": "Ghost Lecture"},
        headers=auth_headers(professor_token),
    )
    assert response.status_code == 404
