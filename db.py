import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Separate database for HOD and Faculty user accounts and authentication details
AUTH_DB_PATH = os.path.join(BASE_DIR, "users_auth.db")

# Core database for Subjects, Units, Questions, and Examination Papers
CORE_DB_PATH = os.path.join(BASE_DIR, "question_paper_system.db")

def get_auth_db():
    """
    Connects to the separate Users & Authentication Database (users_auth.db).
    Used exclusively for user registration, credentials, roles, and profiles.
    """
    conn = sqlite3.connect(AUTH_DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def get_db_connection():
    """
    Connects to the Core Academic Database (question_paper_system.db).
    Used for subjects, syllabus units, question bank, and generated papers.
    """
    conn = sqlite3.connect(CORE_DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    """
    Initializes both databases with zero initial dummy records.
    All users, subjects, units, and questions are created dynamically by the user.
    """
    # 1. Initialize Users Auth Database
    auth_conn = get_auth_db()
    auth_cursor = auth_conn.cursor()
    auth_cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(120) NOT NULL,
        role VARCHAR(20) NOT NULL CHECK(role IN ('FACULTY', 'HOD')),
        department VARCHAR(120) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    auth_conn.commit()
    auth_conn.close()

    # 2. Initialize Core Academic Database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Subjects Table (Fully user-defined)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_code VARCHAR(30) UNIQUE NOT NULL,
        subject_name VARCHAR(120) NOT NULL,
        department VARCHAR(120) NOT NULL,
        semester INTEGER NOT NULL CHECK(semester BETWEEN 1 AND 8),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Units / Topics Table (User-defined per subject)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS units (
        unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        unit_number INTEGER NOT NULL,
        unit_name VARCHAR(150) NOT NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE CASCADE,
        UNIQUE (subject_id, unit_number)
    );
    """)

    # Questions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        question_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        unit_id INTEGER NOT NULL,
        faculty_id INTEGER NOT NULL,
        faculty_name VARCHAR(120) NOT NULL,
        question_text TEXT NOT NULL,
        marks INTEGER NOT NULL CHECK (marks > 0),
        difficulty VARCHAR(20) NOT NULL CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
        blooms_level VARCHAR(30) NOT NULL CHECK (blooms_level IN ('Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create')),
        status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
        rejection_reason TEXT,
        approved_by INTEGER,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE RESTRICT,
        FOREIGN KEY (unit_id) REFERENCES units(unit_id) ON DELETE RESTRICT
    );
    """)

    # Generated Papers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS generated_papers (
        paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_title VARCHAR(150) NOT NULL,
        subject_id INTEGER NOT NULL,
        exam_code VARCHAR(50),
        duration_minutes INTEGER NOT NULL DEFAULT 180,
        total_marks INTEGER NOT NULL CHECK (total_marks > 0),
        academic_year VARCHAR(30) NOT NULL DEFAULT '2026-2027',
        semester INTEGER NOT NULL,
        blueprint_json TEXT NOT NULL,
        pdf_path VARCHAR(255),
        generated_by INTEGER NOT NULL,
        generated_by_name VARCHAR(120) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE RESTRICT
    );
    """)

    # Paper Questions Junction Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paper_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        section_name VARCHAR(50) NOT NULL,
        question_order INTEGER NOT NULL,
        marks INTEGER NOT NULL,
        FOREIGN KEY (paper_id) REFERENCES generated_papers(paper_id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE RESTRICT
    );
    """)

    # Usage Audit Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_usage_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        paper_id INTEGER NOT NULL,
        used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
        FOREIGN KEY (paper_id) REFERENCES generated_papers(paper_id) ON DELETE CASCADE
    );
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_lookup ON questions(subject_id, status, marks);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_subject ON units(subject_id);")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Databases initialized with 0 records. Completely clean slate.")
