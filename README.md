# Automated Question Paper Generator (OS & DBMS Powered)

An intelligent, balanced, and automated examination question paper generation system. Designed to replace manual paper setting with an algorithmic constraint solver adhering to **Bloom's Taxonomy**, **difficulty targets**, **unit/syllabus distribution**, and **question fatigue avoidance**.

Built with a strong focus on core **Operating Systems (OS)** and **Database Management Systems (DBMS)** concepts.

---

## 📚 1. Core Operating Systems (OS) Concepts Used

| OS Concept | Real-World Application in System | Implementation in Code |
| :--- | :--- | :--- |
| **Process Synchronization & Mutexes** | Prevents race conditions when concurrent faculties submit questions or HODs generate papers simultaneously. Avoids duplicate allocation of scarce question bank items. | [`os_concurrency.py`](os_concurrency.py) utilizes `threading.Lock()` (`generation_mutex`, `audit_log_mutex`) to guard critical sections. |
| **Atomic File System Operations** | Prevents corrupted/partial PDF downloads if a user requests a paper while it is still being compiled to disk. | Writes to a temporary file (`tempfile.mkstemp`), flushes OS kernel buffers with `os.fsync(fd)`, and executes an atomic replacement via `os.replace(temp, target)`. |
| **Multithreading & Worker Pools** | Asynchronous execution of intensive tasks (PDF compilation, bulk exports) without blocking the HTTP request/response cycle. | `concurrent.futures.ThreadPoolExecutor(max_workers=4)` handles non-blocking worker threads. |
| **Memory Management & Caching** | Minimizes repeated disk reads for static syllabi, course codes, and unit lists, mirroring Page Cache / TLB mechanisms. | Implements Least Recently Used (`@lru_cache(maxsize=32)`) in-memory cache eviction in [`os_concurrency.py`](os_concurrency.py). |
| **Deadlock Avoidance & Resource Ordering** | Prevents deadlock states when multiple resources (database connections, file locks, question pool locks) are acquired. | Strict lock-hierarchy ordering: Database connections are always acquired *inside* the synchronization mutex, preventing circular wait conditions. |

---

## 🗄️ 2. Core Database Management Systems (DBMS) Concepts Used

| DBMS Concept | Real-World Application in System | Implementation in Code |
| :--- | :--- | :--- |
| **Relational Normalization (3NF / BCNF)** | Prevents insertion, update, and deletion anomalies. Separates entities: `users`, `subjects`, `units`, `questions`, `generated_papers`, `paper_questions`, `question_usage_audit`. | Strict 3NF schema defined in [`db.py`](db.py). No transitive dependencies. |
| **ACID Transaction Management** | **Atomicity**: Paper generation either completely commits (paper inserted, question links created, usage counts incremented, audit logged) or rolls back entirely if any step fails.<br>**Consistency**: Ensures total marks match exactly.<br>**Isolation**: WAL mode ensures non-blocking readers.<br>**Durability**: Disk write-ahead logging guarantees persistence. | Handled in [`app.py`](app.py) (`api_finalize_paper`) using `conn.execute("BEGIN TRANSACTION")`, `conn.commit()`, and `conn.rollback()` on exceptions. |
| **B-Tree Indexing & Query Optimization** | Accelerates algorithmic question filtering by marks, subject, bloom's level, and approval status from $O(N)$ full table scans to $O(\log N)$ index seeks. | Composite index `idx_questions_filter ON questions(subject_id, status, marks, difficulty, blooms_level)` in [`db.py`](db.py). |
| **Referential Integrity & Constraints** | Enforces data validity at the database engine level rather than relying solely on application code. | `FOREIGN KEY ... ON DELETE CASCADE / RESTRICT`, `CHECK (marks > 0)`, `CHECK (difficulty IN ('Easy','Medium','Hard'))`, `CHECK (blooms_level IN (...))`. |
| **Database Views & Aggregations** | Provides instantaneous analytics of question distribution per subject, difficulty breakdown, and approval status without redundant calculations. | SQL View `view_subject_question_stats` defined in [`db.py`](db.py). |
| **Write-Ahead Logging (WAL)** | Enables high-concurrency read/write operations by maintaining a separate WAL log file, allowing simultaneous readers while a write occurs. | `PRAGMA journal_mode = WAL;` enabled on every connection in [`db.py`](db.py). |

---

## 🏛️ 3. Database Schema & Architecture

```
[ users ] (user_id PK, username, password_hash, role: 'FACULTY'|'HOD', department)
    │
    ├── 1:N ──> [ questions ] (question_id PK, subject_id FK, unit_id FK, faculty_id FK,
    │                           question_text, marks, difficulty, blooms_level,
    │                           status: 'PENDING'|'APPROVED'|'REJECTED',
    │                           usage_count, last_used_at, rejection_reason, approved_by FK)
    │                               │
    └── 1:N ──> [ generated_papers ]│(paper_id PK, subject_id FK, total_marks, duration,
                    │               │ pdf_path, blueprint_json, generated_by FK)
                    │               │
                    └─── M:N ───────┴──> [ paper_questions ] (id PK, paper_id FK, question_id FK,
                                                              section_name, question_order, marks)
                                              │
                                              └──> [ question_usage_audit ] (audit_id PK, question_id FK, paper_id FK, used_at)
```

---

## 👥 4. Role Features & Workflows

### 👨‍🏫 Faculty Portal:
1. **Secure Login**: Session-based authentication with role verification.
2. **Add Questions**:
   - Dynamic subject selection with AJAX unit loading.
   - Specify question statement, marks (2M, 5M, 10M, etc.), difficulty level (Easy, Medium, Hard).
   - Tag with **Bloom's Cognitive Level**:
     - *L1 Remember*: Recall facts and definitions.
     - *L2 Understand*: Explain concepts and ideas.
     - *L3 Apply*: Solve problems and implement solutions.
     - *L4 Analyze*: Compare, contrast, and deconstruct concepts.
     - *L5 Evaluate*: Justify choices and assess algorithms.
     - *L6 Create*: Design systems or synthesize architectures.
3. **Track Submissions ("My Questions")**:
   - Status indicators: `Approved` (emerald), `Pending Review` (amber), `Needs Revision` (rose).
   - Reviewer feedback notes displayed for rejected questions to facilitate revision.
   - Real-time usage counter showing how many times each question has been used in university examinations.

### 🧑‍💼 HOD Portal:
1. **Executive Dashboard**:
   - High-level KPIs: Total question bank size, pending reviews, generated papers count.
   - Live matrix of question pool depth per subject and difficulty spread.
2. **Question Bank Verification**:
   - Filter by course, status, Bloom's level, difficulty.
   - **One-click Approve**.
   - **Reject with Modal Feedback**: Provides actionable guidance back to faculty.
3. **Paper Generator Studio**:
   - Blueprint configuration: Custom sections (e.g., Part A: 5 $\times$ 2M = 10M; Part B: 4 $\times$ 5M = 20M; Part C: 2 $\times$ 10M = 20M = 50 Marks).
   - Algorithmic Solver:
     - Balances unit coverage across the entire syllabus.
     - Meets Bloom's taxonomy targets.
     - Minimizes question fatigue by prioritizing questions with lowest `usage_count` and oldest `last_used_at`.
   - **Interactive Live Preview**:
     - Visualizes Bloom's level coverage bars and unit distribution.
     - **Question Swap (Regeneration)**: Swap any single question on the fly with another approved question of equal marks.
4. **Finalize & Official PDF Export**:
   - Single atomic ACID transaction commit.
   - Generates university-standard PDF with institution header, course code, duration, maximum marks, instructions, and aligned questions table.
5. **Previous Papers Archive**:
   - Search, view printable versions, and re-download official PDFs anytime.
6. **Usage History & Question Fatigue Analysis**:
   - Visual breakdown of Fresh (0 uses), Once-used, and High-fatigue questions to guarantee academic examination security.

---

## 🚀 5. How to Run the Application

### 1. Requirements
- Python 3.10+
- Installed packages: `Flask`, `reportlab`, `pillow`, `werkzeug`

### 2. Quick Start
From the project folder:
```bash
cd "C:\Users\SUMEET PRASAD\.gemini\antigravity\scratch\auto_paper_generator"

# (Optional: Re-initialize and seed sample database)
python db.py

# Run the Automated Test Suite (Verifies all 6 OS/DBMS milestones)
python test_system.py

# Start the Web Application
python app.py
```

Open your browser at: **`http://127.0.0.1:5000`**

### 3. Demo Credentials
| Role | Username | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **HOD** | `hod` | `hod123` | Paper generator, question bank approval, previous papers archive |
| **Faculty (OS)** | `faculty1` | `fac123` | Submit Operating Systems questions, review feedback |
| **Faculty (DBMS)** | `faculty2` | `fac123` | Submit DBMS questions, track usage stats |
