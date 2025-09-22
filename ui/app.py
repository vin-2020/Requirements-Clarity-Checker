import streamlit as st
import sys
import os
import docx
import re
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd

# Ensure local package imports work when running from /ui
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- External project modules (analysis + scoring + LLM helpers) ---
from core.analyzer import check_requirement_ambiguity, check_passive_voice, check_incompleteness
from core.scoring import calculate_clarity_score
from llm.ai_suggestions import get_ai_suggestion, generate_requirement_from_need

# -------------------------------------------------------------------
# LLM helpers import + fallback shim for chatbot
# NOTE: Kept exactly as in your original code. The shim preserves behavior
# if get_chatbot_response is missing in llm.ai_suggestions.
# -------------------------------------------------------------------
from llm.ai_suggestions import get_ai_suggestion, generate_requirement_from_need
# Try to import chatbot; if not present, define a local shim that reuses get_ai_suggestion
try:
    from llm.ai_suggestions import get_chatbot_response  # may not exist in your file
except Exception:
    def get_chatbot_response(api_key: str, history: list[dict]) -> str:
        """
        Fallback: builds a single prompt from chat history and calls get_ai_suggestion().

        Parameters
        ----------
        api_key : str
            Google AI (Gemini) API key.
        history : list[dict]
            Chat history in the form [{"role": "user"|"assistant", "parts": [text]}, ...].

        Returns
        -------
        str
            Assistant reply composed by the underlying suggestion function.
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


# ===================================================================
# Helper functions: extraction, parsing, and HTML formatting
# ===================================================================

def extract_requirements_from_string(content):
    """
    Parse multi-line text to extract requirement tuples (id, text).

    Uses a regex to capture:
      - IDs like 'SYS-001', 'FLT-123'  (pattern: [A-Z]+-\\d+)
      - Simple numbered lists like '1.' '2.' etc. (pattern: \\d+\\.)

    Parameters
    ----------
    content : str
        The full text content containing line-separated requirements.

    Returns
    -------
    list[tuple[str, str]]
        A list of (requirement_id, requirement_text) tuples.
    """
    requirements = []
    # Specific pattern to avoid matching divider lines or noise.
    req_pattern = re.compile(r'^((?:[A-Z]+-\d+)|(?:\d+\.))\s+(.*)')
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if match := req_pattern.match(line):
            requirements.append((match.group(1), match.group(2)))
    return requirements


def extract_requirements_from_file(uploaded_file):
    """
    Read an uploaded .txt or .docx into text and reuse the string parser.

    Parameters
    ----------
    uploaded_file : UploadedFile
        Streamlit uploaded file object (.txt or .docx).

    Returns
    -------
    list[tuple[str, str]]
        Parsed (id, text) requirement tuples.
    """
    content = ""
    if uploaded_file.name.endswith('.txt'):
        content = uploaded_file.getvalue().decode("utf-8")
    elif uploaded_file.name.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        content = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    return extract_requirements_from_string(content)


def format_requirement_with_highlights(req_id, req_text, issues):
    """
    Create an HTML snippet that highlights ambiguity/passive phrases in a requirement.

    Highlighting scheme:
      - Ambiguous words -> yellow background
      - Passive voice phrases -> orange background

    Parameters
    ----------
    req_id : str
        Requirement identifier (e.g., 'SYS-001' or '1.').
    req_text : str
        Raw requirement text.
    issues : dict
        Dict with keys 'ambiguous', 'passive', 'incomplete' as produced by analysis.

    Returns
    -------
    str
        HTML block (safe to render with unsafe_allow_html=True).
    """
    highlighted_text = req_text
    if issues['ambiguous']:
        for word in issues['ambiguous']:
            # Keep text readable on yellow background
            highlighted_text = re.sub(
                r'\b' + re.escape(word) + r'\b',
                f'<span style="background-color: #FFFF00; color: black; padding: 2px 4px; border-radius: 3px;">{word}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )
    if issues['passive']:
        for phrase in issues['passive']:
            highlighted_text = re.sub(
                re.escape(phrase),
                f'<span style="background-color: #FFA500; padding: 2px 4px; border-radius: 3px;">{phrase}</span>',
                highlighted_text,
                flags=re.IGNORECASE
            )

    # Compose the primary display line and optional issue explanations
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
        f'<div style="background-color: #FFF3CD; color: #856404; padding: 10px; '
        f'border-radius: 5px; margin-bottom: 10px;">{display_html}</div>'
    )


# ===================================================================
# UI: Global styles (CSS), sidebar, and API key input
# ===================================================================

# Self-contained CSS for optional future class-based styling (not required by current flow)
st.markdown("""
<style>
    /* Card container for each requirement */
    .req-container {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
    }
    /* Flagged requirement look */
    .flagged {
        background-color: #FFF3CD;
        color: #856404;
        border-color: #FFEEBA;
    }
    /* Clear requirement look */
    .clear {
        background-color: #D4EDDA;
        color: #155724;
        border-color: #C3E6CB;
    }
    /* Ambiguity highlight */
    .highlight-ambiguity {
        background-color: #FFFF00;
        color: black;
        padding: 2px 4px;
        border-radius: 3px;
    }
    /* Passive voice highlight */
    .highlight-passive {
        background-color: #FFA500;
        padding: 2px 4px;
        border-radius: 3px;
    }
    /* Explanation line style */
    .explanation {
        font-size: 0.9em;
        font-style: italic;
        color: #6c757d;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar content
with st.sidebar:
    st.image("https://github.com/vin-2020/Requirements-Clarity-Checker/blob/main/ReqCheck_Logo.png?raw=true", use_container_width=True)
    st.header("About ReqCheck")
    st.info("An AI-assisted tool to evaluate the quality of system requirements...")
    st.header("Project Links")
    st.markdown("[GitHub Repository](https://github.com/vin-2020/Requirements-Clarity-Checker)")
    st.markdown("[INCOSE Handbook](https://www.incose.org/products-and-publications/se-handbook)")

# Main title + API key capture (stored in session for all tabs)
st.title("✨ ReqCheck: AI-Powered Requirements Assistant")
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
api_key_input = st.text_input(
    "Enter your Google AI API Key to enable AI features:",
    type="password",
    value=st.session_state.api_key
)
if api_key_input:
    st.session_state.api_key = api_key_input


# ===================================================================
# Tabs: Document Analyzer, Need-to-Requirement Helper, Chatbot
# ===================================================================

tab1, tab2, tab3 = st.tabs(["📄 Document Analyzer", "💡 Need-to-Requirement Helper", "💬 Requirements Chatbot"])

# ------------------------------
# Tab 1: Document Analyzer
# ------------------------------
with tab1:
    st.header("Analyze a Requirements Document")

    # Upload your own file (.txt/.docx)
    uploaded_file = st.file_uploader("Upload your own requirements document", type=['txt', 'docx'])

    # Example file selection (if present locally)
    example_files = {
        "Choose an example...": None,
        "Drone System SRS (Complex Example)": "DRONE_SRS_v1.0.docx"
    }
    selected_example = st.selectbox("Or, select an example to get started:", options=list(example_files.keys()))

    # Internal store for parsed requirements
    requirements_list = []

    # Load example from disk if selected
    if selected_example != "Choose an example...":
        file_path = example_files[selected_example]
        try:
            # Read .docx or .txt based on extension
            if file_path.endswith('.docx'):
                doc = docx.Document(file_path)
                content = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            else:  # Assumes .txt
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            requirements_list = extract_requirements_from_string(content)
            st.info(f"Loaded example: **{selected_example}**")
        except FileNotFoundError:
            st.error(f"Example file not found: {file_path}. Please make sure it's in the main project folder.")

    # Or analyze an uploaded file
    elif uploaded_file is not None:
        with st.spinner('Analyzing document... Please wait.'):
            requirements_list = extract_requirements_from_file(uploaded_file)
        st.success(f"Analysis complete! Found {len(requirements_list)} requirements.")

    # Run full analysis and render results
    if requirements_list:
        # Analyze each requirement with your analyzer functions
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

        # Summary metrics
        total_reqs = len(requirements_list)
        flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
        if total_reqs > 0:
            clarity_score = calculate_clarity_score(total_reqs, flagged_reqs)
        else:
            clarity_score = 100

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Requirements", f"{total_reqs}")
        col2.metric("Flagged for Issues", f"{flagged_reqs}")
        col3.metric("Clarity Score", f"{clarity_score} / 100")
        st.progress(clarity_score)  # Using your current 0–100 usage
        if clarity_score >= 90:
            st.balloons()

        # Issue counts for bar chart (kept identical)
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

        # Word cloud of ambiguous words (kept as-is)
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

        # Per-requirement cards (flagged vs clear), with AI rewrite option
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
                        st.caption(f"ⓘ **Incompleteness:** Requirement appears to be a fragment.")
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
                    f'<div style="background-color: #D4EDDA; color: #155724; padding: 10px; '
                    f'border-radius: 5px; margin-bottom: 10px;">✅ <strong>{result["id"]}</strong> {result["text"]}</div>'
                )
                st.markdown(success_html, unsafe_allow_html=True)

        st.divider()
        st.header("Export Report")

        # Build export table with issue summary string
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
with tab2:
    st.header("Translate a Stakeholder Need into a Formal Requirement")
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
with tab3:
    st.header("Chat with an AI Systems Engineering Assistant")

    # Initialize chat history in session state once
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
            # Append user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Compose API history and query the assistant
            with st.spinner("AI is thinking..."):
                api_history = [{"role": msg["role"], "parts": [msg["content"]]} for msg in st.session_state.messages]
                response = get_chatbot_response(st.session_state.api_key, api_history)

                # Append assistant reply
                st.session_state.messages.append({"role": "assistant", "content": response})
                with st.chat_message("assistant"):
                    st.markdown(response)

