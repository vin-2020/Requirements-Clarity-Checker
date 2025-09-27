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
        model = genai.GenerativeModel('gemini-2.5-flash')

        # --- NEW, highly-detailed INCOSE-aligned prompt you provided ---
        prompt = f"""
        You are a lead Systems Engineer acting as a mentor. Your task is to review and rewrite a single requirement statement to make it exemplary.

        Follow these critical INCOSE-based principles for your rewrite:
        1.  **Verifiable:** The requirement must be testable. Replace subjective words (like "easy", "fast", "efficient") with specific, measurable criteria (like "within 500ms", "with 99.9% accuracy").
        2.  **Unambiguous:** The requirement must have only one possible interpretation. Use clear, direct language.
        3.  **Singular:** The requirement MUST state only a single capability. DO NOT use words like "and" or "or" to combine multiple requirements.
        4.  **Active Voice:** The requirement must be in the active voice (e.g., "The system shall...").
        5.  **Concise:** Remove unnecessary words like "be able to" or "be capable of".

        CRITICAL INSTRUCTION: Your final output must be ONLY the rewritten requirement sentence and nothing else. Do not add preambles like "Here is the rewritten requirement:".

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
        model = genai.GenerativeModel('gemini-2.5-flash')

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
        model = genai.GenerativeModel('gemini-2.5-flash')

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
        model = genai.GenerativeModel("gemini-2.5-flash")
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
    for ch in (chunks if chunks else [""]):

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


@st.cache_data
def decompose_requirement_with_ai(api_key, requirement_text):
    """
    Uses the Gemini LLM to decompose a complex requirement into multiple singular requirements.
    Returns a plain numbered list string.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""
        You are an expert Systems Engineer. Your task is to analyze the following requirement.
        If it is not singular, decompose it into a set of clear, singular, and verifiable requirements.

        CRITICAL INSTRUCTIONS:
        1. Analyze the original requirement to identify all distinct ideas (actions, constraints, metrics).
        2. Rewrite each idea as its own requirement in active voice: "The system shall ...".
        3. Each requirement must be a single sentence and testable.
        4. If the original requirement has an ID (e.g., "SYS-001"), assign incremental child IDs (e.g., "SYS-001.1", "SYS-001.2").
        5. Ensure **scope control**: do not add new conditions beyond the original requirement unless they are logically implied. If unsure, keep the decomposition minimal.
        6. Ensure **consistency**: separate system capability requirements from process/documentation requirements. Do not mix them in the same sentence.
        7. Ensure **normative language**: use "shall". Only upgrade "should" to "shall" if the intent is clearly mandatory.
        8. OUTPUT FORMAT: Return ONLY a numbered list, one item per line, with no extra commentary or markdown.

        Original Requirement: "{requirement_text}"
        """

        resp = model.generate_content(prompt)
        out = (getattr(resp, "text", "") or "").strip()
        return out if out else "No decomposition produced."
    except Exception as e:
        return f"An error occurred with the AI service: {e}"
# ------------------------------
# Structured helpers for Req Tutor (non-breaking additions)
# ------------------------------
import json
import re

def _extract_json_or_none(text: str):
    """Try to parse JSON; tolerate code fences and trailing prose."""
    if not text:
        return None
    # strip common fences
    m = re.search(r'\{.*\}', text, flags=re.DOTALL)
    candidate = m.group(0) if m else text.strip()
    try:
        return json.loads(candidate)
    except Exception:
        return None

def _kv_lines_to_dict(text: str) -> dict:
    """Fallback parser for 'Key: value' lines."""
    out = {}
    for line in (text or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip("-").strip()
            if k:
                out[k] = v
    return out

# Keys expected by template type
_NEED_AUTOFILL_FIELDS = {
    "Functional": ["Actor","Action","Object","Trigger","Conditions","Performance","ModalVerb"],
    "Performance": ["Function","Metric","Threshold","Unit","Conditions","Measurement","VerificationMethod"],
    "Constraint": ["Subject","ConstraintText","DriverOrStandard","Rationale"],
    "Interface": ["System","ExternalSystem","InterfaceStandard","Direction","DataItems","Performance","Conditions"],
}

@st.cache_data
def analyze_need_autofill(api_key: str, need_text: str, req_type: str) -> dict:
    """
    Return a dict with the fields required by the chosen requirement type.
    Uses Gemini directly with a strict JSON prompt + light post-processing.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
    except Exception:
        # fail-safe: return empty skeleton
        fields = _NEED_AUTOFILL_FIELDS.get(req_type or "Functional", _NEED_AUTOFILL_FIELDS["Functional"])
        return {k: "" for k in fields}

    req_type = (req_type or "Functional").strip()
    fields = _NEED_AUTOFILL_FIELDS.get(req_type, _NEED_AUTOFILL_FIELDS["Functional"])

    # Few-shot anchors
    if req_type == "Functional":
        fewshot = """Example (Functional, JSON only):
{"Actor":"UAV","Action":"present","Object":"low-battery alert to operator","Trigger":"battery state-of-charge < 20%","Conditions":"in all flight modes","Performance":"within 1 s","ModalVerb":"shall"}"""
    elif req_type == "Performance":
        fewshot = """Example (Performance, JSON only):
{"Function":"position estimator","Metric":"RMSE","Threshold":"1.5","Unit":"m","Conditions":"steady hover","Measurement":"flight log analysis","VerificationMethod":"Analysis"}"""
    elif req_type == "Constraint":
        fewshot = """Example (Constraint, JSON only):
{"Subject":"avionics enclosure","ConstraintText":"IP65 ingress protection","DriverOrStandard":"IEC 60529","Rationale":"dust and water resistance for field ops"}"""
    else:
        fewshot = """Example (Interface, JSON only):
{"System":"flight computer","ExternalSystem":"ground control station","InterfaceStandard":"MAVLink v2","Direction":"Bi-directional","DataItems":"heartbeat, position, battery_status","Performance":"latency ≤ 150 ms","Conditions":"nominal flight modes"}"""

    prompt = f"""
You are assisting a systems engineer. Given this stakeholder need, produce a FIRST-DRAFT for a {req_type} requirement.

NEED:
\"\"\"{(need_text or '').strip()}\"\"\"\n
Return ONLY a VALID JSON object with EXACTLY these keys (no extra text, no code fences):
{json.dumps(fields)}

Guidance:
- Map scenario context into fields (e.g., contested airspace, stealth/avoiding detection, mission completion/return).
- Keep Object as the thing acted on (do NOT include metrics or percentages in Object).
- Put numbers/thresholds/units in Performance (or Threshold/Unit for Performance type).
- Prefer an EARS style (use Trigger/Conditions when implied).
- Avoid vague phrases: "all specified", "as soon as possible", "as needed", "etc.", "including but not limited to".
- ModalVerb should usually be "shall".
- VerificationMethod (if present): one of "Test","Analysis","Inspection","Demonstration".

{fewshot}
"""

    try:
        resp = model.generate_content(prompt)
        raw = (getattr(resp, "text", "") or "").strip()
    except Exception:
        raw = ""

    # Parse JSON strictly; fallback to Key: value lines
    data = _extract_json_or_none(raw)
    if data is None or not isinstance(data, dict):
        data = _kv_lines_to_dict(raw)

    # Build skeleton and copy values
    out = {k: (data.get(k, "") if isinstance(data, dict) else "") for k in fields}

    # --------- Light post-processing for quality ----------
    def _ban_vague_phrases(txt: str) -> str:
        banned = ["all specified", "as needed", "as soon as possible", "etc.", "including but not limited to"]
        t = (txt or "")
        for b in banned:
            t = t.replace(b, "").strip()
        return t

    def _strip_perf_from_object(obj: str, perf: str) -> tuple[str, str]:
        o = (obj or "").strip()
        p = (perf or "").strip()
        if not o:
            return o, p
        patterns = [
            r'\bwith (a )?probability of\s*[0-9]*\.?[0-9]+%?',
            r'\b(minimum|maximum|at least|no more than)\s*[0-9]*\.?[0-9]+%?\b',
            r'\b\d+(\.\d+)?\s*(ms|s|sec|m|km|hz|khz|mhz|kbps|mbps|gbps|fps)\b',
            r'\b\d+(\.\d+)?\s*%(\b|$)'
        ]
        extracted = []
        for rx in patterns:
            m = re.search(rx, o, flags=re.IGNORECASE)
            if m:
                extracted.append(m.group(0).strip())
                o = (o[:m.start()] + o[m.end():]).strip().strip(',. ')
        if extracted:
            extra = " ".join(extracted)
            if p:
                if extra not in p:
                    p = f"{p}; {extra}"
            else:
                p = extra
        return o, p

    need_lower = (need_text or "").lower()
    def _maybe_push_context_to_conditions(conds: str) -> str:
        bits = []
        if "contested airspace" in need_lower and "contested airspace" not in (conds or "").lower():
            bits.append("in contested airspace")
        if "avoiding detection" in need_lower and "avoid" not in (conds or "").lower():
            bits.append("while minimizing detectability by adversary sensors")
        if "return" in need_lower and "return" not in (conds or "").lower():
            bits.append("and return safely to base")
        if bits:
            return (f"{conds} " + " ".join(bits)).strip() if conds else " ".join(bits)
        return conds

    # Enums normalization
    if "ModalVerb" in out:
        mv = (out["ModalVerb"] or "shall").lower()
        out["ModalVerb"] = mv if mv in ("shall","will","must") else "shall"
    if "VerificationMethod" in out:
        vm = (out["VerificationMethod"] or "").title()
        out["VerificationMethod"] = vm if vm in ("Test","Analysis","Inspection","Demonstration") else "Test"
    if "Direction" in out:
        dr = (out["Direction"] or "")
        out["Direction"] = dr if dr in ("In","Out","Bi-directional") else "Bi-directional"

    # Apply quality polish by type
    if req_type == "Functional":
        out["Object"], out["Performance"] = _strip_perf_from_object(out.get("Object",""), out.get("Performance",""))
        out["Object"] = _ban_vague_phrases(out.get("Object",""))
        out["Conditions"] = _maybe_push_context_to_conditions(out.get("Conditions",""))
    elif req_type == "Performance":
        out["Function"] = _ban_vague_phrases(out.get("Function",""))
    elif req_type == "Interface":
        out["DataItems"] = _ban_vague_phrases(out.get("DataItems",""))
    elif req_type == "Constraint":
        out["ConstraintText"] = _ban_vague_phrases(out.get("ConstraintText",""))

    return out


def review_requirement_with_ai(api_key: str, requirement_text: str, preferred_verification: str | None = None) -> dict:
    """
    Return {"review": str, "acceptance": [str, ...]}.
    JSON-first with graceful fallback if the model emits text.
    """
    pv = preferred_verification if preferred_verification in ("Test","Analysis","Inspection","Demonstration") else ""
    hint = f' "preferredVerification": "{pv}",' if pv else ""

    prompt = f"""
Act as a systems engineering reviewer. Evaluate the requirement and propose precise, testable acceptance criteria.

Return ONLY this JSON (no extra text, no code fences):
{{
  "review": "short critique focusing on ambiguity, measurability, singularity, feasibility",
  {hint}
  "acceptance": [
    "bullet 1 with threshold(s), setup/conditions, verification method",
    "bullet 2 ..."
  ]
}}

Requirement:
\"\"\"{(requirement_text or '').strip()}\"\"\"
"""

    raw = get_ai_suggestion(api_key, prompt)
    data = _extract_json_or_none(raw)
    if not isinstance(data, dict):
        # fallback: wrap the raw text as a single acceptance block
        return {"review": raw.strip(), "acceptance": []}

    # shape and defaults
    review = str(data.get("review", "")).strip()
    acceptance = data.get("acceptance", [])
    if not isinstance(acceptance, list):
        acceptance = [str(acceptance)]
    acceptance = [str(x).strip() for x in acceptance if str(x).strip()]
    return {"review": review, "acceptance": acceptance}
