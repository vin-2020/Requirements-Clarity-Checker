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

# --- NEW: read .docx from disk path (for re-analysis of stored files) ---
def _read_docx_text_and_rows_from_path(path: str):
    """Same as _read_docx_text_and_rows, but loads a .docx from a path on disk."""
    d = docx.Document(path)
    parts = []
    rows = []

    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)

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

# --- NEW: File storage helpers (added exactly as requested) ---
def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name)

def _save_uploaded_file_for_doc(project_id: int, doc_id: int, display_name: str, uploaded_file) -> str:
    base_dir = os.path.join("data", "projects", str(project_id), "documents")
    os.makedirs(base_dir, exist_ok=True)
    safe_name = _sanitize_filename(display_name)
    out_path = os.path.join(base_dir, f"{doc_id}_{safe_name}")
    try:
        uploaded_file.seek(0)
        with open(out_path, "wb") as f:
            f.write(uploaded_file.read())
    except Exception:
        with open(out_path, "wb") as f:
            f.write(uploaded_file.getvalue())
    return out_path

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

    # --- NEW: allow re-analysis of previously saved files in this project ---
    stored_to_analyze = None
    if project_id is not None and hasattr(db, "get_documents_for_project"):
        try:
            _rows = db.get_documents_for_project(project_id)
            stored_docs = []
            labels = []
            for (doc_id, file_name, version, uploaded_at, clarity_score) in _rows:
                conv_path = os.path.join("data", "projects", str(project_id), "documents",
                                         f"{doc_id}_{_sanitize_filename(file_name)}")
                if os.path.exists(conv_path):
                    stored_docs.append((doc_id, file_name, version, conv_path))
                    labels.append(f"{file_name} (v{version})")
            if stored_docs:
                sel = st.selectbox("Re-analyze a saved document:", ["— Select —"] + labels, key="rean_select")
                if sel != "— Select —":
                    if st.button("Analyze Selected", key="rean_btn"):
                        idx = labels.index(sel)
                        _doc_id, _fn, _ver, _path = stored_docs[idx]
                        stored_to_analyze = (_fn, _path)
        except Exception:
            pass

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
    # - source_type == "stored"  -> payload is a filesystem path to a saved file
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

    # --- NEW: append stored selection (if any) ---
    if stored_to_analyze:
        _fn, _path = stored_to_analyze
        docs_to_process.append(("stored", _fn, _path))

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

                elif src_type == "stored":
                    # payload is a filesystem path we previously saved
                    path = payload
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        if path.endswith(".txt"):
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                raw = f.read()
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw) or extract_requirements_from_string(raw)
                        elif path.endswith(".docx"):
                            flat_text, table_rows = _read_docx_text_and_rows_from_path(path)
                            table_reqs = _extract_requirements_from_table_rows(table_rows)
                            if table_reqs:
                                reqs = table_reqs
                            else:
                                reqs = extract_requirements_with_ai(st.session_state.api_key, flat_text) or extract_requirements_from_string(flat_text)
                        else:
                            reqs = []
                    else:
                        # Standard parse without AI
                        if path.endswith(".txt"):
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                raw = f.read()
                            reqs = extract_requirements_from_string(raw)
                        elif path.endswith(".docx"):
                            flat_text, table_rows = _read_docx_text_and_rows_from_path(path)
                            reqs = _extract_requirements_from_table_rows(table_rows) or extract_requirements_from_string(flat_text)
                        else:
                            reqs = []

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

                # --- Save to DB if helpers exist and a project is selected (only for new inputs) ---
                if project_id is not None and src_type in ("upload", "example"):
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

                            # --- persist uploaded file (only for actual uploads) ---
                            if src_type == "upload":
                                try:
                                    file_path = _save_uploaded_file_for_doc(project_id, doc_id, display_name, payload)
                                    if hasattr(db, "add_document_file"):
                                        try:
                                            db.add_document_file(doc_id, file_path)
                                        except Exception:
                                            pass
                                    elif hasattr(db, "set_document_file_path"):
                                        try:
                                            db.set_document_file_path(doc_id, file_path)
                                        except Exception:
                                            pass
                                except Exception as _e:
                                    st.warning(f"Saved analysis, but file persistence failed for '{display_name}': {_e}")

                        # Fallback to legacy helpers
                        elif hasattr(db, "add_document_to_project") and hasattr(db, "add_requirements_to_document"):
                            doc_id = db.add_document_to_project(project_id, display_name, clarity_score)
                            db.add_requirements_to_document(doc_id, reqs)
                            saved_count += 1

                            # --- persist uploaded file for legacy path as well ---
                            if src_type == "upload":
                                try:
                                    file_path = _save_uploaded_file_for_doc(project_id, doc_id, display_name, payload)
                                    if hasattr(db, "add_document_file"):
                                        try:
                                            db.add_document_file(doc_id, file_path)
                                        except Exception:
                                            pass
                                    elif hasattr(db, "set_document_file_path"):
                                        try:
                                            db.set_document_file_path(doc_id, file_path)
                                        except Exception:
                                            pass
                                except Exception as _e:
                                    st.warning(f"Saved analysis, but file persistence failed for '{display_name}': {_e}")
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
        

# ------------------------------ Tab: Need Tutor (Simplified Editable Preview + Pro CSV) ------------------------------
with tab_need:
    import re, json
    import pandas as pd
    import streamlit as st
    import streamlit.components.v1 as components

    # ---------- SAFE analyzer imports (unchanged behavior) ----------
    try:
        from core.rules import RuleEngine as _RealRuleEngine
    except Exception:
        _RealRuleEngine = None

    class _FallbackRuleEngine:
        def is_check_enabled(self, name: str) -> bool: return True
        def get_ambiguity_terms(self): return []
        def get_custom_weak_words(self): return []
        def get_ambiguity_words(self): return []
        def get_weak_words(self): return []

    def _get_rule_engine():
        try:
            return _RealRuleEngine() if _RealRuleEngine is not None else _FallbackRuleEngine()
        except Exception:
            return _FallbackRuleEngine()

    try:
        from core.analyzer import check_requirement_ambiguity, check_passive_voice, check_incompleteness
        try:
            from core.analyzer import check_singularity as _chk_sing
        except Exception:
            def _chk_sing(_): return []
    except Exception:
        def check_requirement_ambiguity(_t, _re=None): return []
        def check_passive_voice(_t): return []
        def check_incompleteness(_t): return []
        def _chk_sing(_): return []

    # ---------- AI helpers (keep as-is) ----------
    try:
        from llm.ai_suggestions import analyze_need_autofill as _strict_autofill
    except Exception:
        _strict_autofill = None
    try:
        from llm.ai_suggestions import get_ai_suggestion, decompose_requirement_with_ai
    except Exception:
        def get_ai_suggestion(*args, **kwargs): return ""
        def decompose_requirement_with_ai(*args, **kwargs): return ""

    # ---------- State ----------
    def _init_state():
        if "need_ui" not in st.session_state:
            st.session_state.need_ui = {
                # top
                "mode":"Detailed",
                "req_type":"Functional",
                "stakeholder":"", "priority":"Should", "lifecycle":"Operations",
                # content
                "need_text":"", "rationale":"",
                # structured fields (for Detailed)
                "Functional":{"actor":"", "modal":"shall", "action":"", "object":"", "trigger":"", "conditions":"", "performance":""},
                "Performance":{"function":"", "metric":"", "threshold":"", "unit":"", "conditions":"", "measurement":"", "verification":"Test"},
                "Constraint":{"subject":"", "constraint_text":"", "driver":"", "why":""},
                "Interface":{"system":"", "external":"", "standard":"", "direction":"Bi-directional", "data":"", "perf":"", "conditions":""},
                # previews/output
                "preview_req":"",          # now the ONLY editable preview surface
                "final_req":"",            # explicit final requirement (user-loaded)
                "final_ac":[],             # acceptance criteria (editable)
                "last_ai_raw":"",          # latest AI raw (review/decompose)
                # IDs & role (simple)
                "final_role":"Parent",     # "Parent" or "Child"
                "final_id":"",             # ID for the Final Requirement
                "final_parent_id":"",      # only if final is a child
                "child_next":1,            # next child integer suffix for quick generate
                # Decomposition
                "decomp_source":"Need",    # "Need" or "Final Requirement"
                "decomp_parent_text":"",   # parent text used in decomposition section (editable)
                "decomp_parent_id":"",     # parent id used in decomposition section (editable)
                "decomp_rows":[],          # list of {"ID","ParentID","Requirement Text"}
                "scroll_to":""
            }
    _init_state()
    S = st.session_state.need_ui

    # ---------- Header ----------
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    st.header("✍️ Need → Requirement Assistant" + (f" — Project: {pname}" if pname else ""))

    # ---------- Top controls ----------
    c_top = st.columns([1,1,1,1,1])
    with c_top[0]:
        S["mode"] = st.radio("Mode", ["Simple","Detailed"], index=["Simple","Detailed"].index(S["mode"]),
                             horizontal=True, key="need_mode_top")
    with c_top[1]:
        S["req_type"] = st.selectbox("Requirement Type",
            ["Functional","Performance","Constraint","Interface"],
            index=["Functional","Performance","Constraint","Interface"].index(S["req_type"]),
            key="need_reqtype_top")
    with c_top[2]:
        S["priority"] = st.selectbox("Priority", ["Must","Should","Could","Won't (now)"],
                                     index=["Must","Should","Could","Won't (now)"].index(S["priority"]),
                                     key="need_priority_top")
    with c_top[3]:
        S["lifecycle"] = st.selectbox("Life-cycle", ["Concept","Development","P/I/V&V","Operations","Maintenance","Disposal"],
                                      index=["Concept","Development","P/I/V&V","Operations","Maintenance","Disposal"].index(S["lifecycle"]),
                                      key="need_lifecycle_top")
    with c_top[4]:
        S["stakeholder"] = st.text_input("Stakeholder / Role", value=S["stakeholder"],
                                         placeholder="e.g., Field operator, Acquirer", key="need_stakeholder_top")

    # ---------- Need & Rationale ----------
    st.subheader("Stakeholder Need")
    S["need_text"] = st.text_area("Describe the need (no 'shall')", value=S["need_text"], height=110,
                                  placeholder="e.g., The operator needs the drone to warn about low battery to avoid mission aborts.",
                                  key="need_text_area")
    S["rationale"] = st.text_area("Rationale (why this matters)", value=S["rationale"], height=80,
                                  placeholder="e.g., Prevent mission failure and avoid emergency landings.",
                                  key="need_rat_area")

    # ---------- Helpers (formatting only; analyzer unchanged) ----------
    _VAGUE = ("all specified","as needed","as soon as possible","etc.","including but not limited to")
    def _strip_vague(t: str) -> str:
        x = (t or "")
        for b in _VAGUE: x = x.replace(b, "")
        return re.sub(r"\s{2,}", " ", x).strip(" ,.")

    def _strip_perf_from_object(obj: str, perf: str) -> tuple[str,str]:
        o = (obj or "").strip(); p = (perf or "").strip()
        if not o: return o, p
        rxes = [
            r'\bwith (a )?probability of\s*[0-9]*\.?[0-9]+%?',
            r'\b(minimum|maximum|at least|no more than)\s*[0-9]*\.?[0-9]+%?\b',
            r'\b\d+(\.\d+)?\s*(ms|s|sec|m|km|Hz|kHz|MHz|kbps|Mbps|Gbps|fps)\b',
            r'\b\d+(\.\d+)?\s*%(\b|$)'
        ]
        extracted = []
        for rx in rxes:
            m = re.search(rx, o, flags=re.I)
            if m:
                extracted.append(m.group(0))
                o = (o[:m.start()] + o[m.end():]).strip(" ,.")
        if extracted:
            extra = " ".join(extracted)
            if p and extra not in p: p = f"{p}; {extra}"
            if not p: p = extra
        return o, p

    def _push_need_context_to_conditions(conds: str, need_text: str) -> str:
        base = (conds or "")
        nl = (need_text or "").lower()
        bits = []
        if "contested airspace" in nl and "contested airspace" not in base.lower():
            bits.append("in contested airspace")
        if ("avoid" in nl or "avoiding detection" in nl or "stealth" in nl) and not re.search(r"detect|avoid", base, flags=re.I):
            bits.append("while minimizing detectability by adversary sensors")
        if "return" in nl and "return" not in base.lower():
            bits.append("and return safely to base")
        if bits:
            base = (base + " " + " ".join(bits)).strip()
        return re.sub(r"\s{2,}", " ", base)

    def _normalize_trigger(trig: str) -> str:
        t = (trig or "").strip(" ,.")
        if not t: return ""
        t = re.sub(r'^\s*when\s+when\s+', 'when ', t, flags=re.I)
        if not re.match(r'^(when|if|while|during)\b', t, flags=re.I):
            t = "when " + t
        return t

    # ---------- Previews ----------
    def _need_preview():
        raw_need = (S["need_text"] or "").strip()
        if raw_need.lower().startswith(("the ","a ","an ","i ","we ","user ","operator ","stakeholder ","mission")):
            text = raw_need
        else:
            text = f"The {S['stakeholder'] or 'stakeholder'} needs the system to {raw_need or '[describe need]'}"
        text += f" so that {S['rationale'].strip()}." if S["rationale"].strip() else "."
        return text

    def _build_req_preview():
        t = S["req_type"]
        if t == "Functional":
            f = S["Functional"]
            actor = (f["actor"] or "[Actor]").strip()
            modal = (f["modal"] or "shall").strip()
            action = (f["action"] or "[action]").strip()
            obj = (f["object"] or "[object]").strip()
            trig = _normalize_trigger(f["trigger"])
            cond = _strip_vague(f["conditions"])
            perf = _strip_vague(f["performance"])
            prefix = (trig + ", ") if trig else ""
            tail_perf = f" {perf}" if perf and perf.lower() not in obj.lower() else ""
            tail_cond = f" {cond}" if cond else ""
            snt = f"{prefix}{actor} {modal} {action} {obj}{tail_perf}{tail_cond}"
            snt = re.sub(r"\s{2,}", " ", snt).strip()
            if not snt.endswith("."): snt += "."
            return snt
        if t == "Performance":
            p = S["Performance"]
            seg_cond = f" under {p['conditions']}" if p["conditions"] else ""
            seg_meas = f" as measured by {p['measurement']}" if p["measurement"] else ""
            return f"The {p['function'] or '[function]'} shall have {p['metric'] or '[metric]'} {p['threshold'] or '[value]'} {p['unit'] or '[unit]'}{seg_cond}{seg_meas}."
        if t == "Constraint":
            c = S["Constraint"]
            seg = f" per {c['driver']}" if c["driver"] else ""
            return f"The {c['subject'] or '[subject]'} shall comply with {c['constraint_text'] or '[constraint]'}{seg}."
        if t == "Interface":
            i = S["Interface"]
            seg_perf = f" with {i['perf']}" if i["perf"] else ""
            seg_cond = f" under {i['conditions']}" if i["conditions"] else ""
            return f"The {i['system'] or '[system]'} shall interface with {i['external'] or '[external system]'} via {i['standard'] or '[standard]'} ({i['direction']}). It shall exchange {i['data'] or '[data]'}{seg_perf}{seg_cond}."
        return ""

    # Initialize preview once if empty (avoid overwriting user edits each render)
    if not S.get("preview_req"):
        S["preview_req"] = _build_req_preview()

    # ---------- SIMPLE MODE ACTION ROW ----------
    if S["mode"] == "Simple":
        row = st.columns([1.2, 1.2, 1.1, 1.1, 1.0])
        with row[0]:
            if st.button("🚀 Generate Requirement"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need.")
                else:
                    prompt = f"""
You are a systems engineer. Convert the NEED into ONE clear, testable {S['req_type']} requirement (use 'shall') and 3–6 acceptance criteria.

NEED:
\"\"\"{S['need_text'].strip()}\"\"\"\n
RATIONALE:
\"\"\"{S['rationale'].strip()}\"\"\"\n
Return STRICTLY:

REQUIREMENT: <one sentence, active voice, measurable where applicable>

ACCEPTANCE CRITERIA:
- <criterion 1 with setup/conditions + threshold + verification method>
- <criterion 2>
- <criterion 3>
"""
                    raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    S["last_ai_raw"] = raw
                    req = ""
                    m = re.search(r'(?im)^\s*REQUIREMENT\s*:\s*(.+)$', raw)
                    if m: req = m.group(1).strip()
                    if not req:
                        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                        req = next((ln for ln in lines if re.search(r'\bshall\b', ln, re.I)), "")
                    if req:
                        S["preview_req"] = req

                    ac = []
                    ac_block = raw.split("ACCEPTANCE CRITERIA", 1)[-1] if "ACCEPTANCE CRITERIA" in raw else ""
                    for ln in (ac_block or "").splitlines():
                        if re.match(r'^\s*[-*•]\s+', ln):
                            ac.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                    S["final_ac"] = ac
                    st.success("Requirement generated. Review below.")
        with row[1]:
            if st.button("🪄 Improve Requirement"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["preview_req"].strip():
                    st.error("Generate a requirement first.")
                else:
                    base = S["preview_req"].strip()
                    prompt = f"""Rewrite this as a single, clear, unambiguous, testable sentence in active voice using 'shall'. Return only the sentence.

\"\"\"{base}\"\"\""""
                    out = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    if out.strip():
                        S["preview_req"] = out.strip().splitlines()[0]
                        st.success("Requirement refined.")
        with row[2]:
            if st.button("🤖 Review & Generate AC"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["preview_req"].strip():
                    st.error("Enter or generate a requirement first.")
                else:
                    prompt = f"""
Act as a systems engineering reviewer. Provide a short critique and 3–6 testable acceptance criteria (each includes setup/conditions, threshold(s), and verification: Test/Analysis/Inspection/Demonstration).

REQUIREMENT:
\"\"\"{S['preview_req'].strip()}\"\"\""""
                    raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    S["last_ai_raw"] = raw
                    bullets = []
                    for ln in raw.splitlines():
                        if re.match(r'^\s*[-*•]\s+', ln):
                            bullets.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                    if bullets:
                        S["final_ac"] = bullets
                        st.success("Acceptance Criteria generated.")
        with row[3]:
            if st.button("🧩 Decompose"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                else:
                    src = S.get("decomp_source","Need")
                    base = S["need_text"].strip() if src == "Need" else S["preview_req"].strip()
                    if not base:
                        st.error(f"Enter a {src.lower()} to decompose.")
                    else:
                        S["last_ai_raw"] = decompose_requirement_with_ai(st.session_state.api_key, base) or ""
                        rows, idx = [], 1
                        for ln in (S["last_ai_raw"] or "").splitlines():
                            if re.match(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', ln):
                                txt = re.sub(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', '', ln).strip()
                                if txt:
                                    parent = S.get("final_id","").strip() or S.get("final_parent_id","").strip()
                                    cid = f"{(parent or 'REQ-000')}.{idx}"
                                    rows.append({"ID": cid, "ParentID": parent, "Requirement Text": txt})
                                    idx += 1
                        S["decomp_rows"] = rows
                        S["decomp_parent_text"] = S["preview_req"].strip() if src == "Final Requirement" else ""
                        S["decomp_parent_id"] = S.get("final_id","").strip()
                        S["scroll_to"] = "decomp"
                        st.rerun()
        with row[4]:
            if st.button("↺ Reset"):
                _init_state()
                st.rerun()

    # ---------- DETAILED MODE (Analyze Autofill + fields) ----------
    if S["mode"] == "Detailed":
        st.caption("Use **Analyze Need (AI Autofill)** to seed fields; then refine and preview.")
        c_an = st.columns([1,1,2])
        with c_an[0]:
            if st.button("🔎 Analyze Need (AI Autofill)"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need first.")
                elif not _strict_autofill:
                    st.info("Autofill helper not available; fill fields manually.")
                else:
                    with st.spinner("Analyzing need..."):
                        kv = _strict_autofill(st.session_state.api_key, S["need_text"], S["req_type"]) or {}
                    if S["req_type"] == "Functional":
                        actor = _strip_vague(kv.get("Actor","")) or "The system"
                        modal = (kv.get("ModalVerb","shall") or "shall").lower()
                        action = _strip_vague(kv.get("Action",""))
                        obj, perf = _strip_perf_from_object(_strip_vague(kv.get("Object","")), _strip_vague(kv.get("Performance","")))
                        trig = _normalize_trigger(_strip_vague(kv.get("Trigger","")))
                        cond = _push_need_context_to_conditions(_strip_vague(kv.get("Conditions","")), S["need_text"])
                        S["Functional"].update({"actor":actor,"modal": modal if modal in ("shall","will","must") else "shall",
                                                "action":action,"object":obj,"trigger":trig,"conditions":cond,"performance":perf})
                    elif S["req_type"] == "Performance":
                        S["Performance"].update({
                            "function":_strip_vague(kv.get("Function","")),
                            "metric":_strip_vague(kv.get("Metric","")),
                            "threshold":_strip_vague(kv.get("Threshold","")),
                            "unit":_strip_vague(kv.get("Unit","")),
                            "conditions":_strip_vague(kv.get("Conditions","")),
                            "measurement":_strip_vague(kv.get("Measurement","")),
                            "verification": kv.get("VerificationMethod","Test") if kv.get("VerificationMethod") in ("Test","Analysis","Inspection","Demonstration") else "Test"
                        })
                    elif S["req_type"] == "Constraint":
                        S["Constraint"].update({
                            "subject":_strip_vague(kv.get("Subject","")),
                            "constraint_text":_strip_vague(kv.get("ConstraintText","")),
                            "driver":_strip_vague(kv.get("DriverOrStandard","")),
                            "why": _strip_vague(kv.get("Rationale","")) or S["rationale"]
                        })
                    else:
                        dr = kv.get("Direction","Bi-directional")
                        S["Interface"].update({
                            "system":_strip_vague(kv.get("System","")),
                            "external":_strip_vague(kv.get("ExternalSystem","")),
                            "standard":_strip_vague(kv.get("InterfaceStandard","")),
                            "direction": dr if dr in ("In","Out","Bi-directional") else "Bi-directional",
                            "data":_strip_vague(kv.get("DataItems","")),
                            "perf":_strip_vague(kv.get("Performance","")),
                            "conditions":_strip_vague(kv.get("Conditions",""))
                        })
                    # After autofill, seed preview from fields if preview is empty
                    if not S.get("preview_req"):
                        S["preview_req"] = _build_req_preview()
                    st.success("Autofilled. Review and refine below.")
        with c_an[1]:
            if st.button("↺ Clear Fields (this type)"):
                if S["req_type"] == "Functional":
                    S["Functional"] = {"actor":"", "modal":"shall", "action":"", "object":"", "trigger":"", "conditions":"", "performance":""}
                elif S["req_type"] == "Performance":
                    S["Performance"] = {"function":"", "metric":"", "threshold":"", "unit":"", "conditions":"", "measurement":"", "verification":"Test"}
                elif S["req_type"] == "Constraint":
                    S["Constraint"] = {"subject":"", "constraint_text":"", "driver":"", "why":""}
                else:
                    S["Interface"] = {"system":"", "external":"", "standard":"", "direction":"Bi-directional", "data":"", "perf":"", "conditions":""}
                st.info(f"{S['req_type']} fields cleared.")

        # Fields (type-specific)
        st.subheader("Structured Fields")
        if S["req_type"] == "Functional":
            F = S["Functional"]
            c1, c2 = st.columns(2)
            with c1:
                F["actor"] = st.text_input("Actor / System", value=F["actor"], key="fun_actor")
                F["modal"] = st.selectbox("Modal Verb", ["shall","will","must"], index=["shall","will","must"].index(F["modal"]) if F["modal"] in ["shall","will","must"] else 0, key="fun_modal")
                F["action"] = st.text_input("Action / Verb", value=F["action"], key="fun_action")
                F["object"] = st.text_input("Object", value=F["object"], key="fun_object")
            with c2:
                F["trigger"] = st.text_input("Trigger / Event (optional)", value=F["trigger"], key="fun_trigger")
                F["conditions"] = st.text_input("Operating Conditions / State (optional)", value=F["conditions"], key="fun_cond")
                F["performance"] = st.text_input("Performance / Constraint (optional, measurable)", value=F["performance"], key="fun_perf")
        elif S["req_type"] == "Performance":
            P = S["Performance"]
            c1, c2, c3 = st.columns(3)
            with c1:
                P["function"] = st.text_input("Function (what is measured)", value=P["function"], key="perf_func")
                P["metric"] = st.text_input("Metric (e.g., latency, accuracy)", value=P["metric"], key="perf_metric")
            with c2:
                P["threshold"] = st.text_input("Threshold (number)", value=P["threshold"], key="perf_threshold")
                P["unit"] = st.text_input("Unit", value=P["unit"], key="perf_unit")
            with c3:
                P["conditions"] = st.text_input("Conditions / State", value=P["conditions"], key="perf_cond")
                P["measurement"] = st.text_input("Measurement Method", value=P["measurement"], key="perf_measure")
                P["verification"] = st.selectbox("Verification Method", ["Test","Analysis","Inspection","Demonstration"],
                                                 index=["Test","Analysis","Inspection","Demonstration"].index(P["verification"]),
                                                 key="perf_verif")
        elif S["req_type"] == "Constraint":
            C = S["Constraint"]
            c1, c2 = st.columns(2)
            with c1:
                C["subject"] = st.text_input("Subject (system/subsystem/component)", value=C["subject"], key="con_subject")
                C["constraint_text"] = st.text_input("Constraint (what must hold true)", value=C["constraint_text"], key="con_text")
            with c2:
                C["driver"] = st.text_input("Driver / Standard / Policy", value=C["driver"], key="con_driver")
                C["why"] = st.text_input("Rationale (optional)", value=C["why"], key="con_why")
        else:
            I = S["Interface"]
            c1, c2 = st.columns(2)
            with c1:
                I["system"] = st.text_input("This System", value=I["system"], key="if_sys")
                I["external"] = st.text_input("External System", value=I["external"], key="if_ext")
                I["standard"] = st.text_input("Interface Standard / Protocol", value=I["standard"], key="if_std")
            with c2:
                I["direction"] = st.selectbox("Direction", ["In","Out","Bi-directional"],
                                              index=["In","Out","Bi-directional"].index(I["direction"]), key="if_dir")
                I["data"] = st.text_input("Data Items / Messages", value=I["data"], key="if_data")
                I["perf"] = st.text_input("Performance (e.g., latency/throughput)", value=I["perf"], key="if_perf")
            I["conditions"] = st.text_input("Conditions / Modes (optional)", value=I["conditions"], key="if_cond")

    # ---------- Previews & Quality (always shown) ----------
    st.subheader("Previews & Quality")
    left, right = st.columns(2)
    with left:
        st.markdown("**Need Preview (no 'shall')**")
        st.markdown(f"> {_need_preview()}")

    with right:
        st.markdown("**Requirement Preview (editable)**")
        # single editable surface for the preview
        S["preview_req"] = st.text_area(
            "Edit the requirement preview before sending to Final",
            value=S["preview_req"] or _build_req_preview(),
            height=90,
            key="preview_req_edit_area"
        )
        # quick rebuild from fields if needed
        if st.button("Rebuild Preview from Fields"):
            S["preview_req"] = _build_req_preview()
            st.info("Preview rebuilt from the structured fields.")

        # quality checks on the edited preview
        try:
            amb = check_requirement_ambiguity(S["preview_req"], _get_rule_engine())
        except TypeError:
            amb = check_requirement_ambiguity(S["preview_req"])
        except Exception:
            amb = []
        pas = check_passive_voice(S["preview_req"])
        inc = check_incompleteness(S["preview_req"])
        sing = _chk_sing(S["preview_req"])
        qc = st.columns(4)
        qc[0].write(("✅" if not amb else "⚠️") + " Unambiguous")
        qc[1].write(("✅" if not pas else "⚠️") + " Active Voice")
        qc[2].write(("✅" if not inc else "⚠️") + " Complete")
        qc[3].write(("✅" if not sing else "⚠️") + " Singular")
        if amb: st.caption(f"Ambiguous terms: {', '.join(amb)}")
        if pas: st.caption(f"Passive voice: {', '.join(pas)}")
        if sing: st.caption(f"Multiple actions: {', '.join(sing)}")

    # ---------- Final Requirement ----------
    st.subheader("Final Requirement")
    cols_fr = st.columns([1,1])
    with cols_fr[0]:
        if st.button("Load Preview → Final"):
            S["final_req"] = (S["preview_req"] or "").strip()
            st.success("Loaded preview into Final.")
    with cols_fr[1]:
        if st.button("🤖 Review & Generate AC (Final)"):
            if not st.session_state.api_key:
                st.warning("Enter your Google AI API Key.")
            elif not S.get("final_req","").strip():
                st.error("Enter or load a Final requirement first.")
            else:
                prompt = f"""
Act as a systems engineering reviewer. Provide a short critique and 3–6 testable acceptance criteria (each includes setup/conditions, threshold(s), and verification: Test/Analysis/Inspection/Demonstration).

REQUIREMENT:
\"\"\"{S['final_req'].strip()}\"\"\""""
                raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                S["last_ai_raw"] = raw
                bullets = []
                for ln in raw.splitlines():
                    if re.match(r'^\s*[-*•]\s+', ln):
                        bullets.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                if bullets:
                    S["final_ac"] = bullets
                    st.success("Acceptance Criteria generated below.")
                else:
                    st.info("No bullets detected. See raw output under the expander below.")

    # Safety defaults
    S.setdefault("final_req", "")
    S.setdefault("final_ac", [])

    S["final_req"] = st.text_area("Final Requirement (single sentence, uses 'shall')",
                                  value=S["final_req"], height=90, key="final_req_edit")

    # ---------- Acceptance Criteria ----------
    st.subheader("Acceptance Criteria")
    ac_text = "\n".join(S.get("final_ac", []))
    new_ac_text = st.text_area("One bullet per line", value=ac_text, height=130, key="need_ac_edit")
    S["final_ac"] = [ln.strip() for ln in new_ac_text.splitlines() if ln.strip()]

    # ---------- ID & Role for Final Requirement ----------
    st.subheader("ID & Role for Final Requirement")
    idrow = st.columns([1,1,1,1])
    with idrow[0]:
        S["final_id"] = st.text_input("Final Requirement ID", value=S.get("final_id",""), placeholder="e.g., REQ-001", key="final_req_id")
    with idrow[1]:
        S["final_role"] = st.radio("Role", ["Parent","Child"],
                                   index=["Parent","Child"].index(S.get("final_role","Parent")), horizontal=True, key="final_role_radio")
    with idrow[2]:
        if S["final_role"] == "Child":
            S["final_parent_id"] = st.text_input("Parent ID", value=S.get("final_parent_id",""), placeholder="e.g., REQ-000", key="final_parent_id")
        else:
            st.caption("Parent role: no parent ID needed.")
    with idrow[3]:
        if S["final_role"] == "Child" and (S.get("final_parent_id","").strip()):
            if st.button("Generate Next Child ID"):
                S["final_id"] = f"{S['final_parent_id'].strip()}.{int(S.get('child_next',1))}"
                S["child_next"] = int(S.get("child_next",1)) + 1
                st.success(f"Child: {S['final_id']}")

    # ---------- Decomposition ----------
    st.subheader("Decomposition")
    st.caption("Choose a source and create a parent/children set. You can edit the parent text/ID and the child items, add or delete children.")

    decomp_top = st.columns([1,1,2])
    with decomp_top[0]:
        S["decomp_source"] = st.selectbox("Decompose From", ["Need","Final Requirement"],
                                          index=["Need","Final Requirement"].index(S["decomp_source"]),
                                          key="decomp_source_sel")

    def _parse_children_lines(text: str) -> list[str]:
        out = []
        for ln in (text or "").splitlines():
            if re.match(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', ln):
                out.append(re.sub(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', '', ln).strip())
        return [x for x in out if x]

    def _ai_parent_and_children_from_need(api_key: str, need_text: str) -> tuple[str, list[str]]:
        prompt = f"""
You are a systems engineer. From the following stakeholder NEED, propose exactly:
- PARENT: a single top-level requirement sentence (use 'shall'), covering the overall capability.
- CHILDREN: 3–8 singular child requirements that decompose the parent, each testable.

Return strictly in this format (no extra prose):
PARENT: <one sentence>
CHILDREN:
- <child 1>
- <child 2>
- <child 3>
- ...

NEED:
\"\"\"{(need_text or '').strip()}\"\"\""""
        raw = get_ai_suggestion(api_key, prompt) or ""
        parent = ""
        m = re.search(r'(?im)^\s*PARENT\s*:\s*(.+)$', raw)
        if m: parent = m.group(1).strip()
        children = _parse_children_lines(raw.split("CHILDREN", 1)[-1] if "CHILDREN" in raw else raw)
        return parent, children

    with decomp_top[1]:
        if st.button("🧩 Generate Decomposition"):
            if S["decomp_source"] == "Final Requirement":
                if not S.get("final_req","").strip():
                    st.error("Enter or load a Final requirement first.")
                else:
                    parent_text = S["final_req"].strip()
                    parent_id = (S.get("final_parent_id","").strip()
                                 if S.get("final_role","Parent") == "Child" and S.get("final_parent_id","").strip()
                                 else S.get("final_id","").strip())
                    if not st.session_state.api_key:
                        st.warning("Enter your Google AI API Key to generate children.")
                    else:
                        raw = decompose_requirement_with_ai(st.session_state.api_key, parent_text) or ""
                        S["last_ai_raw"] = raw
                        kids = _parse_children_lines(raw)
                        rows = []
                        base = parent_id or "REQ-000"
                        for i, txt in enumerate(kids, start=1):
                            rows.append({"ID": f"{base}.{i}", "ParentID": parent_id, "Requirement Text": txt})
                        S["decomp_parent_text"] = parent_text
                        S["decomp_parent_id"] = parent_id
                        S["decomp_rows"] = rows
                        S["scroll_to"] = "decomp"
                        st.rerun()
            else:
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need first.")
                else:
                    with st.spinner("Creating parent and children…"):
                        ptxt, kids = _ai_parent_and_children_from_need(st.session_state.api_key, S["need_text"])
                    S["decomp_parent_text"] = (ptxt or "").strip()
                    S["decomp_parent_id"] = S.get("final_id","").strip()
                    rows = []
                    base = S["decomp_parent_id"] or "REQ-000"
                    for i, txt in enumerate(kids, start=1):
                        rows.append({"ID": f"{base}.{i}", "ParentID": S["decomp_parent_id"], "Requirement Text": txt})
                    S["decomp_rows"] = rows
                    S["scroll_to"] = "decomp"
                    st.rerun()

    # ---- Editable Parent (for decomposition) ----
    st.markdown("<div id='decomp_section'></div>", unsafe_allow_html=True)
    if S["decomp_parent_text"] or S["decomp_rows"]:
        st.markdown("**Decomposition Parent**")
        dpc1, dpc2 = st.columns([3,1])
        with dpc1:
            S["decomp_parent_text"] = st.text_input("Parent Requirement (editable)",
                                                    value=S["decomp_parent_text"], key="decomp_parent_text_edit")
        with dpc2:
            S["decomp_parent_id"] = st.text_input("Parent ID (editable)",
                                                  value=S["decomp_parent_id"], placeholder="e.g., REQ-010",
                                                  key="decomp_parent_id_edit")

    # ---- Editable Children table ----
    if S.get("decomp_rows"):
        st.markdown("**Children (edit / add / delete)**")
        parent_id = (S.get("decomp_parent_id","") or "").strip()
        new_rows = []
        for idx, row in enumerate(S["decomp_rows"], start=1):
            cols = st.columns([0.07, 0.63, 0.20, 0.10])
            with cols[0]:
                st.write(f"{idx}.")
            with cols[1]:
                txt = st.text_input("Child Requirement", value=row.get("Requirement Text",""), key=f"decomp_child_txt_{idx}")
            with cols[2]:
                cid = st.text_input("Child ID", value=row.get("ID",""), key=f"decomp_child_id_{idx}")
            with cols[3]:
                if st.button("🗑️", key=f"decomp_child_del_{idx}"):
                    S["decomp_rows"].pop(idx-1)
                    st.rerun()
            new_rows.append({"Requirement Text": txt, "ID": cid})

        rows_persist = []
        for r in new_rows:
            rows_persist.append({"ID": r["ID"] or "", "ParentID": parent_id, "Requirement Text": r["Requirement Text"]})
        S["decomp_rows"] = rows_persist

        btns = st.columns([1,1,2])
        with btns[0]:
            if st.button("➕ Add Child"):
                base = parent_id or "REQ-000"
                next_idx = len(S["decomp_rows"]) + 1
                S["decomp_rows"].append({"ID": f"{base}.{next_idx}", "ParentID": parent_id, "Requirement Text":"New child requirement"})
                st.rerun()
        with btns[1]:
            if st.button("🔢 Renumber Children"):
                base = parent_id or "REQ-000"
                ren = []
                for i, r in enumerate(S["decomp_rows"], start=1):
                    ren.append({"ID": f"{base}.{i}", "ParentID": parent_id, "Requirement Text": r["Requirement Text"]})
                S["decomp_rows"] = ren
                st.success("Children renumbered.")

        df = pd.DataFrame(S["decomp_rows"])
        st.download_button("Download Decomposition (CSV)",
                           df.to_csv(index=False).encode("utf-8"),
                           file_name="Decomposition.csv",
                           mime="text/csv",
                           key="dl_decomp_csv")

    else:
        st.info("Use **🧩 Generate Decomposition** to create a parent and children set from the Need or from the Final requirement.")

    # ---------- Raw AI output (optional) ----------
    if S.get("last_ai_raw"):
        with st.expander("Show last AI output (raw)"):
            st.code(S["last_ai_raw"])

    # ---------- Smooth scroll ----------
    if S.get("scroll_to") == "decomp":
        components.html("""
            <script>
              const el = document.getElementById('decomp_section');
              if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
            </script>
        """, height=0)
        S["scroll_to"] = ""

    # =========================
    # Professional CSV Export
    # =========================
    st.subheader("Export Requirements (Professional CSV)")

    def _g(val, default=""):  # safe get
        return (val or default).strip() if isinstance(val, str) else (val if val is not None else default)

    # Decide the "parent" row for export
    parent_text = _g(S.get("decomp_parent_text")) or _g(S.get("final_req")) or _g(S.get("preview_req"))
    parent_id   = _g(S.get("decomp_parent_id"))   or _g(S.get("final_id"))
    role        = S.get("final_role","Parent")
    src         = S.get("decomp_source","Need")  # "Need" or "Final Requirement"
    req_type    = S.get("req_type","Functional")
    priority    = S.get("priority","Should")
    lifecycle   = S.get("lifecycle","Operations")
    stakeholder = S.get("stakeholder","")
    rationale   = _g(S.get("rationale"))
    verification = ""
    if req_type == "Performance":
        verification = S.get("Performance",{}).get("verification","") or ""

    # Acceptance criteria (only for the parent/final)
    ac_joined = " | ".join(S.get("final_ac", [])) if S.get("final_ac") else ""

    rows = []

    # Parent row
    if parent_text or parent_id:
        rows.append({
            "ID": parent_id,
            "ParentID": "",
            "Requirement Text": parent_text,
            "Type": req_type,
            "Role": "Parent" if role == "Parent" or not parent_id else role,
            "Priority": priority,
            "Lifecycle": lifecycle,
            "Stakeholder": stakeholder,
            "Source": src,  # Need / Final Requirement
            "Verification": verification,
            "Acceptance Criteria": ac_joined,
            "Rationale": rationale
        })

    # Child rows from decomposition
    for child in (S.get("decomp_rows") or []):
        rows.append({
            "ID": _g(child.get("ID")),
            "ParentID": _g(child.get("ParentID") or parent_id),
            "Requirement Text": _g(child.get("Requirement Text")),
            "Type": req_type,
            "Role": "Child",
            "Priority": priority,
            "Lifecycle": lifecycle,
            "Stakeholder": stakeholder,
            "Source": src,
            "Verification": "",              # per-child verification left blank in this export
            "Acceptance Criteria": "",       # per-child AC not collected here
            "Rationale": rationale
        })

    if not rows:
        st.info("No requirements to export yet. Enter a Final or Decomposition first.")
    else:
        df_pro = pd.DataFrame(rows, columns=[
            "ID","ParentID","Requirement Text","Type","Role","Priority","Lifecycle","Stakeholder",
            "Source","Verification","Acceptance Criteria","Rationale"
        ])
        st.download_button(
            "⬇️ Download Requirements (CSV)",
            data=df_pro.to_csv(index=False).encode("utf-8"),
            file_name="Requirements_Export.csv",
            mime="text/csv",
            key="pro_export_csv"
        )

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
