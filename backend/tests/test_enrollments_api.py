"""Course enrollment and code-free live-lecture discovery tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app

SETTINGS = Settings(app_env="test")


def token_for(user_id: str, role: str = "student") -> str:
    """Mint a synthetic token for a selected role."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role=role))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def create_course(client: TestClient, professor: dict[str, str], code: str) -> dict:
    """Create one course as a professor and return its record."""

    response = client.post(
        "/api/v1/courses",
        json={"title": f"Course {code}", "code": code},
        headers=professor,
    )
    assert response.status_code == 201
    return response.json()


def start_session(
    client: TestClient,
    professor: dict[str, str],
    course_id: str,
    title: str,
    zoom_meeting_id: str | None = None,
) -> dict:
    """Start one active session for a course and return its record."""

    payload = {
        "lecture_id": f"lecture-{title}",
        "course_id": course_id,
        "title": title,
        "mode": "zoom" if zoom_meeting_id else "in_person",
    }
    if zoom_meeting_id:
        payload["zoom_meeting_id"] = zoom_meeting_id
    response = client.post("/api/v1/sessions", json=payload, headers=professor)
    assert response.status_code == 201
    return response.json()


def test_student_enrolls_by_course_code_idempotently() -> None:
    """Enrollment normalizes the code and repeats return the same record."""

    client = build_test_client()
    professor = auth_headers(token_for("prof-1", "professor"))
    student = auth_headers(token_for("student-1"))
    course = create_course(client, professor, "CS101")

    first = client.post(
        "/api/v1/enrollments", json={"course_code": "  cs101 "}, headers=student
    )
    assert first.status_code == 201
    body = first.json()
    assert body["course_id"] == course["course_id"]
    assert body["user_id"] == "student-1"
    assert body["course_title"] == "Course CS101"
    assert body["course_code"] == "CS101"
    assert body["is_auto_join_enabled"] is False
    assert body["enrolled_at"].endswith("Z")

    again = client.post(
        "/api/v1/enrollments", json={"course_code": "CS101"}, headers=student
    )
    assert again.status_code == 201
    assert again.json()["enrollment_id"] == body["enrollment_id"]

    listed = client.get("/api/v1/enrollments", headers=student)
    assert listed.status_code == 200
    assert [entry["enrollment_id"] for entry in listed.json()] == [body["enrollment_id"]]
    assert "no-store" in listed.headers["cache-control"]


def test_enrollment_rejects_professors_unknown_and_ambiguous_codes() -> None:
    """Only students enroll; unknown codes 404 and cross-professor clashes 409."""

    client = build_test_client()
    professor_a = auth_headers(token_for("prof-a", "professor"))
    professor_b = auth_headers(token_for("prof-b", "professor"))
    student = auth_headers(token_for("student-1"))
    create_course(client, professor_a, "SHARED")
    create_course(client, professor_b, "SHARED")

    forbidden = client.post(
        "/api/v1/enrollments", json={"course_code": "SHARED"}, headers=professor_a
    )
    assert forbidden.status_code == 403

    missing = client.post(
        "/api/v1/enrollments", json={"course_code": "NOPE99"}, headers=student
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["details"]["course_code"] == "NOPE99"

    ambiguous = client.post(
        "/api/v1/enrollments", json={"course_code": "shared"}, headers=student
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "duplicate"

    invalid = client.post(
        "/api/v1/enrollments",
        json={"course_code": "CS101", "user_id": "someone-else"},
        headers=student,
    )
    assert invalid.status_code == 422


def test_joining_by_code_enrolls_student_in_course() -> None:
    """One join-code join is enough for later lectures to be detected."""

    client = build_test_client()
    professor = auth_headers(token_for("prof-1", "professor"))
    student = auth_headers(token_for("student-1"))
    course = create_course(client, professor, "BIO200")
    first_session = start_session(client, professor, course["course_id"], "Week 1")

    joined = client.post(
        f"/api/v1/sessions/{first_session['session_id']}/participants", headers=student
    )
    assert joined.status_code == 201

    enrollments = client.get("/api/v1/enrollments", headers=student).json()
    assert [entry["course_id"] for entry in enrollments] == [course["course_id"]]

    # Professors joining their own session are not enrolled as students.
    client.post(
        f"/api/v1/sessions/{first_session['session_id']}/participants", headers=professor
    )
    assert client.get("/api/v1/enrollments", headers=professor).json() == []

    ended = client.post(
        f"/api/v1/sessions/{first_session['session_id']}/end", headers=professor
    )
    assert ended.status_code == 200
    second_session = start_session(client, professor, course["course_id"], "Week 2")

    available = client.get("/api/v1/sessions/available", headers=student)
    assert available.status_code == 200
    assert "no-store" in available.headers["cache-control"]
    matches = available.json()
    assert [match["session"]["session_id"] for match in matches] == [
        second_session["session_id"]
    ]
    assert matches[0]["matched_by"] == "enrollment"
    assert matches[0]["is_joined"] is False
    assert matches[0]["is_auto_join_enabled"] is False


def test_available_sessions_are_scoped_to_enrollments_and_report_join_state() -> None:
    """Only enrolled courses' active sessions are listed; joined state is reported."""

    client = build_test_client()
    professor = auth_headers(token_for("prof-1", "professor"))
    student = auth_headers(token_for("student-1"))
    other_student = auth_headers(token_for("student-2"))
    enrolled = create_course(client, professor, "MATH1")
    foreign = create_course(client, professor, "MATH2")
    client.post("/api/v1/enrollments", json={"course_code": "MATH1"}, headers=student)

    enrolled_session = start_session(client, professor, enrolled["course_id"], "Algebra")
    start_session(client, professor, foreign["course_id"], "Foreign")

    before = client.get("/api/v1/sessions/available", headers=student).json()
    assert [match["session"]["title"] for match in before] == ["Algebra"]
    assert before[0]["session"]["join_code"] == enrolled_session["join_code"]

    client.post(
        f"/api/v1/sessions/{enrolled_session['session_id']}/participants", headers=student
    )
    after = client.get("/api/v1/sessions/available", headers=student).json()
    assert after[0]["is_joined"] is True

    assert client.get("/api/v1/sessions/available", headers=other_student).json() == []

    # Ended sessions disappear from the list.
    client.post(f"/api/v1/sessions/{enrolled_session['session_id']}/end", headers=professor)
    assert client.get("/api/v1/sessions/available", headers=student).json() == []


def test_zoom_meeting_id_matches_active_session_without_enrollment() -> None:
    """A detected Zoom meeting id resolves the session even for unenrolled students."""

    client = build_test_client()
    professor = auth_headers(token_for("prof-1", "professor"))
    student = auth_headers(token_for("student-1"))
    course = create_course(client, professor, "PHYS1")
    zoom_session = start_session(
        client, professor, course["course_id"], "Zoom lecture", zoom_meeting_id="987654321"
    )
    start_session(client, professor, course["course_id"], "Other", zoom_meeting_id="111")

    matched = client.get(
        "/api/v1/sessions/available?zoom_meeting_id=987654321", headers=student
    ).json()
    assert [match["session"]["session_id"] for match in matched] == [
        zoom_session["session_id"]
    ]
    assert matched[0]["matched_by"] == "zoom_meeting"
    assert matched[0]["is_auto_join_enabled"] is False

    unmatched = client.get(
        "/api/v1/sessions/available?zoom_meeting_id=000", headers=student
    ).json()
    assert unmatched == []


def test_auto_join_preference_and_leaving_are_owner_scoped() -> None:
    """Students toggle auto-join and leave courses; other students cannot."""

    client = build_test_client()
    professor = auth_headers(token_for("prof-1", "professor"))
    student = auth_headers(token_for("student-1"))
    intruder = auth_headers(token_for("student-2"))
    course = create_course(client, professor, "HIST1")
    enrollment = client.post(
        "/api/v1/enrollments", json={"course_code": "HIST1"}, headers=student
    ).json()
    start_session(client, professor, course["course_id"], "Lecture")

    foreign_update = client.patch(
        f"/api/v1/enrollments/{enrollment['enrollment_id']}",
        json={"is_auto_join_enabled": True},
        headers=intruder,
    )
    assert foreign_update.status_code == 404

    updated = client.patch(
        f"/api/v1/enrollments/{enrollment['enrollment_id']}",
        json={"is_auto_join_enabled": True},
        headers=student,
    )
    assert updated.status_code == 200
    assert updated.json()["is_auto_join_enabled"] is True
    available = client.get("/api/v1/sessions/available", headers=student).json()
    assert available[0]["is_auto_join_enabled"] is True

    foreign_delete = client.delete(
        f"/api/v1/enrollments/{enrollment['enrollment_id']}", headers=intruder
    )
    assert foreign_delete.status_code == 404

    deleted = client.delete(
        f"/api/v1/enrollments/{enrollment['enrollment_id']}", headers=student
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/enrollments", headers=student).json() == []
    assert client.get("/api/v1/sessions/available", headers=student).json() == []


def test_available_sessions_require_authentication() -> None:
    """Anonymous callers cannot discover live sessions."""

    client = build_test_client()
    assert client.get("/api/v1/sessions/available").status_code == 401
    assert client.get("/api/v1/enrollments").status_code == 401
