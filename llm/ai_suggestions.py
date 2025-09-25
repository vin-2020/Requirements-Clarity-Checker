# llm/ai_suggestions.py
"""
Lightweight helpers for ReqCheck's AI features (Gemini via google.generativeai).

IMPORTANT:
- Functionality is unchanged from your original file.
- Streamlit caching (@st.cache_data) is kept exactly as-is per your request.
- Prompts and model names are identical (except the new extractor's robust JSON prompt).
- Only formatting, structure, and comments/docstrings were improved.
"""

import streamlit as st
import google.generativeai as genai
import json
import re
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


# --- NEW: AI Requirement Extractor (full JSON-based, robust) ---
@st.cache_data
def extract_requirements_with_ai(
    api_key: str,
    document_text: str,
    max_chunk_chars: int = 12000
) -> List[Tuple[str, str]]:
    """
    Use the LLM to extract ONLY requirement statements from raw text.
    Returns: list of (req_id, req_text)

    - Strongly prefers STRICT JSON output from the model.
    - Handles documents without tables, mixed numbering, and narrative prose.
    - Falls back to heuristic extraction if JSON parsing fails.
    - Deduplicates by text (case-insensitive).
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        # Keep behavior consistent: return empty on config failure
        return []

    # ---- Chunk large documents on blank lines to stay well under context limits ----
    paras = re.split(r"\n\s*\n", document_text or "")
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

    # ---- Helper: parse model JSON or fallback ----
    def _parse_or_fallback(resp_text: str) -> List[Tuple[str, str]]:
        # Try to grab the last JSON object in the output
        json_text = None
        m = re.search(r"\{.*\}\s*$", resp_text or "", flags=re.S)
        if m:
            json_text = m.group(0)

        pairs: List[Tuple[str, str]] = []
        if json_text:
            try:
                data = json.loads(json_text)
                items = data.get("requirements", []) if isinstance(data, dict) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    rid = (item.get("id") or "").strip()
                    rtx = (item.get("text") or "").strip()
                    if rtx:
                        pairs.append((rid, rtx))
                if pairs:
                    return pairs
            except Exception:
                # fall through to heuristic
                pass

        # Heuristic fallback on the model output:
        # 1) Bullet/numbered lines
        heur_pairs: List[Tuple[str, str]] = []
        bullets = re.findall(r"^\s*(?:-|\*|\d+[\.\)])\s*(.+)$", resp_text or "", flags=re.M)
        for b in bullets:
            t = (b or "").strip()
            if t:
                heur_pairs.append(("", t))

        # 2) Normative sentences (look for optional ID and normative keywords)
        norm_pat = re.compile(
            r"""(?ix)
            ^
            (?:
                (?P<id>[A-Z][A-Z0-9-]*-\d+|[A-Z]{2,}\d+|\d+[\.\)])\s+    # e.g., ABC-123, SYS-001, 1., 1)
            )?
            (?P<text>.*?\b(shall|must|will|should)\b.*)
            $
            """
        )
        for line in (resp_text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            m2 = norm_pat.match(line)
            if m2:
                rid = (m2.group("id") or "").strip()
                txt = (m2.group("text") or "").strip()
                if txt:
                    heur_pairs.append((rid, txt))

        return heur_pairs

    # ---- Process each chunk with a strict-JSON prompt ----
    for ch in chunks if chunks else [""]:
        prompt = f"""
You are an expert Systems Engineer and requirements analyst.

Extract ONLY formal requirement statements from the TEXT below and output STRICT JSON with this exact schema (no extra commentary, no markdown, no prefixes/suffixes):

{{
  "requirements": [
    {{"id": "optional-id-or-empty", "text": "the requirement text (original phrasing, trimmed)"}}
  ]
}}

Extraction rules:
- Include normative, testable statements: contain "shall", "must", "will", or "should", or measurable constraints.
- Accept both formats:
  • Table/ID-based: e.g., "SYS-001 The system shall ..." or "SAT-REQ-12 The payload shall ..."
  • Narrative/numbered/bulleted: e.g., "1. The drone shall ..." or "- The controller will ..."
- Keep the original sentence wording except trimming bullets/numbering. Do not rewrite.
- If an explicit identifier exists (e.g., "SYS-001", "1."), put it in "id"; otherwise, use "" (empty string).
- Return VALID JSON ONLY. Do not add any text before or after the JSON.

TEXT:
\"\"\"{ch}\"\"\""""
        try:
            resp = model.generate_content(prompt)
            text_out = (resp.text or "").strip()
        except Exception:
            text_out = ""

        pairs = _parse_or_fallback(text_out)
        for rid, rtx in pairs:
            if not rtx:
                continue
            # If the model didn't provide an id, synthesize one (stable within this call)
            final_id = rid.strip() if rid.strip() else f"R-{running_index:03d}"
            out.append((final_id, rtx.strip()))
            running_index += 1

    # ---- If still empty, last-resort heuristic on the ORIGINAL document_text ----
    if not out and (document_text or "").strip():
        norm = re.compile(
            r'(?im)^(?:(?P<id>[A-Z][A-Z0-9-]*-\d+|\d+[.)])\s+)?(?P<txt>.*?\b(shall|must|will|should)\b.*)$'
        )
        idx = 1
        for line in (document_text or "").splitlines():
            m = norm.match(line.strip())
            if m:
                rid = (m.group("id") or f"R-{idx:03d}").strip()
                txt = (m.group("txt") or "").strip()
                if txt:
                    out.append((rid, txt))
                    idx += 1

    # ---- Deduplicate by requirement text (case-insensitive) ----
    seen = set()
    unique: List[Tuple[str, str]] = []
    for rid, txt in out:
        key = (txt or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append((rid, txt))

    return unique
