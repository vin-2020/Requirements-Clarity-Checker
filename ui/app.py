import streamlit as st
import sys
import os
import docx
import re
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.analyzer import check_requirement_ambiguity, check_passive_voice, check_incompleteness
from core.scoring import calculate_clarity_score

# All other functions (extract_requirements_from_file) remain the same.
def extract_requirements_from_file(uploaded_file):
    """Reads an uploaded file and uses regex to extract requirement lines."""
    requirements = []
    req_pattern = re.compile(r'^((?:REQ-\d+)|(?:\d+\.))\s+(.*)')
    if uploaded_file.name.endswith('.txt'):
        lines = uploaded_file.getvalue().decode("utf-8").split('\n')
        for line in lines:
            line = line.strip()
            match = req_pattern.match(line)
            if match:
                requirements.append((match.group(1), match.group(2)))
    elif uploaded_file.name.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        for para in doc.paragraphs:
            line = para.text.strip()
            match = req_pattern.match(line)
            if match:
                requirements.append((match.group(1), match.group(2)))
    return requirements

# --- CORRECTED HELPER FUNCTION FOR HIGHLIGHTING & DETAILS ---
def format_requirement_with_highlights(req_id, req_text, issues):
    """
    Takes a requirement and its issues, and returns an HTML string with issues 
    highlighted AND a list of explanations.
    """
    highlighted_text = req_text
    
    # Highlight ambiguous words in yellow
    if issues['ambiguous']:
        for word in issues['ambiguous']:
            highlighted_text = re.sub(r'\b' + re.escape(word) + r'\b', f'<span style="background-color: #FFFF00; padding: 2px 4px; border-radius: 3px;">{word}</span>', highlighted_text, flags=re.IGNORECASE)

    # Highlight passive phrases in orange
    if issues['passive']:
        for phrase in issues['passive']:
            highlighted_text = re.sub(re.escape(phrase), f'<span style="background-color: #FFA500; padding: 2px 4px; border-radius: 3px;">{phrase}</span>', highlighted_text, flags=re.IGNORECASE)
    
    # Create the main text with a warning icon
    display_html = f"⚠️ <strong>{req_id}</strong> {highlighted_text}"
    
    # --- THIS IS THE CORRECTED LOGIC ---
    # Build a list of all explanations
    explanations = []
    if issues['ambiguous']:
        explanations.append(f"<i>- Ambiguity: Found weak words: <b>{', '.join(issues['ambiguous'])}</b></i>")
    if issues['passive']:
        explanations.append(f"<i>- Passive Voice: Found phrase: <b>'{', '.join(issues['passive'])}'</b>. Consider active voice.</i>")
    if issues['incomplete']:
        explanations.append("<i>- Incompleteness: Requirement appears to be a fragment.</i>")
    
    # Add the explanations below the main text
    if explanations:
        display_html += "<br>" + "<br>".join(explanations)
        
    # Wrap everything in a styled box
    return f'<div style="background-color: #FFF3CD; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 10px;">{display_html}</div>'

# --- Page Configuration & Sidebar (No Changes) ---
st.set_page_config(page_title="ReqCheck v1.0", page_icon="✅", layout="wide")
with st.sidebar:
    st.header("About ReqCheck")
    st.info("An AI-assisted tool to evaluate the quality of system requirements...")
    st.header("Project Links")
    st.markdown("[GitHub Repository](https://github.com/vin-2020/Requirements-Clarity-Checker)")
    st.markdown("[INCOSE Handbook](https://www.incose.org/products-and-publications/se-handbook)")

# --- Main Page (No changes until the final loop) ---
st.title("✅ ReqCheck: Requirement Clarity Checker")
st.write("Upload your system requirements document (.txt or .docx) to begin analysis.")

uploaded_file = st.file_uploader("Choose a requirements document", type=['txt', 'docx'])

if uploaded_file is not None:
    with st.spinner('Analyzing document... Please wait.'):
        requirements_list = extract_requirements_from_file(uploaded_file)
    
    st.success(f"Analysis complete! Found {len(requirements_list)} requirements.")
    
    if not requirements_list:
        st.error("No valid requirements found.")
    else:
        # --- Analysis Loop (No changes here) ---
        issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0}
        results = []
        all_ambiguous_words = []
        for req_id, req_text in requirements_list:
            ambiguous_words = check_requirement_ambiguity(req_text)
            passive_phrases = check_passive_voice(req_text)
            is_incomplete = check_incompleteness(req_text)
            if ambiguous_words:
                all_ambiguous_words.extend(ambiguous_words)
            if ambiguous_words: issue_counts["Ambiguity"] += 1
            if passive_phrases: issue_counts["Passive Voice"] += 1
            if is_incomplete: issue_counts["Incompleteness"] += 1
            results.append({'id': req_id, 'text': req_text, 'ambiguous': ambiguous_words, 'passive': passive_phrases, 'incomplete': is_incomplete})

        # --- Summary Section (No changes here) ---
        st.divider()
        st.header("Analysis Summary")
        total_reqs = len(requirements_list)
        flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
        col1, col2 = st.columns(2)
        with col1:
            if total_reqs > 0:
                clarity_score = calculate_clarity_score(total_reqs, issue_counts)
                st.metric(label="Overall Clarity Score", value=f"{clarity_score} / 100")
                st.progress(clarity_score)
                if clarity_score >= 90:
                    st.balloons()
        with col2:
            st.subheader("Issues by Type")
            st.bar_chart(issue_counts)
        st.subheader("Common Weak Words Found")
        if all_ambiguous_words:
            text_for_cloud = ' '.join(all_ambiguous_words)
            wordcloud = WordCloud(width=800, height=300, background_color='white', collocations=False).generate(text_for_cloud)
            fig, ax = plt.subplots()
            ax.imshow(wordcloud, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)

        st.divider()
        st.header(f"Detailed Analysis")
        
        # --- Display Loop (No changes here, it uses the corrected formatter function) ---
        for result in results:
            is_flagged = result['ambiguous'] or result['passive'] or result['incomplete']
            
            if is_flagged:
                formatted_html = format_requirement_with_highlights(result['id'], result['text'], result)
                st.markdown(formatted_html, unsafe_allow_html=True)
            else:
                success_html = f'<div style="background-color: #D4EDDA; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 10px;">✅ <strong>{result["id"]}</strong> {result["text"]}</div>'
                st.markdown(success_html, unsafe_allow_html=True)
        
        # --- Export Section (No Changes here) ---
        st.divider()
        st.header("Export Report")
        export_data = []
        for result in results:
            issues = []
            if result['ambiguous']: issues.append(f"Ambiguity: {', '.join(result['ambiguous'])}")
            if result['passive']: issues.append(f"Passive Voice: {', '.join(result['passive'])}")
            if result['incomplete']: issues.append("Incompleteness: Missing verb.")
            export_data.append({"ID": result['id'], "Requirement Text": result['text'], "Status": "Clear" if not issues else "Flagged", "Issues Found": "; ".join(issues)})
        df = pd.DataFrame(export_data)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download Report as CSV", data=csv, file_name=f"ReqCheck_Report_{uploaded_file.name}.csv", mime="text/csv")
