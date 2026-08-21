from datetime import datetime, timedelta


def _make_student(client):
    resp = client.post(
        "/students",
        json={"full_name": "Session Student", "guardian_email": "s@example.com"},
    )
    return resp.json()["id"]


def _make_tutor_direct(tenant_name: str):
    # There's no /tutors router in the starter kit yet (see README
    # "next steps"), so tests insert a tutor directly via the DB
    # session to exercise the sessions endpoints.
    from database import get_session
    from models import Tutor

    db = get_session(tenant_name)
    tutor = Tutor(full_name="Test Tutor", subject_specialty="Math", hourly_rate=40)
    db.add(tutor)
    db.commit()
    db.refresh(tutor)
    tid = tutor.id
    db.close()
    return tid


def test_create_session_success(client):
    from tests.conftest import TEST_TENANT

    student_id = _make_student(client)
    tutor_id = _make_tutor_direct(TEST_TENANT)

    scheduled_at = (datetime.utcnow() + timedelta(days=1)).isoformat()
    resp = client.post(
        "/sessions",
        json={
            "student_id": student_id,
            "tutor_id": tutor_id,
            "scheduled_at": scheduled_at,
            "duration_minutes": 60,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "scheduled"


def test_double_booking_rejected(client):
    from tests.conftest import TEST_TENANT

    student_id = _make_student(client)
    tutor_id = _make_tutor_direct(TEST_TENANT)
    scheduled_at = datetime.utcnow() + timedelta(days=2)

    first = client.post(
        "/sessions",
        json={
            "student_id": student_id,
            "tutor_id": tutor_id,
            "scheduled_at": scheduled_at.isoformat(),
            "duration_minutes": 60,
        },
    )
    assert first.status_code == 201

    conflicting = client.post(
        "/sessions",
        json={
            "student_id": student_id,
            "tutor_id": tutor_id,
            "scheduled_at": (scheduled_at + timedelta(minutes=15)).isoformat(),
            "duration_minutes": 60,
        },
    )
    assert conflicting.status_code == 409


def test_scheduled_at_must_be_future(client):
    from tests.conftest import TEST_TENANT

    student_id = _make_student(client)
    tutor_id = _make_tutor_direct(TEST_TENANT)
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()

    resp = client.post(
        "/sessions",
        json={
            "student_id": student_id,
            "tutor_id": tutor_id,
            "scheduled_at": past,
            "duration_minutes": 60,
        },
    )
    assert resp.status_code == 422


def test_cancel_session(client):
    from tests.conftest import TEST_TENANT

    student_id = _make_student(client)
    tutor_id = _make_tutor_direct(TEST_TENANT)
    scheduled_at = datetime.utcnow() + timedelta(days=3)

    created = client.post(
        "/sessions",
        json={
            "student_id": student_id,
            "tutor_id": tutor_id,
            "scheduled_at": scheduled_at.isoformat(),
            "duration_minutes": 30,
        },
    ).json()

    cancelled = client.post(f"/sessions/{created['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"