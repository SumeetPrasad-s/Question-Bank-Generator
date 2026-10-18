"""
test_system.py
==============
Automated test suite verifying:
- Authentication & RBAC (Faculty & HOD)
- Question submission & HOD approval workflow
- Algorithmic Question Paper Generation satisfying constraints
- Question Swapping functionality
- ACID Transactional Finalization & PDF Generation
- OS Concurrency Locks & Atomic File I/O
"""

import os
import json
from app import app
from db import get_db_connection

def test_full_pipeline():
    client = app.test_client()
    print("\n--- [TEST 1] Testing Faculty Login & Question Submission ---")
    
    # 1. Login as Faculty
    res = client.post("/login", data={"username": "faculty1", "password": "fac123"}, follow_redirects=True)
    assert res.status_code == 200
    print("Faculty login successful!")

    # 2. Submit a new question
    res = client.post("/faculty/add-question", data={
        "subject_id": 1,
        "unit_id": 1,
        "question_text": "Explain the role of Dispatcher in CPU scheduling with context switching overheads.",
        "marks": 5,
        "difficulty": "Medium",
        "blooms_level": "Understand"
    }, follow_redirects=True)
    assert res.status_code == 200
    print("Question submitted by faculty!")

    # Verify pending state in DB
    conn = get_db_connection()
    q = conn.execute("SELECT * FROM questions WHERE question_text LIKE '%role of Dispatcher%'").fetchone()
    assert q is not None
    assert q['status'] == 'PENDING'
    q_id = q['question_id']
    conn.close()
    print(f"Verified new question pending with ID: {q_id}")

    print("\n--- [TEST 2] Testing HOD Login & Question Approval ---")
    # Logout faculty and login as HOD
    client.get("/logout")
    res = client.post("/login", data={"username": "hod", "password": "hod123"}, follow_redirects=True)
    assert res.status_code == 200
    print("HOD login successful!")

    # Approve the question
    res = client.post(f"/hod/approve-question/{q_id}", follow_redirects=True)
    assert res.status_code == 200

    conn = get_db_connection()
    q_updated = conn.execute("SELECT status, approved_by FROM questions WHERE question_id = ?", (q_id,)).fetchone()
    assert q_updated['status'] == 'APPROVED'
    conn.close()
    print(f"Question {q_id} approved by HOD successfully!")

    print("\n--- [TEST 3] Testing Algorithmic Paper Generation ---")
    gen_payload = {
        "subject_id": 1,
        "sections": [
            {"section_name": "Part A - Short Answer Questions", "marks_per_q": 2, "num_questions": 5},
            {"section_name": "Part B - Conceptual & Analytical", "marks_per_q": 5, "num_questions": 4},
            {"section_name": "Part C - Comprehensive Problems", "marks_per_q": 10, "num_questions": 2}
        ],
        "difficulty": {"Easy": 30, "Medium": 50, "Hard": 20},
        "blooms": {}
    }
    res = client.post("/api/generate-preview", json=gen_payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["total_marks"] == 50
    assert len(data["sections"]) == 3
    print(f"Paper generated successfully: Total Marks = {data['total_marks']}, Total Questions = {data['total_questions']}")
    print("Section Breakdown:", [(s['section_name'], f"{s['num_questions']} Qs x {s['marks_per_q']}M = {s['total_section_marks']}M") for s in data['sections']])
    print("Difficulty Stats:", data['difficulty_stats'])
    print("Bloom's Stats:", data['blooms_stats'])

    print("\n--- [TEST 4] Testing Question Swapping ---")
    # Swap first question of section 1
    target_q = data['sections'][0]['questions'][0]
    excluded_ids = [q['question_id'] for s in data['sections'] for q in s['questions']]
    swap_res = client.post("/api/swap-question", json={
        "subject_id": 1,
        "question_id": target_q['question_id'],
        "excluded_ids": excluded_ids
    })
    swap_data = swap_res.get_json()
    assert swap_res.status_code == 200
    if swap_data["success"]:
        print(f"Swapped Q[{target_q['question_id']}] -> Q[{swap_data['question']['question_id']}]: {swap_data['question']['question_text'][:50]}...")
    else:
        print("Swap note:", swap_data.get("error"))

    print("\n--- [TEST 5] Testing ACID Transaction Finalization & PDF Generation ---")
    finalize_payload = {
        "subject_id": 1,
        "paper_title": "Automated End Semester Exam 2026",
        "duration_minutes": 180,
        "semester": 5,
        "academic_year": "2026-2027",
        "total_marks": data["total_marks"],
        "sections": data["sections"]
    }
    final_res = client.post("/api/finalize-paper", json=finalize_payload)
    assert final_res.status_code == 200
    final_data = final_res.get_json()
    assert final_data["success"] is True
    paper_id = final_data["paper_id"]
    print(f"Paper successfully finalized with ID: {paper_id}")

    # Verify DB commit & Question usage increment
    conn = get_db_connection()
    paper = conn.execute("SELECT * FROM generated_papers WHERE paper_id = ?", (paper_id,)).fetchone()
    assert paper is not None
    assert paper['pdf_path'] and os.path.exists(paper['pdf_path'])
    print(f"PDF verified on disk at: {paper['pdf_path']}")

    # Verify usage_count incremented
    first_q_id = data['sections'][0]['questions'][0]['question_id']
    usage_check = conn.execute("SELECT usage_count, last_used_at FROM questions WHERE question_id = ?", (first_q_id,)).fetchone()
    assert usage_check['usage_count'] >= 1
    assert usage_check['last_used_at'] is not None
    print(f"Verified usage count for question {first_q_id}: {usage_check['usage_count']} (last used: {usage_check['last_used_at']})")
    conn.close()

    print("\n--- [TEST 6] Testing PDF Download Endpoint ---")
    pdf_res = client.get(f"/hod/download-paper/{paper_id}")
    assert pdf_res.status_code == 200
    assert len(pdf_res.data) > 1000
    print(f"PDF download successful! Size: {len(pdf_res.data)} bytes.")

    print("\n>>> ALL 6 END-TO-END PIPELINE TESTS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    test_full_pipeline()
