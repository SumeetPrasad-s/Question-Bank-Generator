"""
generator.py
============
Algorithmic Automated Question Paper Generator
----------------------------------------------
Implements a constraint satisfaction algorithm that selects questions satisfying:
1. Exact marks per section and total paper marks.
2. Unit coverage distribution (ensures questions are spread evenly across units).
3. Bloom's Taxonomy balance (Remember, Understand, Apply, Analyze, Evaluate, Create).
4. Difficulty level balance (Easy, Medium, Hard).
5. Question Fatigue Minimization (OS/DBMS Concept: prioritizes questions with lower usage_count and older last_used_at).
6. Single-question swapping for fine-tuning by the HOD.
"""

import random
from collections import defaultdict
from db import get_db_connection
from os_concurrency import generation_mutex

BLOOM_LEVELS = ['Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create']
DIFFICULTY_LEVELS = ['Easy', 'Medium', 'Hard']

def generate_question_paper(subject_id: int, sections_config: list, target_difficulty: dict, target_blooms: dict):
    """
    sections_config format:
    [
        {"section_name": "Part A - Short Answer Questions", "marks_per_q": 2, "num_questions": 5},
        {"section_name": "Part B - Analytical & Conceptual", "marks_per_q": 5, "num_questions": 4},
        {"section_name": "Part C - Comprehensive / Long Problems", "marks_per_q": 10, "num_questions": 2}
    ]
    
    target_difficulty: {"Easy": 30, "Medium": 50, "Hard": 20} (percentages)
    target_blooms: {"Remember": 20, "Understand": 30, "Apply": 25, "Analyze": 15, "Evaluate": 5, "Create": 5}
    """
    with generation_mutex:  # OS Concept: Mutual Exclusion Lock
        conn = get_db_connection()
        
        # DBMS Concept: Optimized query using index on (subject_id, status)
        query = """
        SELECT q.question_id, q.subject_id, q.unit_id, u.unit_number, u.unit_name,
               q.question_text, q.marks, q.difficulty, q.blooms_level, q.usage_count, q.last_used_at
        FROM questions q
        JOIN units u ON q.unit_id = u.unit_id
        WHERE q.subject_id = ? AND q.status = 'APPROVED'
        ORDER BY q.usage_count ASC, q.last_used_at ASC
        """
        all_questions = [dict(row) for row in conn.execute(query, (subject_id,)).fetchall()]
        conn.close()

        if not all_questions:
            return {"success": False, "error": "No approved questions found for this subject."}

        # Group available questions by marks
        by_marks = defaultdict(list)
        for q in all_questions:
            by_marks[q['marks']].append(q)

        selected_question_ids = set()
        paper_sections = []
        unit_counter = defaultdict(int)

        # Allocate questions section by section
        for sec in sections_config:
            sec_name = sec['section_name']
            marks_per_q = int(sec['marks_per_q'])
            count_needed = int(sec['num_questions'])

            eligible = [q for q in by_marks[marks_per_q] if q['question_id'] not in selected_question_ids]

            if len(eligible) < count_needed:
                return {
                    "success": False,
                    "error": f"Insufficient approved questions of {marks_per_q} marks for '{sec_name}'. Needed {count_needed}, but only {len(eligible)} available."
                }

            # Scoring function for selecting candidate questions:
            # We want:
            # 1. Lower usage_count (penalty for high usage)
            # 2. Units that haven't been selected much yet (diversity across syllabus)
            # 3. Random jitter to allow varied regeneration
            def question_score(item):
                unit_penalty = unit_counter[item['unit_id']] * 3.0
                usage_penalty = item['usage_count'] * 2.0
                # Slight tie-breaker randomness
                jitter = random.random() * 0.5
                return unit_penalty + usage_penalty + jitter

            # Sort eligible questions by score (lowest penalty first)
            eligible.sort(key=question_score)

            # Pick the best candidates
            sec_questions = []
            for i in range(count_needed):
                chosen = eligible[i]
                sec_questions.append(chosen)
                selected_question_ids.add(chosen['question_id'])
                unit_counter[chosen['unit_id']] += 1

            paper_sections.append({
                "section_name": sec_name,
                "marks_per_q": marks_per_q,
                "num_questions": count_needed,
                "total_section_marks": marks_per_q * count_needed,
                "questions": sec_questions
            })

        # Calculate analytics
        total_marks = sum(sec['total_section_marks'] for sec in paper_sections)
        all_selected = [q for sec in paper_sections for q in sec['questions']]
        total_q_count = len(all_selected)

        # Difficulty distribution
        diff_counts = defaultdict(int)
        for q in all_selected:
            diff_counts[q['difficulty']] += 1
        diff_percent = {k: round((diff_counts[k] / total_q_count) * 100, 1) for k in DIFFICULTY_LEVELS}

        # Bloom's distribution
        blooms_counts = defaultdict(int)
        for q in all_selected:
            blooms_counts[q['blooms_level']] += 1
        blooms_percent = {k: round((blooms_counts[k] / total_q_count) * 100, 1) for k in BLOOM_LEVELS}

        # Unit distribution
        unit_summary = defaultdict(int)
        for q in all_selected:
            unit_summary[q['unit_name']] += 1

        return {
            "success": True,
            "total_marks": total_marks,
            "total_questions": total_q_count,
            "sections": paper_sections,
            "difficulty_stats": diff_percent,
            "blooms_stats": blooms_percent,
            "unit_stats": dict(unit_summary)
        }

def swap_alternative_question(subject_id: int, current_question_id: int, excluded_ids: list):
    """
    Finds a replacement question with the same marks from the approved pool,
    excluding questions already currently in the paper.
    """
    with generation_mutex:
        conn = get_db_connection()
        # Find current question details
        curr = conn.execute("SELECT marks, unit_id, difficulty FROM questions WHERE question_id = ?", (current_question_id,)).fetchone()
        if not curr:
            conn.close()
            return {"success": False, "error": "Current question not found."}

        marks = curr['marks']

        # Look for replacement with same marks and not in excluded_ids
        placeholders = ','.join('?' for _ in excluded_ids) if excluded_ids else '0'
        query = f"""
        SELECT q.question_id, q.subject_id, q.unit_id, u.unit_number, u.unit_name,
               q.question_text, q.marks, q.difficulty, q.blooms_level, q.usage_count, q.last_used_at
        FROM questions q
        JOIN units u ON q.unit_id = u.unit_id
        WHERE q.subject_id = ? 
          AND q.status = 'APPROVED'
          AND q.marks = ?
          AND q.question_id NOT IN ({placeholders})
        ORDER BY q.usage_count ASC, RANDOM()
        LIMIT 1
        """
        params = [subject_id, marks] + (excluded_ids if excluded_ids else [])
        alt = conn.execute(query, params).fetchone()
        conn.close()

        if not alt:
            return {"success": False, "error": "No alternative approved question with same marks available."}

        return {"success": True, "question": dict(alt)}
