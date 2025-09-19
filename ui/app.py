import streamlit as st
import sys
import os
import docx

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import both of our analyzer functions
from core.analyzer import check_requirement_ambiguity, check_passive_voice

def extract_requirements_from_file(uploaded_file):
    """Reads an uploaded file and returns a list of requirements."""
    requirements = []
    if uploaded_file.name.endswith('.txt'):
        string_data = uploaded_file.getvalue().decode("utf-8")
        requirements = [line.strip() for line in string_data.split('\n') if line.strip()]
    elif uploaded_file.name.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        for para in doc.paragraphs:
            if para.text.strip():
                requirements.append(para.text.strip())
    return requirements

# --- Page Configuration ---
st.set_page_config(page_title="ReqCheck v1.0", page_icon="✅", layout="wide")

# --- Sidebar ---
with st.sidebar:
    st.header("About ReqCheck")
    st.info("An AI-assisted tool to evaluate the quality of system requirements, aligned with INCOSE standards.")
    st.header("Project Links")
    st.markdown("[GitHub Repository](https://your-github-repo-link-here)")
    st.markdown("[INCOSE Handbook](https://www.incose.org/products-and-publications/se-handbook)")

# --- Main Page ---
st.title("✅ ReqCheck: Requirement Clarity Checker")
st.write("Upload your system requirements document (.txt or .docx) to begin analysis.")

uploaded_file = st.file_uploader("Choose a requirements document", type=['txt', 'docx'])

if uploaded_file is not None:
    st.success(f"File '{uploaded_file.name}' uploaded successfully. Analyzing...")
    
    requirements_list = extract_requirements_from_file(uploaded_file)
    
    if not requirements_list:
        st.error("No requirements found in the uploaded file.")
    else:
        # --- NEW CODE: Logic for counting issues and creating the graph ---
        # 1. Initialize counters for our charts
        issue_counts = {"Ambiguity": 0, "Passive Voice": 0}
        total_reqs = len(requirements_list)
        flagged_reqs = 0

        # We need to store results to display them after the summary
        results = []

        # Analyze all requirements first to get summary data
        for req_text in requirements_list:
            ambiguous_words = check_requirement_ambiguity(req_text)
            passive_phrases = check_passive_voice(req_text)
            
            is_flagged = False
            if ambiguous_words:
                issue_counts["Ambiguity"] += 1
                is_flagged = True
            if passive_phrases:
                issue_counts["Passive Voice"] += 1
                is_flagged = True
            
            if is_flagged:
                flagged_reqs += 1
            
            results.append({'text': req_text, 'ambiguous': ambiguous_words, 'passive': passive_phrases})

        st.divider()
        st.header("Analysis Summary")

        # 2. Display summary metrics and the bar chart
        col1, col2 = st.columns(2)
        with col1:
            clarity_score = int(((total_reqs - flagged_reqs) / total_reqs) * 100)
            st.metric(label="Overall Clarity Score", value=f"{clarity_score} / 100")
            st.progress(clarity_score)
        with col2:
            st.subheader("Issues by Type")
            st.bar_chart(issue_counts)
        # --- END OF NEW CODE ---

        st.divider()
        st.header("Detailed Analysis")
        
        # 3. Loop through the stored results and display them
        for i, result in enumerate(results, 1):
            is_flagged = result['ambiguous'] or result['passive']
            
            if is_flagged:
                st.warning(f"**REQ-{i:03}:** {result['text']}")
                if result['ambiguous']:
                    st.info(f"   - **Ambiguity:** Found weak words: **{', '.join(result['ambiguous'])}**")
                if result['passive']:
                    st.info(f"   - **Passive Voice:** Found phrase: **'{', '.join(result['passive'])}'**. Consider active voice.")
            else:
                st.success(f"**REQ-{i:03}:** {result['text']}")