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
from llm.ai_suggestions import get_ai_suggestion, generate_requirement_from_need

# --- FINAL, CORRECTED PARSER FUNCTION ---
def extract_requirements_from_file(uploaded_file):
    """
    Reads a file and uses a robust regex to extract requirement lines with various ID formats.
    """
    requirements = []
    # This pattern is now more specific to prevent matching divider lines.
    # It looks for IDs starting with letters and numbers, followed by a hyphen or period.
    req_pattern = re.compile(r'^([A-Z0-9\.-]+)\s+(.*)')

    if uploaded_file.name.endswith('.txt'):
        lines = uploaded_file.getvalue().decode("utf-8").split('\n')
        for line in lines:
            line = line.strip()
            # We add a condition to explicitly ignore lines that start with '---'
            if line.startswith('---'):
                continue
            if match := req_pattern.match(line):
                requirements.append((match.group(1), match.group(2)))

    elif uploaded_file.name.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        for para in doc.paragraphs:
            line = para.text.strip()
            if line.startswith('---'):
                continue
            if match := req_pattern.match(line):
                requirements.append((match.group(1), match.group(2)))
                
    return requirements

def format_requirement_with_highlights(req_id, req_text, issues):
    """Formats a requirement with HTML for highlighting issues."""
    highlighted_text = req_text
    if issues['ambiguous']:
        for word in issues['ambiguous']:
            highlighted_text = re.sub(r'\b' + re.escape(word) + r'\b', f'<span style="background-color: #FFFF00; color: black; padding: 2px 4px; border-radius: 3px;">{word}</span>', highlighted_text, flags=re.IGNORECASE)
    if issues['passive']:
        for phrase in issues['passive']:
            highlighted_text = re.sub(re.escape(phrase), f'<span style="background-color: #FFA500; padding: 2px 4px; border-radius: 3px;">{phrase}</span>', highlighted_text, flags=re.IGNORECASE)
    
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
    return f'<div style="background-color: #FFF3CD; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 10px;">{display_html}</div>'

st.set_page_config(page_title="ReqCheck v2.0", page_icon="✨", layout="wide")
with st.sidebar:
    st.image("https://github.com/vin-2020/Requirements-Clarity-Checker/blob/main/ReqCheck_LOGO.png?raw=true", use_container_width=True)
    st.header("About ReqCheck")
    st.info("An AI-assisted tool to evaluate the quality of system requirements...")
    st.header("Project Links")
    st.markdown("[GitHub Repository](https://github.com/vin-2020/Requirements-Clarity-Checker)")
    st.markdown("[INCOSE Handbook](https://www.incose.org/products-and-publications/se-handbook)")

st.title("✨ ReqCheck: AI-Powered Requirements Assistant")
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
api_key_input = st.text_input("Enter your Google AI API Key to enable AI features:", type="password", value=st.session_state.api_key)
if api_key_input:
    st.session_state.api_key = api_key_input

tab1, tab2 = st.tabs(["📄 Document Analyzer", "💡 Need-to-Requirement Helper"])

with tab1:
    st.header("Analyze a Requirements Document")
    uploaded_file = st.file_uploader("Choose a requirements document", type=['txt', 'docx'])

    if uploaded_file is not None:
        with st.spinner('Analyzing document... Please wait.'):
            requirements_list = extract_requirements_from_file(uploaded_file)
        
        st.success(f"Analysis complete! Found {len(requirements_list)} requirements.")
        
        if not requirements_list:
            st.error("No valid requirements found.")
        else:
            results = []
            for req_id, req_text in requirements_list:
                ambiguous_words = check_requirement_ambiguity(req_text)
                passive_phrases = check_passive_voice(req_text)
                is_incomplete = check_incompleteness(req_text)
                results.append({'id': req_id, 'text': req_text, 'ambiguous': ambiguous_words, 'passive': passive_phrases, 'incomplete': is_incomplete})
            
            st.divider()
            st.header("Analysis Summary")
            
            total_reqs = len(requirements_list)
            flagged_reqs = sum(1 for r in results if r['ambiguous'] or r['passive'] or r['incomplete'])
            col1, col2 = st.columns(2)
            with col1:
                if total_reqs > 0:
                    clarity_score = calculate_clarity_score(total_reqs, flagged_reqs)
                    st.metric(label="Overall Clarity Score", value=f"{clarity_score} / 100")
                    st.progress(clarity_score)
                    if clarity_score >= 90: st.balloons()
            with col2:
                issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0}
                for res in results:
                    if res['ambiguous']: issue_counts["Ambiguity"] += 1
                    if res['passive']: issue_counts["Passive Voice"] += 1
                    if res['incomplete']: issue_counts["Incompleteness"] += 1
                st.subheader("Issues by Type")
                st.bar_chart(issue_counts)
            
            all_ambiguous_words = []
            for res in results:
                if res['ambiguous']: all_ambiguous_words.extend(res['ambiguous'])
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
            
            for result in results:
                is_flagged = result['ambiguous'] or result['passive'] or result['incomplete']
                
                if is_flagged:
                    with st.container(border=True):
                        formatted_html = format_requirement_with_highlights(result['id'], result['text'], result)
                        st.markdown(formatted_html, unsafe_allow_html=True)
                        if result['ambiguous']: st.caption(f"ⓘ **Ambiguity:** Found weak words: **{', '.join(result['ambiguous'])}**.")
                        if result['passive']: st.caption(f"ⓘ **Passive Voice:** Found phrase: **'{', '.join(result['passive'])}'**. Consider active voice.")
                        if result['incomplete']: st.caption(f"ⓘ **Incompleteness:** Requirement appears to be a fragment.")
                        
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
                    success_html = f'<div style="background-color: #D4EDDA; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 10px;">✅ <strong>{result["id"]}</strong> {result["text"]}</div>'
                    st.markdown(success_html, unsafe_allow_html=True)
            
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
            st.download_button(
                label="Download Report as CSV",
                data=csv,
                file_name=f"ReqCheck_Report_{uploaded_file.name}.csv",
                mime="text/csv",
            )

with tab2:
    st.header("Translate a Stakeholder Need into a Formal Requirement")
    need_input = st.text_area("Enter a stakeholder need:", height=100, placeholder="e.g., I need to see the drone's location on a map.")
    
    if st.button("Generate Requirement"):
        if not st.session_state.api_key:
            st.warning("Please enter your Google AI API Key at the top of the page.")
        elif not need_input:
            st.error("Please enter a stakeholder need.")
        else:
            with st.spinner("AI is thinking..."):
                generated_req = generate_requirement_from_need(st.session_state.api_key, need_input)
                st.info("AI Generated Suggestion:")
                st.markdown(generated_req)
