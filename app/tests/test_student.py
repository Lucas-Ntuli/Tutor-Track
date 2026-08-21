def test_create_and_get_student(client):
    payload = {
        "full_name": "Ada Lovelace",
        "guardian_email": "guardian@example.com",
        "grade_level": "10",
    }
    created = client.post("/students", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["full_name"] == "Ada Lovelace"
    assert "created_at" in body

    fetched = client.get(f"/students/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["guardian_email"] == "guardian@example.com"


def test_get_missing_student_404(client):
    resp = client.get("/students/999999")
    assert resp.status_code == 404


def test_list_students_is_paginated(client):
    for i in range(3):
        client.post(
            "/students",
            json={
                "full_name": f"Student {i}",
                "guardian_email": f"student{i}@example.com",
            },
        )
    resp = client.get("/students", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 2
    assert len(body["items"]) <= 2
    assert body["total"] >= 3


def test_invalid_email_rejected(client):
    resp = client.post(
        "/students",
        json={"full_name": "Bad Email", "guardian_email": "not-an-email"},
    )
    assert resp.status_code == 422