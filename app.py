import os
import json
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_auth_db, get_db_connection
from generator import generate_question_paper, swap_alternative_question
from pdf_exporter import export_paper_to_pdf

app = Flask(__name__)
app.secret_key = "antigravity_automated_question_paper_system_secret_key_2026"

PDF_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_pdfs")
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    auth_conn = get_auth_db()
    user = auth_conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    auth_conn.close()
    return user

@app.context_processor
def inject_user():
    user = get_current_user()
    pending_count = 0
    if user and user["role"] == "HOD":
        conn = get_db_connection()
        row = conn.execute("SELECT COUNT(*) as cnt FROM questions WHERE status = 'PENDING'").fetchone()
        pending_count = row["cnt"] if row else 0
        conn.close()
    return dict(current_user=user, pending_approval_count=pending_count)

@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "HOD":
            return redirect(url_for("hod_generate_paper_page"))
        return redirect(url_for("faculty_my_questions"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "").strip()
        department = request.form.get("department", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not all([full_name, username, role, department, password]):
            flash("All fields are required.", "warning")
            return render_template("register.html")

        if role not in ["FACULTY", "HOD"]:
            flash("Invalid role selected.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "danger")
            return render_template("register.html")

        auth_conn = get_auth_db()
        existing = auth_conn.execute("SELECT user_id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            auth_conn.close()
            flash("This Official ID / Username is already registered.", "danger")
            return render_template("register.html")

        password_hash = generate_password_hash(password)
        try:
            auth_conn.execute("""
                INSERT INTO users (username, password_hash, full_name, role, department)
                VALUES (?, ?, ?, ?, ?)
            """, (username, password_hash, full_name, role, department))
            auth_conn.commit()
            auth_conn.close()
            flash("Account registered successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            auth_conn.rollback()
            auth_conn.close()
            flash(f"Error creating account: {str(e)}", "danger")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        auth_conn = get_auth_db()
        user = auth_conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        auth_conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            session["department"] = user["department"]
            flash(f"Welcome, {user['full_name']}!", "success")
            if user["role"] == "HOD":
                return redirect(url_for("hod_generate_paper_page"))
            else:
                return redirect(url_for("faculty_my_questions"))
        else:
            flash("Invalid Official ID or Password.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))

@app.route("/subjects", methods=["GET", "POST"])
def manage_subjects():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_subject":
            subject_code = request.form.get("subject_code", "").strip().upper()
            subject_name = request.form.get("subject_name", "").strip()
            department = request.form.get("department", "").strip()
            semester = request.form.get("semester")

            if not all([subject_code, subject_name, department, semester]):
                flash("Please fill all subject details.", "warning")
            else:
                try:
                    conn.execute("""
                        INSERT INTO subjects (subject_code, subject_name, department, semester)
                        VALUES (?, ?, ?, ?)
                    """, (subject_code, subject_name, department, int(semester)))
                    conn.commit()
                    flash(f"Subject '{subject_code}: {subject_name}' added successfully!", "success")
                except Exception as e:
                    conn.rollback()
                    flash(f"Error adding subject: {str(e)}", "danger")

        elif action == "add_unit":
            subject_id = request.form.get("subject_id")
            unit_number = request.form.get("unit_number")
            unit_name = request.form.get("unit_name", "").strip()

            if not all([subject_id, unit_number, unit_name]):
                flash("Please fill all unit details.", "warning")
            else:
                try:
                    conn.execute("""
                        INSERT INTO units (subject_id, unit_number, unit_name)
                        VALUES (?, ?, ?)
                    """, (int(subject_id), int(unit_number), unit_name))
                    conn.commit()
                    flash(f"Unit {unit_number} added successfully!", "success")
                except Exception as e:
                    conn.rollback()
                    flash(f"Error adding unit: {str(e)}", "danger")

    subjects_raw = conn.execute("SELECT * FROM subjects ORDER BY subject_code").fetchall()
    subjects_list = []
    for s in subjects_raw:
        s_dict = dict(s)
        units = conn.execute("SELECT * FROM units WHERE subject_id = ? ORDER BY unit_number", (s["subject_id"],)).fetchall()
        q_count = conn.execute("SELECT COUNT(*) as cnt FROM questions WHERE subject_id = ?", (s["subject_id"],)).fetchone()["cnt"]
        s_dict["units"] = [dict(u) for u in units]
        s_dict["question_count"] = q_count
        subjects_list.append(s_dict)

    conn.close()
    return render_template("manage_subjects.html", subjects=subjects_list)

@app.route("/faculty/my-questions")
def faculty_my_questions():
    if session.get("role") != "FACULTY":
        flash("Faculty login required.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    status_filter = request.args.get("status", "ALL")

    conn = get_db_connection()
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_submitted,
            SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved_count,
            SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_count
        FROM questions
        WHERE faculty_id = ?
    """, (user_id,)).fetchone()

    query = """
        SELECT q.*, s.subject_code, s.subject_name, u.unit_name, u.unit_number
        FROM questions q
        JOIN subjects s ON q.subject_id = s.subject_id
        JOIN units u ON q.unit_id = u.unit_id
        WHERE q.faculty_id = ?
    """
    params = [user_id]
    if status_filter != "ALL":
        query += " AND q.status = ?"
        params.append(status_filter)

    query += " ORDER BY q.created_at DESC"
    questions = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("faculty_my_questions.html", stats=stats, questions=questions, status_filter=status_filter)

@app.route("/faculty/add-question", methods=["GET", "POST"])
def faculty_add_question():
    if session.get("role") != "FACULTY":
        flash("Faculty login required.", "danger")
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        unit_id = request.form.get("unit_id")
        question_text = request.form.get("question_text", "").strip()
        marks = request.form.get("marks")
        difficulty = request.form.get("difficulty")
        blooms_level = request.form.get("blooms_level")
        faculty_id = session["user_id"]
        faculty_name = session.get("full_name", "Faculty")

        if not all([subject_id, unit_id, question_text, marks, difficulty, blooms_level]):
            flash("Please complete all required fields.", "warning")
        else:
            try:
                conn.execute("""
                    INSERT INTO questions (
                        subject_id, unit_id, faculty_id, faculty_name, question_text,
                        marks, difficulty, blooms_level, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """, (int(subject_id), int(unit_id), faculty_id, faculty_name, question_text, int(marks), difficulty, blooms_level))
                conn.commit()
                flash("Question submitted successfully! Now pending HOD verification.", "success")
                conn.close()
                return redirect(url_for("faculty_my_questions"))
            except Exception as e:
                conn.rollback()
                flash(f"Error submitting question: {str(e)}", "danger")

    subjects = conn.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    conn.close()
    return render_template("faculty_add_question.html", subjects=subjects)

@app.route("/hod/generate-paper", methods=["GET"])
def hod_generate_paper_page():
    if session.get("role") != "HOD":
        flash("HOD login required.", "danger")
        return redirect(url_for("login"))

    conn = get_db_connection()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    conn.close()
    return render_template("hod_generate_paper.html", subjects=subjects)

@app.route("/hod/question-bank")
def hod_question_bank():
    if session.get("role") != "HOD":
        flash("HOD login required.", "danger")
        return redirect(url_for("login"))

    subject_id = request.args.get("subject_id", "ALL")
    status = request.args.get("status", "ALL")

    conn = get_db_connection()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()

    counts = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected
        FROM questions
    """).fetchone()

    query = """
        SELECT q.*, s.subject_code, s.subject_name, u.unit_name, u.unit_number
        FROM questions q
        JOIN subjects s ON q.subject_id = s.subject_id
        JOIN units u ON q.unit_id = u.unit_id
        WHERE 1=1
    """
    params = []
    if subject_id != "ALL":
        query += " AND q.subject_id = ?"
        params.append(int(subject_id))
    if status != "ALL":
        query += " AND q.status = ?"
        params.append(status)

    query += " ORDER BY CASE WHEN q.status = 'PENDING' THEN 0 ELSE 1 END, q.created_at DESC"
    questions = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("hod_question_bank.html", questions=questions, subjects=subjects, subject_id=subject_id, status=status, counts=counts)

@app.route("/hod/approve-question/<int:question_id>", methods=["POST"])
def hod_approve_question(question_id):
    if session.get("role") != "HOD":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    hod_id = session["user_id"]
    conn = get_db_connection()
    try:
        conn.execute("UPDATE questions SET status = 'APPROVED', approved_by = ?, rejection_reason = NULL WHERE question_id = ?", (hod_id, question_id))
        conn.commit()
        conn.close()
        flash("Question approved successfully!", "success")
        return redirect(request.referrer or url_for("hod_question_bank"))
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("hod_question_bank"))

@app.route("/hod/reject-question/<int:question_id>", methods=["POST"])
def hod_reject_question(question_id):
    if session.get("role") != "HOD":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    reason = request.form.get("rejection_reason", "").strip() or "Question requires revision."
    hod_id = session["user_id"]
    conn = get_db_connection()
    try:
        conn.execute("UPDATE questions SET status = 'REJECTED', approved_by = ?, rejection_reason = ? WHERE question_id = ?", (hod_id, reason, question_id))
        conn.commit()
        conn.close()
        flash("Question rejected with feedback to faculty.", "warning")
        return redirect(request.referrer or url_for("hod_question_bank"))
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("hod_question_bank"))

@app.route("/hod/previous-papers")
def hod_previous_papers():
    if session.get("role") != "HOD":
        flash("HOD login required.", "danger")
        return redirect(url_for("login"))

    conn = get_db_connection()
    papers = conn.execute("""
        SELECT p.*, s.subject_code, s.subject_name,
               (SELECT COUNT(*) FROM paper_questions pq WHERE pq.paper_id = p.paper_id) as total_questions
        FROM generated_papers p
        JOIN subjects s ON p.subject_id = s.subject_id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("hod_previous_papers.html", papers=papers)

@app.route("/hod/download-paper/<int:paper_id>")
def download_paper(paper_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    paper = conn.execute("SELECT * FROM generated_papers WHERE paper_id = ?", (paper_id,)).fetchone()
    conn.close()

    if not paper or not paper["pdf_path"] or not os.path.exists(paper["pdf_path"]):
        flash("PDF file not found.", "danger")
        return redirect(url_for("hod_previous_papers"))

    return send_file(paper["pdf_path"], as_attachment=True, download_name=f"{paper['paper_title'].replace(' ', '_')}_{paper_id}.pdf")

@app.route("/hod/view-paper/<int:paper_id>")
def view_paper_detail(paper_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    paper = conn.execute("""
        SELECT p.*, s.subject_code, s.subject_name, s.department, p.generated_by_name as author_name
        FROM generated_papers p
        JOIN subjects s ON p.subject_id = s.subject_id
        WHERE p.paper_id = ?
    """, (paper_id,)).fetchone()

    if not paper:
        conn.close()
        flash("Paper not found.", "danger")
        return redirect(url_for("hod_previous_papers"))

    questions = conn.execute("""
        SELECT pq.section_name, pq.question_order, pq.marks,
               q.question_text, q.difficulty, q.blooms_level, u.unit_number, u.unit_name
        FROM paper_questions pq
        JOIN questions q ON pq.question_id = q.question_id
        JOIN units u ON q.unit_id = u.unit_id
        WHERE pq.paper_id = ?
        ORDER BY pq.section_name, pq.question_order
    """, (paper_id,)).fetchall()
    conn.close()

    grouped_sections = {}
    for q in questions:
        sec = q["section_name"]
        if sec not in grouped_sections:
            grouped_sections[sec] = []
        grouped_sections[sec].append(dict(q))

    return render_template("paper_print_view.html", paper=paper, sections=grouped_sections)

@app.route("/api/units/<int:subject_id>")
def api_get_units(subject_id):
    conn = get_db_connection()
    units = conn.execute("SELECT unit_id, unit_number, unit_name FROM units WHERE subject_id = ? ORDER BY unit_number", (subject_id,)).fetchall()
    conn.close()
    return jsonify({"units": [dict(u) for u in units]})

@app.route("/api/generate-preview", methods=["POST"])
def api_generate_preview():
    if session.get("role") != "HOD":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    payload = request.get_json() or {}
    subject_id = payload.get("subject_id")
    sections_config = payload.get("sections", [])
    target_difficulty = payload.get("difficulty", {})
    target_blooms = payload.get("blooms", {})

    if not subject_id or not sections_config:
        return jsonify({"success": False, "error": "Subject and section requirements are required."}), 400

    result = generate_question_paper(int(subject_id), sections_config, target_difficulty, target_blooms)
    return jsonify(result)

@app.route("/api/swap-question", methods=["POST"])
def api_swap_question():
    if session.get("role") != "HOD":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    payload = request.get_json() or {}
    subject_id = payload.get("subject_id")
    current_q_id = payload.get("question_id")
    excluded_ids = payload.get("excluded_ids", [])

    if not subject_id or not current_q_id:
        return jsonify({"success": False, "error": "Invalid request parameters"}), 400

    result = swap_alternative_question(int(subject_id), int(current_q_id), excluded_ids)
    return jsonify(result)

@app.route("/api/finalize-paper", methods=["POST"])
def api_finalize_paper():
    if session.get("role") != "HOD":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json() or {}
    subject_id = data.get("subject_id")
    paper_title = data.get("paper_title", "Semester Examination 2026")
    duration_minutes = int(data.get("duration_minutes", 180))
    semester = int(data.get("semester", 5))
    academic_year = data.get("academic_year", "2026-2027")
    sections = data.get("sections", [])
    total_marks = int(data.get("total_marks", 100))
    generated_by = session["user_id"]
    generated_by_name = session.get("full_name", "HOD")

    if not sections or not subject_id:
        return jsonify({"success": False, "error": "Invalid paper blueprint."}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")

        subj = conn.execute("SELECT subject_code, subject_name FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone()
        if not subj:
            raise ValueError("Subject not found.")

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generated_papers (
                paper_title, subject_id, exam_code, duration_minutes,
                total_marks, academic_year, semester, blueprint_json, generated_by, generated_by_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_title, subject_id, subj["subject_code"], duration_minutes,
            total_marks, academic_year, semester, json.dumps(sections), generated_by, generated_by_name
        ))
        paper_id = cursor.lastrowid

        q_order = 1
        for sec in sections:
            sec_name = sec.get("section_name", "Section")
            for q in sec.get("questions", []):
                qid = q["question_id"]
                q_marks = q["marks"]

                cursor.execute("""
                    INSERT INTO paper_questions (paper_id, question_id, section_name, question_order, marks)
                    VALUES (?, ?, ?, ?, ?)
                """, (paper_id, qid, sec_name, q_order, q_marks))

                cursor.execute("""
                    UPDATE questions
                    SET usage_count = usage_count + 1,
                        last_used_at = CURRENT_TIMESTAMP
                    WHERE question_id = ?
                """, (qid,))

                cursor.execute("""
                    INSERT INTO question_usage_audit (question_id, paper_id)
                    VALUES (?, ?)
                """, (qid, paper_id))

                q_order += 1

        pdf_filename = f"Paper_{paper_id}_{subj['subject_code']}_{paper_title.replace(' ', '_')[:25]}.pdf"
        output_filepath = os.path.join(PDF_STORAGE_DIR, pdf_filename)

        metadata = {
            "paper_title": paper_title,
            "subject_code": subj["subject_code"],
            "subject_name": subj["subject_name"],
            "duration_minutes": duration_minutes,
            "total_marks": total_marks
        }

        export_paper_to_pdf(metadata, sections, output_filepath)

        cursor.execute("UPDATE generated_papers SET pdf_path = ? WHERE paper_id = ?", (output_filepath, paper_id))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "paper_id": paper_id,
            "download_url": url_for("download_paper", paper_id=paper_id),
            "view_url": url_for("view_paper_detail", paper_id=paper_id)
        })

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
