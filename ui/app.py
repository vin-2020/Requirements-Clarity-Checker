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

# LLM helpers
from llm.ai_suggestions import get_ai_suggestion, generate_requirement_from_need
try:
    from llm.ai_suggestions import get_chatbot_response
except Exception:
    def get_chatbot_response(api_key: str, history: list[dict]) -> str:
        """
        Fallback: flattens chat history into a single prompt and uses get_ai_suggestion().
        """
        convo = []
        for msg in history:
            role = msg.get("role", "user")
            parts = msg.get("parts", [])
            text = parts[0] if parts else ""
            convo.append(f"{role.upper()}: {text}")
        prompt = (
            "You are a Systems Engineering assistant. Answer briefly and precisely.\n\n"
            + "\n".join(convo)
            + "\nASSISTANT:"
        )
        return get_ai_suggestion(api_key, prompt)

# Database helpers  (DB memory integration)
from db.database import init_db, add_project, get_all_projects  # type: ignore
from db import database as db  # type: ignore  # <-- module import avoids name errors
db = importlib.reload(db)  # ensure latest functions (add_document, etc.) are present

# ========================= Helpers for Analyzer =========================

def extract_requirements_from_string(content: str):
    """Extract (id, text) pairs like 'SYS-001 ...' or '1.' lines."""
    requirements = []
    req_pattern = re.compile(r'^((?:[A-Z]+-\d+)|(?:\d+\.))\s+(.*)')
    for line in content.split('\n'):
        line = line.strip()
        if match := req_pattern.match(line):
            requirements.append((match.group(1), match.group(2)))
    return requirements

def extract_requirements_from_file(uploaded_file):
    """Read .txt/.docx to text, then parse requirements."""
    if uploaded_file.name.endswith('.txt'):
        content = uploaded_file.getvalue().decode("utf-8")
    elif uploaded_file.name.endswith('.docx'):
        d = docx.Document(uploaded_file)
        # FIX: proper list comprehension (no stray quotes)
        content = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    else:
        content = ""
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

# =============================== UI Setup ===============================

st.set_page_config(page_title="ReqCheck Workspace", page_icon="🗂️", layout="wide")

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
                    # sanity check and delete
                    if hasattr(db, "delete_project"):
                        db.delete_project(st.session_state.delete_project_id)
                        st.success("Project deleted.")
                    else:
                        st.error("delete_project() is not available in db.database. Did you save and reload?")
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
        st.warning("Please select or create a project to save your analysis.")
    else:
        project_name = st.session_state.selected_project[1]
        st.header(f"Analyze & Add Documents to: {project_name}")

    # Current project (if any)
    project_id = st.session_state.selected_project[0] if st.session_state.selected_project else None

    # One uploader for multiple documents
    uploaded_files = st.file_uploader(
        "Upload one or more requirements documents (.txt or .docx)",
        type=['txt', 'docx'],
        accept_multiple_files=True,
        key="uploader_unified",
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

            for src_type, display_name, payload in docs_to_process:
                # --- Extract requirements ---
                if src_type == "upload":
                    reqs = extract_requirements_from_file(payload)  # UploadedFile
                else:
                    reqs = extract_requirements_from_string(payload)  # text from example

                total_reqs = len(reqs)
                if total_reqs == 0:
                    st.warning(f"⚠️ No recognizable requirements in **{display_name}**.")
                    continue

                # --- Analyze requirements (re-using your checks) ---
                results = []
                issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0, "Singularity": 0}

                for rid, rtext in reqs:
                    ambiguous   = safe_call_ambiguity(rtext, rule_engine)
                    passive     = check_passive_voice(rtext)
                    incomplete  = check_incompleteness(rtext)
                    try:
                        singular = check_singularity(rtext)
                    except Exception:
                        singular = []

                    if ambiguous:  issue_counts["Ambiguity"] += 1
                    if passive:    issue_counts["Passive Voice"] += 1
                    if incomplete: issue_counts["Incompleteness"] += 1
                    if singular:   issue_counts["Singularity"] += 1

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

                                # Optional AI rewrite (uses your existing helper & API key)
                                with st.expander("✨ Get AI Rewrite Suggestion"):
                                    if not st.session_state.api_key:
                                        st.warning("Please enter your Google AI API Key.")
                                    else:
                                        if st.button(
                                            f"Rewrite Requirement {r['id']} ({display_name})",
                                            key=f"rewrite_{display_name}_{r['id']}",
                                        ):
                                            with st.spinner("AI is thinking..."):
                                                suggestion = get_ai_suggestion(st.session_state.api_key, r["text"])
                                            st.info("AI Suggestion:")
                                            st.markdown(f"> {suggestion}")
                        else:
                            st.markdown(
                                f'<div style="background-color:#D4EDDA;color:#155724;padding:10px;'
                                f'border-radius:5px;margin-bottom:10px;">✅ <strong>{r["id"]}</strong> {r["text"]}</div>',
                                unsafe_allow_html=True,
                            )

            if saved_count:
                st.success(f"Successfully saved {saved_count} document(s) to the project.")

    st.divider()
    st.header("Documents in this Project")

    # NEW: show documents actually saved in the DB (if a project is selected)
    if st.session_state.selected_project is None:
        st.info("Select a project to view its saved documents.")
    else:
        pid = st.session_state.selected_project[0]
        try:
            if hasattr(db, "get_documents_for_project"):
                rows = db.get_documents_for_project(pid)
                if not rows:
                    st.info("No documents have been added to this project yet.")
                else:
                    doc_data = []
                    for (doc_id, file_name, version, uploaded_at, clarity_score) in rows:
                        doc_data.append({
                            "File Name": file_name,
                            "Version": version,
                            "Uploaded On": uploaded_at.split("T")[0] if isinstance(uploaded_at, str) else uploaded_at,
                            "Clarity Score": f"{clarity_score} / 100" if clarity_score is not None else "—",
                        })
                    st.dataframe(pd.DataFrame(doc_data), use_container_width=True)
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
