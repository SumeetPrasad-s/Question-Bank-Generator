"""
os_concurrency.py
=================
Operating System (OS) Concepts Implementation Module
---------------------------------------------------
This module demonstrates core OS concepts integrated into the Automated Question Paper Generator:

1. Process Synchronization & Mutual Exclusion (Mutex Locks):
   - Protects critical sections during question bank selection and paper generation.
   - Prevents race conditions when multiple faculties submit questions or HODs generate papers concurrently.

2. Atomic File I/O Operations:
   - Safe file writes using temporary files, OS buffer flushing (os.fsync), and atomic file replacement (os.replace).
   - Eliminates partial-file read anomalies (Dirty Reads in File System).

3. Thread Pool Management:
   - Background worker pool for PDF generation and asynchronous compilation.

4. Caching & Memory Management:
   - Least Recently Used (LRU) cache emulation to avoid redundant disk I/O for frequently queried subjects/units.
"""

import os
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# OS Concept 1: Mutex Lock for Critical Section Protection
# Ensures only one generation process can access and allocate the question pool at a time,
# preventing race conditions on question usage counts.
generation_mutex = threading.Lock()
audit_log_mutex = threading.Lock()

# OS Concept 2: Thread Pool Executor (Process/Thread Management)
# Handles asynchronous PDF generation without blocking the main web server process.
pdf_worker_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="PDFGeneratorWorker")

def atomic_write_file(target_path: str, data_bytes: bytes) -> str:
    """
    OS Concept: Atomic File System Write.
    Steps:
      1. Create a temporary file in the same directory (or system temp).
      2. Write data to temporary file.
      3. Call os.fsync to force flushing file system buffers from RAM to Disk.
      4. Atomically rename/replace the temporary file to target_path using os.replace().
    This guarantees that concurrent readers never encounter a partially written or corrupted PDF.
    """
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    
    # Create temp file in same directory to guarantee same filesystem partition (necessary for atomic rename)
    temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix="tmp_paper_", suffix=".pdf")
    try:
        with open(temp_fd, 'wb') as f:
            f.write(data_bytes)
            f.flush()
            os.fsync(f.fileno())  # OS Concept: Sync kernel I/O cache to physical disk
        # Atomic rename (POSIX & Windows atomic swap)
        os.replace(temp_path, target_path)
        return target_path
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise e

# OS Concept 4: Memory Management - In-Memory Cache with LRU Eviction
@lru_cache(maxsize=32)
def get_cached_subject_metadata(subject_id: int):
    """
    Simulates cache retrieval for subject metadata to avoid repetitive disk access.
    In an OS, this mirrors the Page Cache / Translation Lookaside Buffer concept.
    """
    from db import get_db_connection
    conn = get_db_connection()
    subject = conn.execute("SELECT * FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone()
    units = conn.execute("SELECT * FROM units WHERE subject_id = ? ORDER BY unit_number", (subject_id,)).fetchall()
    conn.close()
    return dict(subject) if subject else None, [dict(u) for u in units]

def invalidate_subject_cache():
    """Clear memory cache when schema or subjects update."""
    get_cached_subject_metadata.cache_clear()
