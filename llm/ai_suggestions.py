# llm/ai_suggestions.py
"""
Lightweight helpers for ReqCheck's AI features (Gemini via google.generativeai).

IMPORTANT:
- Functionality is unchanged from your original file.
- Streamlit caching (@st.cache_data) is kept exactly as-is per your request.
- Prompts and model names are identical.
- Only formatting, structure, and comments/docstrings were improved.
"""

import streamlit as st
import google.generativeai as genai
import json, re
from typing import List, Tuple


@st.cache_data
def get_ai_suggestion(api_key, requirement_text):
    """
    Ask Gemini to rewrite a requirement for clarity and testability.

    Parameters
    ----------
    api_key : str
        Google Generative AI API key.
    requirement_text : str
        The original requirement text to be rewritten.

    Returns
    -------
    str
        The model's rewritten requirement, or an error message.
    """
    try:
        # Configure Gemini client with the provided API key
        genai.configure(api_key=api_key)

        # Model choice kept exactly as in your original code
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Prompt kept identical to preserve behavior/outputs
        prompt = f"""
        You are an expert Systems Engineer following INCOSE standards. 
        Your task is to rewrite the following requirement to be more clear, specific, active, and measurable.
        
        Original Requirement: "{requirement_text}"
        
        Rewritten Requirement:
        """

        # Single-turn content generation
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        # Return string (not raising) to match existing behavior
        return f"An error occurred with the AI service: {e}"


@st.cache_data
def generate_requirement_from_need(api_key, need_text):
    """
    Convert an informal stakeholder need into a structured requirement
    or ask a clarifying question if the need is too vague.

    Parameters
    ----------
    api_key : str
        Google Generative AI API key.
    need_text : str
        Stakeholder need in plain language.

    Returns
    -------
    str
        A structured requirement or a clarifying question, or an error message.
    """
    try:
        # Configure Gemini client with the provided API key
        genai.configure(api_key=api_key)

        # Model choice kept exactly as in your original code
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Prompt kept identical to preserve behavior/outputs
        prompt = f"""
        You are a Systems Engineer creating a formal requirement from a stakeholder's informal need.
        Convert the following need into a structured requirement with the format:
        "[Condition], the [System/Actor] shall [Action] [Object] [Performance Metric]."

        If the need is too vague to create a full requirement, identify the missing pieces (like a measurable number or a clear action) and ask a clarifying question.

        Stakeholder Need: "{need_text}"

        Structured Requirement or Clarifying Question:
        """

        # Single-turn content generation
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        # Return string (not raising) to match existing behavior
        return f"An error occurred with the AI service: {e}"


@st.cache_data
def get_chatbot_response(api_key, chat_history):
    """
    Get a conversational reply from Gemini based on the entire chat history.

    NOTE: The format of `chat_history` is expected to be the same one your
    Streamlit app builds (e.g., a list of role/parts dicts or a compatible structure).
    This function forwards it directly to the model.

    Parameters
    ----------
    api_key : str
        Google Generative AI API key.
    chat_history : Any
        Conversation history object passed straight to model.generate_content().

    Returns
    -------
    str
        The assistant's response text, or an error message.
    """
    try:
        # Configure Gemini client with the provided API key
        genai.configure(api_key=api_key)

        # Model choice kept exactly as in your original code
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Directly pass the provided history (unchanged behavior)
        response = model.generate_content(chat_history)
        return response.text.strip()

    except Exception as e:
        # Return string (not raising) to match existing behavior
        return f"An error occurred with the AI service: {e}"


# --- NEW: AI Requirement Extractor (adds only this function; nothing else changed) ---
def extract_requirements_with_ai(api_key: str, raw_text: str, max_chunk_chars: int = 12000) -> List[Tuple[str, str]]:
    """
    Use the LLM to extract ONLY requirement statements from raw text.
    Returns: list of (req_id, req_text)
    """
    # 1) Split into reasonably sized chunks on blank lines
    paras = re.split(r'\n\s*\n', raw_text)
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 2 <= max_chunk_chars:
            buf += (p + "\n\n")
        else:
            if buf.strip():
                chunks.append(buf)
            buf = p + "\n\n"
    if buf.strip():
        chunks.append(buf)

    out: List[Tuple[str, str]] = []
    running_index = 1

    for ch in chunks:
        prompt = f"""
You are an expert requirements engineer.
Extract ONLY well-formed requirement statements from the text below.

Output STRICT JSON with this exact schema (no extra text):
{{
  "requirements": [
    {{"id": "optional-id-or-empty", "text": "the requirement text (original phrasing, trimmed)"}}
  ]
}}

Rules:
- Include only normative, testable statements (e.g., contain "shall", "must", "should", "will", or measurable constraints).
- Do not include explanations, headings, or non-requirement prose.
- Keep the original sentence wording except trimming numbering/bullets.
- If the source shows an identifier, keep it in "id"; else use "" (empty string).
- Return VALID JSON ONLY.

TEXT:
\"\"\"{ch}\"\"\"

JSON:
""".strip()

        resp = get_ai_suggestion(api_key, prompt)

        # Try to grab the last JSON object in the output
        json_text = None
        m = re.search(r'\{.*\}\s*$', resp, flags=re.S)
        if m:
            json_text = m.group(0)

        data = {"requirements": []}
        if json_text:
            try:
                data = json.loads(json_text)
            except Exception:
                # fall through to heuristic below
                pass

        if not data.get("requirements"):
            # Heuristic fallback: bullet lines -> requirements
            bullets = re.findall(r'^\s*(?:-|\*|\d+\.)\s*(.+)$', resp, flags=re.M)
            data = {"requirements": [{"id": "", "text": b.strip()} for b in bullets]}

        for item in data.get("requirements", []):
            rid = (item.get("id") or "").strip()
            rtx = (item.get("text") or "").strip()
            if not rtx:
                continue
            if not rid:
                rid = f"R-{running_index:03d}"
            out.append((rid, rtx))
            running_index += 1

    # Deduplicate by text (case-insensitive)
    seen = set()
    unique: List[Tuple[str, str]] = []
    for rid, txt in out:
        key = txt.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((rid, txt))
    return unique

