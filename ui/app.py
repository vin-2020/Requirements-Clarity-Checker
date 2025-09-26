# ui/app.py
import streamlit as st
import sys
import os
import re
import docx
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd
import inspect
import importlib
import sqlite3  # <-- added to catch IntegrityError

# Make local packages importable when run from /ui
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ------------------------- Imports from your app -------------------------
# Analyzer functions (some may not exist in older versions; we shim below)
from core.analyzer import (
    check_requirement_ambiguity,
    check_passive_voice,
    check_incompleteness,
)
try:
    from core.analyzer import check_singularity  # optional
except Exception:
    def check_singularity(_text: str):
        return []  # safe fallback

# Scoring (signature may be old or new; we handle both)
from core.scoring import calculate_clarity_score

# Optional rule engine (new); fall back to a dummy if missing
try:
    from core.rule_engine import RuleEngine
except Exception:
    class RuleEngine:
        """Minimal stub to keep the app running if core.rule_engine is absent."""
        def __init__(self):
            pass

# LLM helpers (robust, reloadable)
import importlib
from llm import ai_suggestions as ai  # module import

ai = importlib.reload(ai)  # ensure latest functions are picked up

# Core helpers (these should exist)
get_ai_suggestion = getattr(ai, "get_ai_suggestion")
generate_requirement_from_need = getattr(ai, "generate_requirement_from_need")

# Optional helpers with safe fallbacks
get_chatbot_response = getattr(
    ai, "get_chatbot_response",
    lambda api_key, history: get_ai_suggestion(api_key, "\n".join(
        f"{m.get('role','user').upper()}: { (m.get('parts') or [m.get('content','')])[0] }"
        for m in history
    ) + "\nASSISTANT:")
)

# New decomposition helper (now actually defined in ai_suggestions.py)
decompose_requirement_with_ai = getattr(
    ai, "decompose_requirement_with_ai",
    lambda api_key, requirement_text: "Decomposition helper failed to load."
)



# --- NEW (safe import for AI extractor) ---
try:
    from llm.ai_suggestions import extract_requirements_with_ai
    HAS_AI_PARSER = True
except Exception:
    HAS_AI_PARSER = False
    def extract_requirements_with_ai(*args, **kwargs):
        return []  # fallback

# Database helpers  (DB memory integration)
from db.database import init_db, add_project, get_all_projects  # type: ignore
from db import database as db  # type: ignore  # <-- module import avoids name errors
db = importlib.reload(db)  # ensure latest functions (add_document, etc.) are present

# ========================= Helpers for Analyzer =========================

def _read_docx_text_and_rows(uploaded_file):
    """
    Returns (flat_text, table_rows) where:
      - flat_text is all paragraph + cell text joined with newlines
      - table_rows is a list of rows (each row = list[str] of cell texts)
    """
    d = docx.Document(uploaded_file)
    parts = []

    # paragraphs
    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)

    # tables
    rows = []
    for tbl in d.tables:
        for r in tbl.rows:
            row_cells = []
            for c in r.cells:
                cell_text = " ".join(p.text.strip() for p in c.paragraphs if p.text.strip())
                row_cells.append(cell_text)
                if cell_text:
                    parts.append(cell_text)
            rows.append(row_cells)

    flat_text = "\n".join(parts)
    return flat_text, rows

def _extract_requirements_from_table_rows(table_rows):
    """
    If the DOCX has a requirements table with headers like:
      ID | Requirement | Rationale | Verification | Acceptance Criteria
    this will harvest (id, text) pairs robustly.
    """
    if not table_rows:
        return []

    def _norm(s): return (s or "").strip().lower()

    # Find a header row
    header_idx = None
    for i, row in enumerate(table_rows):
        cells = [_norm(c) for c in row]
        if not cells:
            continue
        if ("id" in cells[0] and any("requirement" in c for c in cells)):
            header_idx = i
            break
        if ("requirement" in cells[0] and any(c == "id" for c in cells)):
            header_idx = i
            break

    if header_idx is None:
        return []

    # Map columns
    header = [_norm(c) for c in table_rows[header_idx]]
    id_col = None
    req_col = None
    for idx, h in enumerate(header):
        if h == "id":
            id_col = idx
        if "requirement" in h:
            req_col = idx
    if id_col is None or req_col is None:
        return []

    # IDs like SAT-REQ-001, ABC-123, SUBSYS-THERM-42
    id_pat = re.compile(r'^[A-Z][A-Z0-9-]*-\d+$')

    out = []
    for row in table_rows[header_idx + 1:]:
        if len(row) <= max(id_col, req_col):
            continue
        rid = (row[id_col] or "").strip()
        rtx = (row[req_col] or "").strip()
        if not rid or not rtx:
            continue
        if id_pat.match(rid):
            out.append((rid, rtx))
    return out

def extract_requirements_from_string(content: str):
    """Extract (id, text) pairs like 'SAT-REQ-001 ...' or '1.' lines."""
    requirements = []
    # IDs like ABC-1, ABC-REQ-001, SUBSYS-THERM-42 or numbered "1."
    req_pattern = re.compile(r'^(([A-Z][A-Z0-9-]*-\d+)|(\d+\.))\s+(.*)$')
    for line in content.split('\n'):
        line = line.strip()
        m = req_pattern.match(line)
        if m:
            rid = m.group(1)
            text = m.group(4)
            requirements.append((rid, text))
    return requirements

def extract_requirements_from_file(uploaded_file):
    """Read .txt/.docx to text, then parse requirements."""
    if uploaded_file.name.endswith('.txt'):
        content = uploaded_file.getvalue().decode("utf-8")
        table_rows = []
    elif uploaded_file.name.endswith('.docx'):
        content, table_rows = _read_docx_text_and_rows(uploaded_file)
    else:
        content, table_rows = "", []

    # Try table-aware extraction first (handles 'ID | Requirement | ...' tables)
    reqs = _extract_requirements_from_table_rows(table_rows)
    if reqs:
        return reqs

    # Fallback to line regex on flattened text
    return extract_requirements_from_string(content)

def format_requirement_with_highlights(req_id, req_text, issues):
    """Inline HTML highlight for ambiguous/passive elements."""
    highlighted_text = req_text
    if issues.get('ambiguous'):
        for word in issues['ambiguous']:
            highlighted_text = re.sub(
                r'\b' + re.escape(word) + r'\b',
                f'<span style="background-color:#FFFF00;color:black;padding:2px 4px;border-radius:3px;">{word}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )
    if issues.get('passive'):
        for phrase in issues['passive']:
            highlighted_text = re.sub(
                re.escape(phrase),
                f'<span style="background-color:#FFA500;padding:2px 4px;border-radius:3px;">{phrase}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )

    display_html = f"⚠️ <strong>{req_id}</strong> {highlighted_text}"
    explanations = []
    if issues.get('ambiguous'):
        explanations.append(f"<i>- Ambiguity: Found weak words: <b>{', '.join(issues['ambiguous'])}</b></i>")
    if issues.get('passive'):
        explanations.append(f"<i>- Passive Voice: Found phrase: <b>'{', '.join(issues['passive'])}'</b>. Consider active voice.</i>")
    if issues.get('incomplete'):
        explanations.append("<i>- Incompleteness: Requirement appears to be a fragment.</i>")
    if issues.get('singularity'):
        explanations.append(f"<i>- Singularity: Multiple actions indicated: <b>{', '.join(issues['singularity'])}</b></i>")
    if explanations:
        display_html += "<br>" + "<br>".join(explanations)

    return (
        f'<div style="background-color:#FFF3CD;color:#856404;padding:10px;'
        f'border-radius:5px;margin-bottom:10px;">{display_html}</div>'
    )

def safe_call_ambiguity(text: str, engine: RuleEngine | None):
    """Call check_requirement_ambiguity with or without rule engine, depending on its signature."""
    try:
        # Try (text, engine)
        return check_requirement_ambiguity(text, engine)
    except TypeError:
        # Fallback to (text)
        return check_requirement_ambiguity(text)

def safe_clarity_score(total_reqs: int, results: list[dict], issue_counts=None, engine: RuleEngine | None = None):
    """
    Call calculate_clarity_score supporting both signatures:
    - New: calculate_clarity_score(total_reqs, issue_counts, rule_engine)
    - Old: calculate_clarity_score(total_reqs, flagged_reqs)
    """
    try:
        sig = inspect.signature(calculate_clarity_score)
        if len(sig.parameters) >= 3:
            # New signature expects issue_counts + engine
            return calculate_clarity_score(total_reqs, issue_counts or {}, engine)
        else:
            # Old signature: compute flagged_reqs
            flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
            return calculate_clarity_score(total_reqs, flagged_reqs)
    except Exception:
        # Ultimate fallback: basic percent clear
        flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
        clear_reqs = max(0, total_reqs - flagged_reqs)
        return int((clear_reqs / total_reqs) * 100) if total_reqs else 100
def _open_db_conn():
    """
    Open a connection to the SAME SQLite DB the db module is using.
    Tries, in order:
      - db.get_connection() (reuse existing connection)
      - db.DB_PATH / DB_FILE / DB_NAME / DATABASE_PATH (string path)
      - common filenames next to db module: reqcheck.db, database.db, app.db
    """
    # 1) Reuse existing connection if the module exposes it.
    if hasattr(db, "get_connection"):
        try:
            conn = db.get_connection()
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn, False  # do not close (owned by db module)
        except Exception:
            pass

    # 2) Known path attributes on the module.
    for attr in ("DB_PATH", "DB_FILE", "DB_NAME", "DATABASE_PATH"):
        path = getattr(db, attr, None)
        if isinstance(path, str) and path:
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn, True

    # 3) Try common filenames in the db package directory.
    base_dir = os.path.dirname(db.__file__)
    for name in ("reqcheck.db", "database.db", "app.db"):
        candidate = os.path.join(base_dir, name)
        if os.path.exists(candidate):
            conn = sqlite3.connect(candidate)
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn, True

    raise RuntimeError(
        "Could not locate the SQLite DB file. "
        "Expose DB_PATH in db.database or provide db.get_connection()."
    )

# =============================== UI Setup ===============================

st.set_page_config(
    page_title="ReqCheck Workspace",
    page_icon="https://github.com/vin-2020/Requirements-Clarity-Checker/blob/main/Logo.png?raw=true",
    layout="wide"
)

# Global CSS
st.markdown("""
<style>
    .req-container { padding:10px;border-radius:5px;margin-bottom:10px;border:1px solid #ddd; }
    .flagged { background:#FFF3CD;color:#856404;border-color:#FFEEBA; }
    .clear { background:#D4EDDA;color:#155724;border-color:#C3E6CB; }
    .highlight-ambiguity { background:#FFFF00;color:black;padding:2px 4px;border-radius:3px; }
    .highlight-passive { background:#FFA500;padding:2px 4px;border-radius:3px; }
    .explanation { font-size:0.9em;font-style:italic;color:#6c757d;margin-top:5px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://github.com/vin-2020/Requirements-Clarity-Checker/blob/main/ReqCheck_Logo.png?raw=true", use_container_width=True)
    st.header("About ReqCheck")
    st.info("An AI-assisted tool to evaluate the quality of system requirements...")
    st.header("Project Links")
    st.markdown("[GitHub Repository](https://github.com/vin-2020/Requirements-Clarity-Checker)")
    st.markdown("[INCOSE Handbook](https://www.incose.org/products-and-publications/se-handbook)")

st.title("✨ ReqCheck: AI-Powered Requirements Assistant")

# ✅ Initialize the database on first run (DB memory)
init_db()

# Single API key stored globally
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
api_key_input = st.text_input(
    "Enter your Google AI API Key to enable AI features:",
    type="password",
    value=st.session_state.api_key,
    key="api_key_global"
)
if api_key_input:
    st.session_state.api_key = api_key_input

# Track selected project globally
if 'selected_project' not in st.session_state:
    st.session_state.selected_project = None
st.markdown("Get your free API key from [Google AI Studio](https://aistudio.google.com/).")
# One RuleEngine instance (real or stub)
rule_engine = RuleEngine()

# ======================= Layout: main + right panel =======================
main_col, right_col = st.columns([4, 1], gap="large")

# ----------------------------- Right Panel (Projects) -----------------------------
with right_col:
    st.subheader("🗂️ Projects")

    # Current selection info + clear
    if st.session_state.selected_project is not None:
        _pid, _pname = st.session_state.selected_project
        st.caption(f"Current: **{_pname}**")
        if st.button("Clear selection", key="btn_clear_proj_right"):
            st.session_state.selected_project = None
            st.rerun()

    # Load existing projects
    projects = get_all_projects()
    names = [p[1] for p in projects] if projects else []
    if names:
        sel_name = st.selectbox("Open project:", names, key="proj_select_right")

        # --- Confirmation state (add these 3 keys once) ---
        if "confirm_delete" not in st.session_state:
            st.session_state.confirm_delete = False
        if "delete_project_id" not in st.session_state:
            st.session_state.delete_project_id = None
        if "delete_project_name" not in st.session_state:
            st.session_state.delete_project_name = None

        # Load / Delete buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Load", key="btn_load_proj_right"):
                for p in projects:
                    if p[1] == sel_name:
                        st.session_state.selected_project = p
                        st.success(f"Loaded: {sel_name}")
                        st.rerun()

        with col2:
            if st.button("Delete", key="btn_delete_proj_right"):
                # Store selection and show confirmation UI on next rerun
                for p in projects:
                    if p[1] == sel_name:
                        st.session_state.delete_project_id = p[0]
                        st.session_state.delete_project_name = sel_name
                        st.session_state.confirm_delete = True

        # Render confirmation UI (persists across reruns)
        if st.session_state.confirm_delete:
            st.warning(
                f"You're about to delete '{st.session_state.delete_project_name}'. "
                "This cannot be undone."
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirm Delete", key="btn_confirm_delete_proj_right"):
                    # === ROBUST RAW-SQL CASCADE DELETE (ONLY THIS BLOCK CHANGED) ===
                    pid_to_delete = st.session_state.delete_project_id

                    def _get_tables(conn):
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                        return [r[0] for r in cur.fetchall()]

                    def _fk_refs(conn, ref_table_name):
                        """
                        Return list of (table, from_col) pairs for all tables that have a FK to ref_table_name.
                        """
                        refs = []
                        for t in _get_tables(conn):
                            try:
                                cur = conn.cursor()
                                cur.execute(f"PRAGMA foreign_key_list('{t}')")
                                for (id_, seq, table, from_col, to_col, on_update, on_delete, match) in cur.fetchall():
                                    if table == ref_table_name:
                                        refs.append((t, from_col))
                            except Exception:
                                pass
                        return refs

                    try:
                        conn, _should_close = _open_db_conn()
                        cur = conn.cursor()
                        cur.execute("PRAGMA foreign_keys = ON;")

                        # 1) Gather document ids for the project
                        cur.execute("SELECT id FROM documents WHERE project_id = ?", (pid_to_delete,))
                        doc_ids = [r[0] for r in cur.fetchall()]

                        if doc_ids:
                            # 2) Delete ALL rows in ANY table that references 'documents'
                            refs_to_documents = _fk_refs(conn, "documents")
                            for (tbl, col) in refs_to_documents:
                                qmarks = ",".join("?" for _ in doc_ids)
                                cur.execute(f"DELETE FROM {tbl} WHERE {col} IN ({qmarks})", doc_ids)

                            # 3) Now delete requirements explicitly, then documents  <<< CHANGED PART
                            qmarks = ",".join("?" for _ in doc_ids)
                            try:
                                cur.execute(f"DELETE FROM requirements WHERE document_id IN ({qmarks})", doc_ids)
                            except Exception:
                                pass
                            cur.execute(f"DELETE FROM documents WHERE id IN ({qmarks})", doc_ids)

                        # 4) Delete ALL rows in ANY table that references 'projects'
                        refs_to_projects = _fk_refs(conn, "projects")
                        for (tbl, col) in refs_to_projects:
                            cur.execute(f"DELETE FROM {tbl} WHERE {col} = ?", (pid_to_delete,))

                        # 5) Finally delete the project
                        cur.execute("DELETE FROM projects WHERE id = ?", (pid_to_delete,))
                        conn.commit()
                        if _should_close:
                            conn.close()

                        st.success("Project deleted.")

                    except sqlite3.IntegrityError as e:
                        # Extra diagnostics to show what blocked the delete
                        try:
                            cur.execute("PRAGMA foreign_key_check;")
                            problems = cur.fetchall()
                        except Exception:
                            problems = []
                        if problems:
                            st.error(f"Delete failed due to FK constraints. Offending rows: {problems}")
                        else:
                            st.error(f"Delete failed due to foreign key constraints: {e}")
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

                    # clear state regardless
                    st.session_state.confirm_delete = False
                    st.session_state.delete_project_id = None
                    st.session_state.delete_project_name = None
                    st.rerun()

            with c2:
                if st.button("Cancel", key="btn_cancel_delete_proj_right"):
                    st.session_state.confirm_delete = False
                    st.session_state.delete_project_id = None
                    st.session_state.delete_project_name = None

    else:
        st.caption("No projects yet.")

    # Create new
    st.text_input("New project name:", key="new_proj_name_right")
    if st.button("Create", key="btn_create_proj_right"):
        new_name = st.session_state.get("new_proj_name_right", "").strip()
        if new_name:
            feedback = add_project(new_name)
            st.success(feedback)
            st.rerun()
        else:
            st.error("Please enter a project name.")

# ------------------------------ Main Tabs ------------------------------
with main_col:
    tab_analyze, tab_need, tab_chat = st.tabs([
        "📄 Document Analyzer",
        "💡 Need-to-Requirement Helper",
        "💬 Requirements Chatbot",
    ])

# ------------------------------ Tab: Analyzer (Unified) ------------------------------
with tab_analyze:
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    if st.session_state.selected_project is None:
        st.header("Analyze a Requirements Document")
        st.warning("You can analyze documents without a project, but results won’t be saved.")
    else:
        project_name = st.session_state.selected_project[1]
        st.header(f"Analyze & Add Documents to: {project_name}")


    # --- NEW: toggle for AI parser (before uploader) ---
    use_ai_parser = st.toggle("Use Advanced AI Parser (requires API key)")
    if use_ai_parser and not (HAS_AI_PARSER and st.session_state.api_key):
        st.info("AI Parser not available (missing function or API key). Falling back to Standard Parser.")

    # Current project (if any)
    project_id = st.session_state.selected_project[0] if st.session_state.selected_project else None

    # One uploader for multiple documents
    uploaded_files = st.file_uploader(
        "Upload one or more requirements documents (.txt or .docx)",
        type=['txt', 'docx'],
        accept_multiple_files=True,
        key=f"uploader_unified_{project_id or 'none'}",  
    )

    # Optional example
    example_files = {
        "Choose an example...": None,
        "Drone System SRS (Complex Example)": "DRONE_SRS_v1.0.docx",
    }
    selected_example = st.selectbox(
        "Or, select an example to analyze:",
        options=list(example_files.keys()),
        key="example_unified",
    )

    # Build a queue of docs to process: (source_type, display_name, payload)
    # - source_type == "upload"  -> payload is an UploadedFile
    # - source_type == "example" -> payload is raw text
    docs_to_process = []

    if uploaded_files:
        for up in uploaded_files:
            docs_to_process.append(("upload", up.name, up))

    if selected_example != "Choose an example...":
        example_path = example_files[selected_example]
        try:
            if example_path.endswith(".docx"):
                d = docx.Document(example_path)
                example_text = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
            else:
                with open(example_path, "r", encoding="utf-8") as f:
                    example_text = f.read()
            docs_to_process.append(("example", selected_example, example_text))
        except FileNotFoundError:
            st.error(f"Example file not found: {example_path}. Place it in the project folder.")

    if docs_to_process:
        with st.spinner("Processing and analyzing documents..."):
            saved_count = 0
            all_export_rows = []  # NEW: collect all rows across documents for a combined CSV

            for src_type, display_name, payload in docs_to_process:
                # --- Extract requirements (AI or standard) ---
                if src_type == "upload":
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        # Read raw text for AI
                        if payload.name.endswith(".txt"):
                            raw = payload.getvalue().decode("utf-8", errors="ignore")
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                            # ---- Fallback if AI found nothing (txt) ----
                            if not reqs and raw:
                                reqs = extract_requirements_from_string(raw)
                        elif payload.name.endswith(".docx"):
                            # Read paragraphs + tables
                            flat_text, table_rows = _read_docx_text_and_rows(payload)

                            # Prefer deterministic table extraction if a requirements table exists
                            table_reqs = _extract_requirements_from_table_rows(table_rows)
                            if table_reqs:
                                reqs = table_reqs
                                raw = None  # not used
                            else:
                                raw = flat_text
                                reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                                # ---- Fallback if AI found nothing (docx, no table) ----
                                if not reqs and raw:
                                    reqs = extract_requirements_from_string(raw)
                        else:
                            raw = ""
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                    else:
                        reqs = extract_requirements_from_file(payload)
                else:
                    # example text payload is already a string
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        reqs = extract_requirements_with_ai(st.session_state.api_key, payload)
                    else:
                        reqs = extract_requirements_from_string(payload)

                total_reqs = len(reqs)
                if total_reqs == 0:
                    st.warning(f"⚠️ No recognizable requirements in **{display_name}**.")
                    continue

                # --- Analyze requirements (re-using your checks) ---
                results = []
                issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0, "Singularity": 0}

                for rid, rtext in reqs:
                    ambiguous = safe_call_ambiguity(rtext, rule_engine)
                    passive = check_passive_voice(rtext)
                    incomplete = check_incompleteness(rtext)
                    try:
                        singular = check_singularity(rtext)
                    except Exception:
                        singular = []

                    if ambiguous:
                        issue_counts["Ambiguity"] += 1
                    if passive:
                        issue_counts["Passive Voice"] += 1
                    if incomplete:
                        issue_counts["Incompleteness"] += 1
                    if singular:
                        issue_counts["Singularity"] += 1

                    results.append({
                        "id": rid,
                        "text": rtext,
                        "ambiguous": ambiguous,
                        "passive": passive,
                        "incomplete": incomplete,
                        "singularity": singular,
                    })

                # --- Scoring: simple percent clear ---
                flagged_total = sum(
                    1 for r in results
                    if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                )
                clarity_score = int(((total_reqs - flagged_total) / total_reqs) * 100) if total_reqs else 100

                # --- Save to DB if helpers exist and a project is selected ---
                if project_id is not None:
                    try:
                        # Prefer new helpers if available
                        if hasattr(db, "add_document") and hasattr(db, "add_requirements") and hasattr(db, "get_documents_for_project"):
                            existing = []
                            try:
                                existing = [d for d in db.get_documents_for_project(project_id) if d[1] == display_name]
                            except Exception:
                                existing = []
                            next_version = (max([d[2] for d in existing], default=0) + 1)
                            doc_id = db.add_document(project_id, display_name, next_version, clarity_score)
                            db.add_requirements(doc_id, reqs)
                            saved_count += 1
                        # Fallback to legacy helpers
                        elif hasattr(db, "add_document_to_project") and hasattr(db, "add_requirements_to_document"):
                            doc_id = db.add_document_to_project(project_id, display_name, clarity_score)
                            db.add_requirements_to_document(doc_id, reqs)
                            saved_count += 1
                        else:
                            st.info("Analysis done — DB helpers not found, so nothing was saved.")
                    except Exception as e:
                        st.warning(f"Saved analysis for **{display_name}**, but DB write failed: {e}")

                # --- Per-document results UI ---
                with st.expander(f"📄 {display_name} — Clarity {clarity_score}/100 • {total_reqs} requirements"):
                    flagged_total = sum(
                        1 for r in results
                        if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                    )
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Requirements", total_reqs)
                    c2.metric("Flagged", flagged_total)
                    c3.metric("Clarity Score", f"{clarity_score} / 100")
                    st.progress(clarity_score)  # if your Streamlit expects 0..1, use clarity_score/100

                    # --- Export CSV for this single document ---
                    export_rows = []
                    for r in results:
                        issues = []
                        if r["ambiguous"]:
                            issues.append(f"Ambiguity: {', '.join(r['ambiguous'])}")
                        if r["passive"]:
                            issues.append(f"Passive Voice: {', '.join(r['passive'])}")
                        if r["incomplete"]:
                            issues.append("Incompleteness")
                        if r["singularity"]:
                            issues.append(f"Singularity: {', '.join(r['singularity'])}")

                        export_rows.append({
                            "Document": display_name,
                            "Requirement ID": r["id"],
                            "Requirement Text": r["text"],
                            "Status": "Clear" if not issues else "Flagged",
                            "Issues Found": "; ".join(issues),
                        })

                    # Download for this single document
                    df_doc = pd.DataFrame(export_rows)
                    csv_doc = df_doc.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"Download '{display_name}' Analysis (CSV)",
                        data=csv_doc,
                        file_name=f"{os.path.splitext(display_name)[0]}_ReqCheck_Report.csv",
                        mime="text/csv",
                        key=f"dl_csv_{display_name}",
                    )

                    # Accumulate into "all documents" export
                    all_export_rows.extend(export_rows)  # NEW

                    st.subheader("Issues by Type")
                    st.bar_chart(issue_counts)

                    # Word cloud of ambiguous terms
                    all_ambiguous_words = []
                    for r in results:
                        if r["ambiguous"]:
                            all_ambiguous_words.extend(r["ambiguous"])
                    with st.expander("Common Weak Words (Word Cloud)"):
                        if all_ambiguous_words:
                            text_for_cloud = " ".join(all_ambiguous_words)
                            wordcloud = WordCloud(
                                width=800, height=300, background_color="white", collocations=False
                            ).generate(text_for_cloud)
                            fig, ax = plt.subplots()
                            ax.imshow(wordcloud, interpolation="bilinear")
                            ax.axis("off")
                            st.pyplot(fig)
                        else:
                            st.write("No ambiguous words found.")

                    st.subheader("Detailed Analysis")
                    for r in results:
                        is_flagged = r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                        if is_flagged:
                            with st.container(border=True):
                                st.markdown(
                                    format_requirement_with_highlights(r["id"], r["text"], r),
                                    unsafe_allow_html=True,
                                )
                                if r["ambiguous"]:
                                    st.caption(f"ⓘ **Ambiguity:** {', '.join(r['ambiguous'])}")
                                if r["passive"]:
                                    st.caption(f"ⓘ **Passive Voice:** {', '.join(r['passive'])}")
                                if r["incomplete"]:
                                    st.caption("ⓘ **Incompleteness** detected.")
                                if r["singularity"]:
                                    st.caption(f"ⓘ **Singularity:** {', '.join(r['singularity'])}")

                                # Optional AI rewrite / decompose (uses your existing helper & API key)
                                with st.expander("✨ Get AI Rewrite / Decomposition"):
                                    if not st.session_state.api_key:
                                        st.warning("Please enter your Google AI API Key.")
                                    else:
                                        # Buttons row: always show Rewrite; show Decompose only if singularity present
                                        if r["singularity"]:
                                            col1, col2 = st.columns(2)
                                        else:
                                            col1 = st.columns(1)[0]

                                        with col1:
                                            if st.button(f"Rewrite Requirement {r['id']}", key=f"rewrite_{r['id']}"):
                                                with st.spinner("AI is thinking..."):
                                                    suggestion = get_ai_suggestion(st.session_state.api_key, r['text'])
                                                st.info("AI Suggestion (Rewrite):")
                                                st.markdown(f"> {suggestion}")

                                        if r["singularity"]:
                                            with col2:
                                                if st.button(f"Decompose Requirement {r['id']}", key=f"decompose_{r['id']}"):
                                                    with st.spinner("AI is decomposing..."):
                                                        decomposed_reqs = decompose_requirement_with_ai(
                                                            st.session_state.api_key,
                                                            f"{r['id']} {r['text']}"
                                                        )
                                                    st.info("AI Suggestion (Decomposition):")
                                                    st.markdown(decomposed_reqs)
                        else:
                            st.markdown(
                                f'<div style="background-color:#D4EDDA;color:#155724;padding:10px;'
                                f'border-radius:5px;margin-bottom:10px;">✅ <strong>{r["id"]}</strong> {r["text"]}</div>',
                                unsafe_allow_html=True,
                            )

            if saved_count:
              st.success(f"Successfully saved {saved_count} document(s) to the project.")
    # Clear uploader state so files aren’t reprocessed
              uploader_key = f"uploader_unified_{project_id or 'none'}"
              st.session_state.pop(uploader_key, None)
    # Also clear the example selector so it doesn’t re-add an example on refresh
              st.session_state.pop("example_unified", None)


            # NEW: Combined CSV for all analyzed documents in this run
            if all_export_rows:
                st.subheader("Download Combined Analysis")
                df_all = pd.DataFrame(all_export_rows)
                csv_all = df_all.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download All Analyzed Documents (CSV)",
                    data=csv_all,
                    file_name="ReqCheck_All_Analyzed_Documents.csv",
                    mime="text/csv",
                    key="dl_csv_all_docs",
                )
                # --- Project library (document versions) ---
st.divider()
st.header("Documents in this Project")

if st.session_state.selected_project is None:
    st.info("Select a project to view its saved documents.")
else:
    pid = st.session_state.selected_project[0]
    try:
        if hasattr(db, "get_documents_for_project"):
            rows = db.get_documents_for_project(pid)  # (doc_id, file_name, version, uploaded_at, clarity_score)
            if not rows:
                st.info("No documents have been added to this project yet.")
            else:
                # One row per version
                doc_data = []
                for (doc_id, file_name, version, uploaded_at, clarity_score) in rows:
                    doc_data.append({
                        "File Name": file_name,
                        "Version": version,
                        "Uploaded On": uploaded_at.replace("T", " ")[:19] if isinstance(uploaded_at, str) else uploaded_at,
                        "Clarity Score": f"{clarity_score} / 100" if clarity_score is not None else "—",
                    })
                df_docs = pd.DataFrame(doc_data).sort_values(["File Name","Version"], ascending=[True, False])
                st.dataframe(df_docs, use_container_width=True)

                # Export summary
                proj_csv = df_docs.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download Project Documents Summary (CSV)",
                    data=proj_csv,
                    file_name=f"Project_{pid}_Documents_Summary.csv",
                    mime="text/csv",
                    key="dl_csv_project_docs",
                )
        else:
            st.info("get_documents_for_project() not found in db.database.")
    except Exception as e:
        st.error(f"Failed to load documents for this project: {e}")




# ------------------------------ Tab: Need Helper ------------------------------
with tab_need:
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    st.header("Translate a Stakeholder Need" + (f" — Project: {pname}" if pname else ""))

    need_input = st.text_area(
        "Enter a stakeholder need:",
        height=100,
        placeholder="e.g., I need to see the drone's location on a map."
    )
    if st.button("Generate Requirement"):
        if not st.session_state.api_key:
            st.warning("Please enter your Google AI API Key.")
        elif not need_input:
            st.error("Please enter a stakeholder need.")
        else:
            with st.spinner("AI is thinking..."):
                generated_req = generate_requirement_from_need(st.session_state.api_key, need_input)
                st.info("AI Generated Suggestion:")
                st.markdown(generated_req)

# ------------------------------ Tab: Chatbot ------------------------------
with tab_chat:
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    st.header("Chat with an AI Systems Engineering Assistant" + (f" — Project: {pname}" if pname else ""))

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a question about your requirements..."):
        if not st.session_state.api_key:
            st.warning("Please enter your Google AI API Key at the top of the page to use the chatbot.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("AI is thinking..."):
                api_history = [{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages]
                response = get_chatbot_response(st.session_state.api_key, api_history)

            st.session_state.messages.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)
