import streamlit as st
import sys
import os
import re
import docx
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd

# Make local packages importable when run from /ui
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- External project modules ---
from core.analyzer import (
    check_requirement_ambiguity,
    check_passive_voice,
    check_incompleteness,
)
from core.scoring import calculate_clarity_score
from llm.ai_suggestions import get_ai_suggestion, generate_requirement_from_need
from db.database import init_db, add_project, get_all_projects

# Try to import chatbot; if missing, shim via get_ai_suggestion
try:
    from llm.ai_suggestions import get_chatbot_response
except Exception:
    def get_chatbot_response(api_key: str, history: list[dict]) -> str:
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

# ===================================================================
# Helpers used by the analyzer UI
# ===================================================================

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
        content = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    else:
        content = ""
    return extract_requirements_from_string(content)

def format_requirement_with_highlights(req_id, req_text, issues):
    """Inline HTML highlight for ambiguous/passive elements."""
    highlighted_text = req_text
    if issues['ambiguous']:
        for word in issues['ambiguous']:
            highlighted_text = re.sub(
                r'\b' + re.escape(word) + r'\b',
                f'<span style="background-color:#FFFF00;color:black;padding:2px 4px;border-radius:3px;">{word}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )
    if issues['passive']:
        for phrase in issues['passive']:
            highlighted_text = re.sub(
                re.escape(phrase),
                f'<span style="background-color:#FFA500;padding:2px 4px;border-radius:3px;">{phrase}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )

    display_html = f"⚠️ <strong>{req_id}</strong> {highlighted_text}"
    explanations = []
    if issues['ambiguous']:
        explanations.append(f"<i>- Ambiguity: Found weak words: <b>{', '.join(issues['ambiguous'])}</b></i>")
    if issues['passive']:
        explanations.append(f"<i>- Passive Voice: Found phrase: <b>'{', '.join(issues['passive'])}'</b>. Consider active voice.</i>")
    if issues['incomplete']:
        explanations.append("<i>- Incompleteness: Requirement appears to be a fragment.</i>")
    if explanations:
        display_html += "<br>" + "<br>".join(explanations)

    return (
        f'<div style="background-color:#FFF3CD;color:#856404;padding:10px;'
        f'border-radius:5px;margin-bottom:10px;">{display_html}</div>'
    )

# ===================================================================
# Global styles & session state
# ===================================================================

st.set_page_config(page_title="ReqCheck Workspace", page_icon="🗂️", layout="wide")

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

# Init DB once
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

# ===================================================================
# Tabs: Analyzer | Need->Requirement | Chatbot | Projects (extra)
# ===================================================================

tab_analyze, tab_need, tab_chat, tab_projects = st.tabs([
    "📄 Document Analyzer",
    "💡 Need-to-Requirement Helper",
    "💬 Requirements Chatbot",
    "🗂️ Projects",  # extra/optional tab
])

# ------------------------------
# Projects (select/create) TAB
# ------------------------------
with tab_projects:
    st.header("Project Workspace")
    projects = get_all_projects()
    if projects:
        names = [p[1] for p in projects]
        selected_name = st.selectbox("Select an existing project:", names, key="proj_select")
        if st.button("Load Project", key="btn_load_proj"):
            for p in projects:
                if p[1] == selected_name:
                    st.session_state.selected_project = p
                    st.success(f"Loaded: {selected_name}")
                    st.rerun()
    else:
        st.info("No projects found. Create a new one to get started.")

    st.divider()
    st.subheader("Create a New Project")
    new_project_name = st.text_input("New Project Name:", key="new_proj_name")
    if st.button("Create", key="btn_create_proj"):
        if new_project_name:
            feedback = add_project(new_project_name)
            st.success(feedback)
            st.rerun()
        else:
            st.error("Please enter a project name.")

    # Show currently selected project (if any)
    if st.session_state.selected_project is not None:
        _, name = st.session_state.selected_project
        st.caption(f"Current project: **{name}**")
        if st.button("← Clear Selection", key="btn_clear_proj"):
            st.session_state.selected_project = None
            st.rerun()

# Utility: badge suffix for headers
def project_suffix():
    if st.session_state.selected_project is None:
        return " — (no project selected)"
    return f" — Project: {st.session_state.selected_project[1]}"

# ------------------------------
# Tab 1: Document Analyzer
# ------------------------------
with tab_analyze:
    st.header("Analyze a Requirements Document" + project_suffix())

    uploaded_file = st.file_uploader("Upload your own requirements document", type=['txt', 'docx'])

    example_files = {
        "Choose an example...": None,
        "Drone System SRS (Complex Example)": "DRONE_SRS_v1.0.docx"
    }
    selected_example = st.selectbox("Or, select an example to get started:", options=list(example_files.keys()))

    requirements_list = []

    if selected_example != "Choose an example...":
        file_path = example_files[selected_example]
        try:
            if file_path.endswith('.docx'):
                d = docx.Document(file_path)
                content = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            requirements_list = extract_requirements_from_string(content)
            st.info(f"Loaded example: **{selected_example}**")
        except FileNotFoundError:
            st.error(f"Example file not found: {file_path}. Place it in the project folder.")

    elif uploaded_file is not None:
        with st.spinner('Analyzing document... Please wait.'):
            requirements_list = extract_requirements_from_file(uploaded_file)
        st.success(f"Analysis complete! Found {len(requirements_list)} requirements.")

    if requirements_list:
        results = []
        for req_id, req_text in requirements_list:
            ambiguous_words = check_requirement_ambiguity(req_text)
            passive_phrases = check_passive_voice(req_text)
            is_incomplete = check_incompleteness(req_text)
            results.append({
                'id': req_id,
                'text': req_text,
                'ambiguous': ambiguous_words,
                'passive': passive_phrases,
                'incomplete': is_incomplete
            })

        st.divider()
        st.header("Analysis Summary")

        total_reqs = len(requirements_list)
        flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
        clarity_score = calculate_clarity_score(total_reqs, flagged_reqs) if total_reqs > 0 else 100

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Requirements", f"{total_reqs}")
        c2.metric("Flagged for Issues", f"{flagged_reqs}")
        c3.metric("Clarity Score", f"{clarity_score} / 100")
        st.progress(clarity_score)
        if clarity_score >= 90:
            st.balloons()

        issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0}
        for res in results:
            if res['ambiguous']:
                issue_counts["Ambiguity"] += 1
            if res['passive']:
                issue_counts["Passive Voice"] += 1
            if res['incomplete']:
                issue_counts["Incompleteness"] += 1

        st.subheader("Issues by Type")
        st.bar_chart(issue_counts)

        all_ambiguous_words = []
        for res in results:
            if res['ambiguous']:
                all_ambiguous_words.extend(res['ambiguous'])

        with st.expander("View Common Weak Words Cloud"):
            if all_ambiguous_words:
                text_for_cloud = ' '.join(all_ambiguous_words)
                wordcloud = WordCloud(width=800, height=300, background_color='white', collocations=False).generate(text_for_cloud)
                fig, ax = plt.subplots()
                ax.imshow(wordcloud, interpolation='bilinear')
                ax.axis("off")
                st.pyplot(fig)
            else:
                st.write("No ambiguous words found.")

        st.divider()
        st.header("Detailed Analysis")

        for result in results:
            is_flagged = result['ambiguous'] or result['passive'] or result['incomplete']
            if is_flagged:
                with st.container(border=True):
                    formatted_html = format_requirement_with_highlights(result['id'], result['text'], result)
                    st.markdown(formatted_html, unsafe_allow_html=True)
                    if result['ambiguous']:
                        st.caption(f"ⓘ **Ambiguity:** Found weak words: **{', '.join(result['ambiguous'])}**.")
                    if result['passive']:
                        st.caption(f"ⓘ **Passive Voice:** Found phrase: **'{', '.join(result['passive'])}'**. Consider active voice.")
                    if result['incomplete']:
                        st.caption("ⓘ **Incompleteness:** Requirement appears to be a fragment.")
                    with st.expander("✨ Get AI Rewrite Suggestion"):
                        if not st.session_state.api_key:
                            st.warning("Please enter your Google AI API Key.")
                        else:
                            if st.button(f"Rewrite Requirement {result['id']}", key=result['id']):
                                with st.spinner("AI is thinking..."):
                                    suggestion = get_ai_suggestion(st.session_state.api_key, result['text'])
                                    st.info("AI Suggestion:")
                                    st.markdown(f"> {suggestion}")
            else:
                success_html = (
                    f'<div style="background-color:#D4EDDA;color:#155724;padding:10px;'
                    f'border-radius:5px;margin-bottom:10px;">✅ <strong>{result["id"]}</strong> {result["text"]}</div>'
                )
                st.markdown(success_html, unsafe_allow_html=True)

        st.divider()
        st.header("Export Report")

        export_data = []
        for result in results:
            issues = []
            if result['ambiguous']:
                issues.append(f"Ambiguity: {', '.join(result['ambiguous'])}")
            if result['passive']:
                issues.append(f"Passive Voice: {', '.join(result['passive'])}")
            if result['incomplete']:
                issues.append("Incompleteness: Missing verb.")
            export_data.append({
                "ID": result['id'],
                "Requirement Text": result['text'],
                "Status": "Clear" if not issues else "Flagged",
                "Issues Found": "; ".join(issues)
            })
        df = pd.DataFrame(export_data)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Report as CSV",
            data=csv,
            file_name=f"ReqCheck_Report.csv",
            mime="text/csv"
        )

# ------------------------------
# Tab 2: Need-to-Requirement Helper
# ------------------------------
with tab_need:
    st.header("Translate a Stakeholder Need" + project_suffix())

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

# ------------------------------
# Tab 3: Requirements Chatbot
# ------------------------------
with tab_chat:
    st.header("Chat with an AI Systems Engineering Assistant")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Render previous messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Get new user input and respond
    if prompt := st.chat_input("Ask a question about your requirements..."):
        if not st.session_state.api_key:
            st.warning("Please enter your Google AI API Key at the top of the page to use the chatbot.")
        else:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Query AI
            with st.spinner("AI is thinking..."):
                api_history = [
                    {"role": m["role"], "parts": [m["content"]]}
                    for m in st.session_state.messages
                ]
                response = get_chatbot_response(st.session_state.api_key, api_history)

            # Add assistant reply
            st.session_state.messages.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)
