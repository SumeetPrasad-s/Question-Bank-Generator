"""
test_dynamic_flow.py
====================
Automated test suite verifying the dynamic user registration, separate auth database,
user-defined subject/units creation, question submission, HOD approval, and paper generation.
"""

from app import app
from db import get_auth_db, get_db_connection

def test_workflow():
    client = app.test_client()

    print("\n--- 1. Testing HOD and Faculty Registration (users_auth.db) ---")
    # Register HOD
    res = client.post("/register", data={
        "role": "HOD",
        "full_name": "Dr. Alan Turing",
        "department": "Computer Science & Engineering",
        "username": "hod_turing",
        "password": "mypassword123",
        "confirm_password": "mypassword123"
    }, follow_redirects=True)
    assert res.status_code == 200

    # Register Faculty
    res = client.post("/register", data={
        "role": "FACULTY",
        "full_name": "Prof. Dennis Ritchie",
        "department": "Computer Science & Engineering",
        "username": "prof_ritchie",
        "password": "facpassword123",
        "confirm_password": "facpassword123"
    }, follow_redirects=True)
    assert res.status_code == 200

    # Verify separate auth DB
    auth_conn = get_auth_db()
    users = auth_conn.execute("SELECT username, role, full_name FROM users").fetchall()
    auth_conn.close()
    assert len(users) == 2
    print("Registered users successfully in users_auth.db:", [dict(u) for u in users])

    print("\n--- 2. Testing Faculty Login ---")
    res = client.post("/login", data={
        "username": "prof_ritchie",
        "password": "facpassword123"
    }, follow_redirects=True)
    assert res.status_code == 200
    print("Faculty authenticated successfully using custom registered credentials!")

    print("\n--- 3. Testing Dynamic Subject & Unit Creation ---")
    # Add custom subject
    res = client.post("/subjects", data={
        "action": "add_subject",
        "subject_code": "CS301",
        "subject_name": "Data Structures & Algorithms",
        "department": "Computer Science & Engineering",
        "semester": 3
    }, follow_redirects=True)
    assert res.status_code == 200

    conn = get_db_connection()
    subj = conn.execute("SELECT * FROM subjects WHERE subject_code = 'CS301'").fetchone()
    assert subj is not None
    subj_id = subj["subject_id"]

    # Add Units
    client.post("/subjects", data={
        "action": "add_unit",
        "subject_id": subj_id,
        "unit_number": 1,
        "unit_name": "Arrays, Stacks and Queues"
    }, follow_redirects=True)

    client.post("/subjects", data={
        "action": "add_unit",
        "subject_id": subj_id,
        "unit_number": 2,
        "unit_name": "Binary Trees and Binary Search Trees"
    }, follow_redirects=True)

    units = conn.execute("SELECT * FROM units WHERE subject_id = ?", (subj_id,)).fetchall()
    assert len(units) == 2
    conn.close()
    print(f"Created custom Subject ID {subj_id} with {len(units)} units successfully!")

    print("\n--- 4. Testing Faculty Question Submission ---")
    # Submit 2M question
    client.post("/faculty/add-question", data={
        "subject_id": subj_id,
        "unit_id": units[0]["unit_id"],
        "question_text": "Define Stack and explain LIFO principle with push/pop operations.",
        "marks": 2,
        "difficulty": "Easy",
        "blooms_level": "Remember"
    }, follow_redirects=True)

    # Submit 5M question
    client.post("/faculty/add-question", data={
        "subject_id": subj_id,
        "unit_id": units[1]["unit_id"],
        "question_text": "Explain insertion and deletion in a Binary Search Tree with time complexity analysis.",
        "marks": 5,
        "difficulty": "Medium",
        "blooms_level": "Understand"
    }, follow_redirects=True)

    conn = get_db_connection()
    q_count = conn.execute("SELECT COUNT(*) as cnt FROM questions WHERE status = 'PENDING'").fetchone()["cnt"]
    assert q_count == 2
    conn.close()
    print(f"Submitted {q_count} questions by faculty, currently pending HOD review.")

    print("\n--- 5. Testing HOD Login & Question Approval ---")
    client.get("/logout")
    res = client.post("/login", data={
        "username": "hod_turing",
        "password": "mypassword123"
    }, follow_redirects=True)
    assert res.status_code == 200
    print("HOD logged in successfully with custom credentials!")

    # Approve all pending questions
    conn = get_db_connection()
    pending_qs = conn.execute("SELECT question_id FROM questions WHERE status = 'PENDING'").fetchall()
    for pq in pending_qs:
        client.post(f"/hod/approve-question/{pq['question_id']}", follow_redirects=True)

    app_count = conn.execute("SELECT COUNT(*) as cnt FROM questions WHERE status = 'APPROVED'").fetchone()["cnt"]
    assert app_count == 2
    conn.close()
    print(f"HOD approved all {app_count} questions successfully!")

    print("\n--- 6. Testing Paper Generation for the Custom Subject ---")
    gen_payload = {
        "subject_id": subj_id,
        "sections": [
            {"section_name": "Section A", "marks_per_q": 2, "num_questions": 1},
            {"section_name": "Section B", "marks_per_q": 5, "num_questions": 1}
        ],
        "difficulty": {},
        "blooms": {}
    }
    res = client.post("/api/generate-preview", json=gen_payload)
    assert res.status_code == 200
    gen_data = res.get_json()
    assert gen_data["success"] is True
    assert gen_data["total_marks"] == 7
    print(f"Generated paper with total marks: {gen_data['total_marks']}")

    # Finalize Paper
    finalize_payload = {
        "subject_id": subj_id,
        "paper_title": "Data Structures Class Test 2026",
        "duration_minutes": 60,
        "semester": 3,
        "academic_year": "2026-2027",
        "total_marks": 7,
        "sections": gen_data["sections"]
    }
    fin_res = client.post("/api/finalize-paper", json=finalize_payload)
    assert fin_res.status_code == 200
    fin_data = fin_res.get_json()
    assert fin_data["success"] is True
    print(f"Paper saved and official PDF compiled with ID: {fin_data['paper_id']}!")

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_workflow()
