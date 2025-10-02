# ui/tabs/need_tab.py
from __future__ import annotations

import re
import time
from typing import Callable
import pandas as pd
import streamlit as st

# -------- Streamlit rerun compatibility (new & old) --------
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

# ----------------- Resilient LLM wrapper -------------------
def _llm_retry(api_fn: Callable[[str], str], prompt: str, retries: int = 2, backoff: float = 0.8) -> str:
    def retriable(msg: str) -> bool:
        m = (msg or "").lower()
        return any(x in m for x in ["429", "quota", "rate", "timeout", "500", "503", "internal"])
    last = ""
    for i in range(retries + 1):
        try:
            out = api_fn(prompt) or ""
            if retriable(out):
                raise RuntimeError(out)
            return out.strip()
        except Exception as e:
            last = str(e)
            if i < retries and retriable(last):
                time.sleep(backoff * (i + 1))
                continue
            st.warning(f"AI service error: {last}. Using local fallback.")
            return ""

# ----------------- Domain fallbacks ------------------------
def _thermal_questions_with_examples() -> list[str]:
    return [
        "What temperature limits apply per subsystem and location? → e.g., Batteries: 0–40 °C; Avionics: −10–50 °C; Payload optics: T_nom ±2 °C.",
        "Under which modes/conditions must limits hold? → e.g., Eclipse, full sun, payload on, comm windows, safe mode.",
        "What time-at-limit and averaging windows apply? → e.g., ≤30 s excursion; 60 s rolling average.",
        "What heater/cooler power budgets apply? → e.g., Heaters ≤10 W average per orbit; radiator area TBD_m².",
        "Which environments/disturbances are assumed? → e.g., SRP, thermal cycling, internal dissipation TBD_W.",
        "How is compliance verified across lifecycle? → e.g., TVAC test, thermal model correlation, in-orbit telemetry trending.",
        "What contingencies/faults must be handled? → e.g., sensor failure, heater open/short, unexpected thermal spike.",
        "What control/estimation update rates are required? → e.g., thermal control loop TBD_Hz; telemetry sample ≥1 Hz.",
    ]

def _thermal_parent_from_need(_: str) -> str:
    return "The System shall maintain onboard component temperatures within specified operational limits throughout the mission duration."

def _thermal_children_default() -> list[str]:
    return [
        "The System shall regulate battery temperatures between 0 °C and 40 °C during all mission phases.",
        "The System shall maintain payload optics within ±2 °C of nominal during active imaging sessions.",
        "The System shall ensure avionics boards remain within −10 °C to 50 °C during eclipse and full sun.",
        "The System shall limit heater average power to ≤ 10 W per orbit while meeting thermal limits.",
        "The System shall detect and log thermal excursions > TBD_°C lasting > 30 s and flag a fault.",
        "Thermal compliance shall be verified by TVAC testing, correlated thermal analysis, and in-orbit telemetry review.",
    ]

def _uas_questions_with_examples() -> list[str]:
    return [
        "What mission profiles and environments apply? → e.g., urban BVLOS, over-water, Class G airspace, wind ≤12 m/s.",
        "What performance thresholds define success? → e.g., endurance ≥45 min; payload mass ≤2 kg; range ≥15 km.",
        "What command-and-control and link requirements apply? → e.g., C2 link ≥99.5% availability; latency ≤200 ms.",
        "What navigation and geo-fencing limits apply? → e.g., RTH on GNSS loss; fence radius TBD_m; altitude ≤120 m AGL.",
        "What safety/redundancy requirements apply? → e.g., parachute deploy under loss-of-thrust; detect-and-avoid class TBD.",
        "What GCS human-factors constraints apply? → e.g., UI alerts within 1 s; max operator workload TBD.",
        "What regulatory/airworthiness constraints apply? → e.g., Part 107/CAA equivalent; remote ID compliance.",
        "How will performance be verified? → e.g., flight test matrix, SIL/HIL, log analysis.",
    ]

def _uas_parent_from_need(_: str) -> str:
    return "The System shall provide an Unmanned Aerial Vehicle and Ground Control Station that achieve the specified mission performance and safety constraints."

def _uas_children_default() -> list[str]:
    return [
        "The UAV shall achieve flight endurance ≥ TBD_min under nominal payload and wind conditions.",
        "The System shall maintain C2 link availability ≥ TBD_% with one-way latency ≤ TBD_ms.",
        "The UAV shall enforce geo-fencing with horizontal error ≤ TBD_m and altitude error ≤ TBD_m AGL.",
        "The System shall provide return-to-home on GNSS loss or link loss within ≤ TBD_s detection time.",
        "The UAV shall carry payload mass up to TBD_kg without exceeding takeoff weight limits.",
        "The GCS shall present critical alerts within ≤ TBD_s of trigger and log them with timestamps.",
        "The System shall comply with TBD_regulatory framework including Remote ID and operational constraints.",
    ]

# ----------------- Generic fallbacks ------------------------
def _generic_questions_with_examples() -> list[str]:
    return [
        "What metric(s) define success with units and thresholds? → e.g., ≤ TBD_unit.",
        "Under which modes/conditions must this hold? → e.g., nominal, safe, maintenance.",
        "What timing/resource limits apply? → e.g., ≤ TBD_s; ≤ TBD_W.",
        "What environment assumptions/disturbances apply? → e.g., vibration, radiation, SRP.",
        "How will compliance be verified? → e.g., Test/Analysis/Inspection/Demo.",
        "What contingencies/faults must be handled? → e.g., sensor/actuator failure.",
    ]

def _fallback_parent(_: str) -> str:
    return "The System shall achieve the stated objective under specified conditions."

def _fallback_children() -> list[str]:
    return [
        "The System shall meet TBD_metric ≤ TBD_value TBD_unit under TBD_conditions.",
        "Compliance shall be verified by TBD_Method.",
    ]

# ----------------- Need normalizer --------------------------
_NEED_SHALL_RX = re.compile(r"\b(shall|must|will)\b", re.I)

def _normalize_need(raw: str) -> str:
    txt = (raw or "").strip()
    if not txt:
        return ""
    if _NEED_SHALL_RX.search(txt):
        txt_no_modal = re.sub(r"\b(the\s+)?(system|uav|vehicle|spacecraft|satellite|platform)\b\s+(shall|must|will)\s+", "", txt, flags=re.I)
        txt_no_modal = re.sub(r"\b(shall|must|will)\s+", "", txt_no_modal, flags=re.I)
        txt = re.sub(r"^\s*(to\s+)?", "", txt_no_modal).strip()
        if not re.match(r"^(enable|provide|maintain|perform|achieve|support)\b", txt, re.I):
            txt = "Enable " + txt[0].lower() + txt[1:]
    txt = re.sub(r"\s+", " ", txt)
    return txt.rstrip(" .")

# ----------------- Domain routing ---------------------------
def _detect_domain(need: str) -> str:
    low = (need or "").lower()
    if any(k in low for k in ["thermal", "temperature", "heater", "radiator", "eclipse", "sun", "tvac"]):
        return "thermal"
    if any(k in low for k in ["uav", "uas", "drone", "gcs", "unmanned", "ground control station"]):
        return "uas"
    return "generic"

# ----------------- Render Tab -------------------------------
def render(st, db, rule_engine, CTX):
    """
    Need → Questions (with → e.g.) → Requirements (strict look & feel).
    - One-click generation (AI + robust fallbacks) with NEED sanitizer.
    - Auto single vs parent→children vs group-of-standalone requirements.
    - Editable IDs & text; Rewrite; Decompose only when non-singular; Structured dropdown editor; Delete.
    - Per-item V&V/traceability: Verification Method/Level/Evidence, Validation Need ID, Test Case IDs, Allocated To, plus Status & Criticality.
    - CSV export includes all new fields.
    """

    # Analyzer & LLM hooks
    safe_call_ambiguity = CTX.get("safe_call_ambiguity", lambda t, e=None: [])
    check_passive_voice = CTX.get("check_passive_voice", lambda t: [])
    check_incompleteness = CTX.get("check_incompleteness", lambda t: [])
    check_singularity = CTX.get("check_singularity", lambda t: [])
    get_ai_suggestion = CTX.get("get_ai_suggestion", lambda *a, **k: "")
    decompose_requirement_with_ai = CTX.get("decompose_requirement_with_ai", lambda *a, **k: "")

    # ---------- State ----------
    if "need_ui" not in st.session_state:
        st.session_state.need_ui = {}
    S = st.session_state.need_ui
    S.setdefault("req_type", "Functional")
    S.setdefault("priority", "Should")
    S.setdefault("lifecycle", "Operations")
    S.setdefault("stakeholder", "")
    S.setdefault("need_text", "")
    S.setdefault("rationale", "")
    S.setdefault("ai_questions", [])
    S.setdefault("requirements", [])
    S.setdefault("child_counts", {})  # parent_id -> next int
    S.setdefault("need_id", "NEED-001")  # NEW: Need ID for validation/traceability

    # ---------- Header ----------
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    st.header("✍️ Need → Requirement Assistant" + (f" — Project: {pname}" if pname else ""))

    # ---------- Top controls ----------
    c_top = st.columns(5)
    with c_top[0]:
        S["req_type"] = st.selectbox("Requirement Type",
                                     ["Functional", "Performance", "Constraint", "Interface"],
                                     index=["Functional", "Performance", "Constraint", "Interface"].index(S["req_type"]))
    with c_top[1]:
        S["priority"] = st.selectbox("Priority", ["Must", "Should", "Could", "Won't (now)"],
                                     index=["Must", "Should", "Could", "Won't (now)"].index(S["priority"]))
    with c_top[2]:
        S["lifecycle"] = st.selectbox("Life-cycle",
                                      ["Concept", "Development", "P/I/V&V", "Operations", "Maintenance", "Disposal"],
                                      index=["Concept", "Development", "P/I/V&V", "Operations", "Maintenance", "Disposal"].index(S["lifecycle"]))
    with c_top[3]:
        S["stakeholder"] = st.text_input("Stakeholder / Role", value=S["stakeholder"],
                                         placeholder="e.g., Flight operator, Acquirer")
    with c_top[4]:
        S["need_id"] = st.text_input("Need ID", value=S["need_id"], help="Used for Validation link & traceability (e.g., NEED-001)")

    # ---------- Need & Rationale ----------
    st.subheader("🧩 Stakeholder Need")
    S["need_text"] = st.text_area(
        "Describe the need (no 'shall')",
        value=S["need_text"],
        height=110,
        placeholder="e.g., Maintain onboard component temperatures within operational limits throughout the mission duration.",
    )

    if _NEED_SHALL_RX.search(S["need_text"] or ""):
        st.info("Heads-up: Your need text contains “shall/must/will”. I’ll treat it as an objective (not a requirement) during generation.")

    st.subheader("🎯 Rationale")
    S["rationale"] = st.text_area(
        "Why this matters",
        value=S["rationale"],
        height=80,
        placeholder="e.g., Temperature regulation is critical to ensure electronics, batteries, and payloads function reliably.",
    )

    # ---------- Helpers ----------
    def _qc(text: str):
        try:
            amb = safe_call_ambiguity(text, rule_engine)
        except TypeError:
            amb = safe_call_ambiguity(text, None)
        except Exception:
            amb = []
        pas = check_passive_voice(text)
        inc = check_incompleteness(text)
        sing = check_singularity(text)
        return amb, pas, inc, sing

    def _badge_row(text: str) -> str:
        amb, pas, inc, sing = _qc(text)
        def mark(ok, label): return ("✅ " if ok else "⚠️ ") + label
        return f"{mark(not amb,'Unambiguous')}  {mark(not pas,'Active Voice')}  {mark(not inc,'Complete')}  {mark(not sing,'Singular')}"

    def _next_child_id(parent_id: str) -> str:
        S["child_counts"].setdefault(parent_id, 1)
        idx = S["child_counts"][parent_id]
        S["child_counts"][parent_id] = idx + 1
        return f"{parent_id}.{idx}"

    def _append_children_ids(base_parent: str, children_texts: list[str]) -> list[dict]:
        rows = []
        for txt in children_texts:
            rows.append({
                "ID": _next_child_id(base_parent),
                "ParentID": base_parent,
                "Text": txt,
                "Role": "Child",
                "Verification": "Test",
                "VerificationLevel": "Subsystem",
                "VerificationEvidence": "",
                "ValidationNeedID": S.get("need_id", "NEED-001"),
                "TestCaseIDs": "",
                "AllocatedTo": "",
                "Criticality": "Medium",
                "Status": "Draft"
            })
        return rows

    # ---------- AI Generators ----------
    def _ai_questions(need: str, req_type: str) -> list[str]:
        dom = _detect_domain(need)
        if st.session_state.get("api_key"):
            prompt = f"""
You are a senior systems engineer.
From the NEED below, write 6–8 concise, domain-specific clarifying questions with a short example after “→ e.g.,”.

Rules:
- Cover thresholds/units, modes/conditions, timing/power/budgets, environments/disturbances, verification, contingencies/faults, and domain specifics (e.g., thermal, UAS).
- No bullets/numbering/prefix text. One line per question.
- Format each line exactly like: Question? → e.g., short example.

NEED:
\"\"\"{need.strip()}\"\"\""""
            raw = _llm_retry(lambda p: get_ai_suggestion(st.session_state.api_key, p), prompt)
            if raw:
                lines = [re.sub(r'^[\-\*\u2022]\s+', '', ln.strip()) for ln in raw.splitlines() if ln.strip()]
                out = []
                for ln in lines:
                    out.append(ln if "→" in ln else (ln.rstrip("?") + "? → e.g., TBD."))
                if len(out) >= 5:
                    return out[:8]
        if dom == "thermal":
            return _thermal_questions_with_examples()
        if dom == "uas":
            return _uas_questions_with_examples()
        return _generic_questions_with_examples()

    def _ai_parent(need: str, rationale: str) -> str:
        dom = _detect_domain(need)
        if st.session_state.get("api_key"):
            prompt = f"""
Convert the NEED into ONE parent requirement:
- singular, unambiguous, verifiable if applicable, 'shall', ≤ 22 words.
- Avoid redefining architecture unless the NEED truly demands it.
Return only the sentence.

NEED: \"\"\"{need.strip()}\"\"\"\nRATIONALE: \"\"\"{(rationale or '').strip()}\"\"\""""
            out = _llm_retry(lambda p: get_ai_suggestion(st.session_state.api_key, p), prompt)
            if out:
                return out.splitlines()[0].strip()
        if dom == "thermal":
            return _thermal_parent_from_need(need)
        if dom == "uas":
            return _uas_parent_from_need(need)
        return _fallback_parent(need)

    def _ai_children(parent_text: str, need_text: str) -> list[str]:
        dom = _detect_domain(need_text or parent_text)
        if st.session_state.get("api_key"):
            prompt = f"""
Produce 5–8 CHILD 'shall' requirements that decompose the goal implied by the text below.
Rules:
- ONE measurable metric per child; keep ≤ 22 words; no bullets/numbering.
- Prefer explicit values from text; else use 'TBD_*' with a brief example in parentheses.
- Include domain-typical children (e.g., ranges/time-at-limit/power budgets for thermal; endurance/link/geo-fence/safety for UAS).

TEXT:
\"\"\"{(parent_text or need_text).strip()}\"\"\""""
            raw = _llm_retry(lambda p: get_ai_suggestion(st.session_state.api_key, p), prompt)
            if raw:
                kids = [re.sub(r'^[\-\*\u2022]\s+', '', ln.strip()) for ln in raw.splitlines() if len(ln.strip().split()) > 3]
                if len(kids) >= 3:
                    return kids[:8]
        if dom == "thermal":
            return _thermal_children_default()
        if dom == "uas":
            return _uas_children_default()
        return _fallback_children()

    def _ai_rewrite_strict(text: str) -> str:
        if not st.session_state.get("api_key"):
            return text
        prompt = f"Rewrite as ONE singular, unambiguous, verifiable requirement using 'shall', ≤ 22 words. Return only the sentence.\n\n\"\"\"{text.strip()}\"\"\""
        out = _llm_retry(lambda p: get_ai_suggestion(st.session_state.api_key, p), prompt)
        return (out.splitlines()[0].strip() if out else text)

    # ---------- Generate (one click) ----------
    st.subheader("❓ Gaps & Clarifying Questions")
    cols_q = st.columns([1.4, 2.6])
    with cols_q[0]:
        if st.button("🔎 Generate Questions & Requirements"):
            need_clean = _normalize_need(S["need_text"])
            if not need_clean.strip():
                st.error("Enter the stakeholder need first.")
            else:
                with st.spinner("Thinking like a systems engineer…"):
                    S["ai_questions"] = _ai_questions(need_clean, S["req_type"])
                    parent_txt = _ai_parent(need_clean, S["rationale"])

                    dom = _detect_domain(need_clean)
                    looks_multi = bool(check_singularity(parent_txt)) or bool(re.search(r"\b(and|;|,)\b", parent_txt))
                    force_children = dom in ("thermal", "uas") or "within" in parent_txt.lower() or "maintain" in parent_txt.lower()
                    children_txt = _ai_children(parent_txt, need_clean) if (looks_multi or force_children) else []

                    reqs = []

                    # --- New: choose structure ---
                    # For domain thermal/UAS -> keep Parent + Children.
                    # For generic: if we have >3 children and parent looks too generic, create a GROUP of standalone reqs (no parent).
                    parent_too_generic = dom == "generic" and re.search(r"\b(achieve|provide|ensure|support)\b", parent_txt.lower()) and len(children_txt) >= 4

                    if parent_too_generic:
                        # Group of standalone requirements (Role: Standalone, no ParentID)
                        for i, t in enumerate(children_txt, start=1):
                            reqs.append({
                                "ID": f"REQ-{i:03d}",
                                "ParentID": "",
                                "Text": t,
                                "Role": "Standalone",
                                "Verification": "Test",
                                "VerificationLevel": "Subsystem",
                                "VerificationEvidence": "",
                                "ValidationNeedID": S.get("need_id", "NEED-001"),
                                "TestCaseIDs": "",
                                "AllocatedTo": "",
                                "Criticality": "Medium",
                                "Status": "Draft"
                            })
                    else:
                        if parent_txt:
                            parent_id = "REQ-001"
                            reqs.append({
                                "ID": parent_id,
                                "ParentID": "",
                                "Text": parent_txt,
                                "Role": "Parent",
                                "Verification": "Test",
                                "VerificationLevel": "System",
                                "VerificationEvidence": "",
                                "ValidationNeedID": S.get("need_id", "NEED-001"),
                                "TestCaseIDs": "",
                                "AllocatedTo": "",
                                "Criticality": "Medium",
                                "Status": "Draft"
                            })
                            S["child_counts"][parent_id] = 1
                            if children_txt:
                                reqs.extend(_append_children_ids(parent_id, children_txt))

                    S["requirements"] = reqs
                st.success("Questions and requirements generated.")
                _rerun()
    with cols_q[1]:
        if not S.get("ai_questions"):
            st.caption("No questions yet. Click **Generate Questions & Requirements**.")
        else:
            for i, q in enumerate(S["ai_questions"], start=1):
                st.markdown(f"{i}. {q}")

    # ---------- Requirements (cards) ----------
    st.subheader("🧱 Requirements")
    reqs = list(S.get("requirements", []))
    if not reqs:
        st.caption("No requirements yet. Use **Generate Questions & Requirements**.")
    else:
        for idx, req in enumerate(reqs):
            rid, role = req["ID"], req["Role"]
            text = req.get("Text", "")
            # ensure defaults
            req.setdefault("Verification", req.get("Verification", "Test"))
            req.setdefault("VerificationLevel", req.get("VerificationLevel", "Subsystem"))
            req.setdefault("VerificationEvidence", req.get("VerificationEvidence", ""))
            req.setdefault("ValidationNeedID", req.get("ValidationNeedID", S.get("need_id", "NEED-001")))
            req.setdefault("TestCaseIDs", req.get("TestCaseIDs", ""))
            req.setdefault("AllocatedTo", req.get("AllocatedTo", ""))
            req.setdefault("Criticality", req.get("Criticality", "Medium"))
            req.setdefault("Status", req.get("Status", "Draft"))

            border = "1px solid #94a3b8" if role == "Parent" else "1px solid #e2e8f0"
            st.markdown(f"<div style='border:{border};border-radius:10px;padding:12px;margin-bottom:10px;'>", unsafe_allow_html=True)

            # Header + ID + Text
            title = "Parent" if role == "Parent" else ("Child" if role == "Child" else "Requirement")
            st.markdown(f"**{title}**")
            top = st.columns([0.20, 0.80])
            with top[0]:
                new_id = st.text_input("ID", value=rid, key=f"id_{rid}")
                if new_id and new_id != rid:
                    prefix_old = rid + "."
                    prefix_new = new_id + "."
                    for j, r2 in enumerate(S["requirements"]):
                        if r2["ID"] == rid:
                            S["requirements"][j]["ID"] = new_id
                            if r2["Role"] == "Parent":
                                if rid in S["child_counts"] and new_id not in S["child_counts"]:
                                    S["child_counts"][new_id] = S["child_counts"].pop(rid)
                        elif r2.get("ParentID") == rid:
                            S["requirements"][j]["ParentID"] = new_id
                        if r2["ID"].startswith(prefix_old):
                            S["requirements"][j]["ID"] = prefix_new + r2["ID"][len(prefix_old):]
                    _rerun()
            with top[1]:
                new_text = st.text_input("Requirement", value=text, key=f"text_{rid}")
                if new_text != text:
                    S["requirements"][idx]["Text"] = new_text

            # Tools row (Rewrite always; Decompose only for non-singular)
            tools = st.columns([0.18, 0.18, 0.18, 0.46])
            with tools[0]:
                if st.button("🪄 Rewrite", key=f"rw_{rid}"):
                    S["requirements"][idx]["Text"] = _ai_rewrite_strict(S["requirements"][idx]["Text"])
                    _rerun()

            # Only show Decompose if not singular AND role is Parent or Standalone (children can also be decomposed, but we keep your rule set simple)
            _, _, _, sing_issues = _qc(S["requirements"][idx]["Text"])
            show_decompose = bool(sing_issues)

            with tools[1]:
                if show_decompose:
                    if st.button("🧩 Decompose", key=f"dc_{rid}"):
                        base_parent = S["requirements"][idx]["ID"]
                        if st.session_state.get("api_key"):
                            raw = _llm_retry(lambda _: decompose_requirement_with_ai(st.session_state.api_key, S["requirements"][idx]["Text"]), "DECOMPOSE")
                            kids_txt = [re.sub(r'^[\-\*\u2022]?\s*', '', ln.strip()) for ln in (raw or "").splitlines() if re.search(r'\w', ln)]
                            kids_txt = [k for k in kids_txt if len(k.split()) > 3]
                        else:
                            parts = [p.strip(" ,.;") for p in re.split(r"\band\b|;", S["requirements"][idx]["Text"], flags=re.I) if p.strip()]
                            kids_txt = [p for p in parts if len(p.split()) > 3]
                        if kids_txt:
                            # If the current item is Standalone (group), convert it into a Parent to host children
                            if S["requirements"][idx]["Role"] == "Standalone":
                                S["requirements"][idx]["Role"] = "Parent"
                                S["child_counts"][base_parent] = 1
                            S["child_counts"].setdefault(base_parent, 1)
                            children = _append_children_ids(base_parent, kids_txt)
                            S["requirements"][idx+1:idx+1] = children
                            st.success(f"Decomposed into {len(children)} child requirement(s).")
                            _rerun()
                        else:
                            st.info("No decomposable actions detected.")
                else:
                    st.write("")

            with tools[2]:
                if st.button("🗑️ Delete", key=f"del_{rid}"):
                    pref = rid + "."
                    S["requirements"] = [r for r in S["requirements"] if not (r["ID"] == rid or r["ID"].startswith(pref))]
                    _rerun()
            with tools[3]:
                st.caption("")

            # Structured edit (dropdowns / with custom)
            with st.expander("Structured edit (dropdowns / with custom)"):
                def _sel_or_custom(label, options, ksel, kcust, initial=""):
                    preset = initial if initial in options else (options[0] if options else "")
                    sel = st.selectbox(label, options + ["Custom…"],
                                       index=(options + ["Custom…"]).index(preset) if preset in options else len(options),
                                       key=ksel)
                    if sel == "Custom…":
                        return st.text_input(f"{label} (custom)", value=initial if (initial and initial not in options) else "",
                                             key=kcust)
                    return sel

                txt_now = S["requirements"][idx]["Text"]
                actor_guess = "System"
                if re.search(r"\b(payload|optics)\b", txt_now, re.I): actor_guess = "Payload"
                if re.search(r"\bbattery|batteries\b", txt_now, re.I): actor_guess = "Power Subsystem"
                if re.search(r"\bthermal|heater|temperature|radiator\b", txt_now, re.I): actor_guess = "Thermal Control Subsystem"
                if re.search(r"\buav|uas|drone|gcs\b", txt_now, re.I): actor_guess = "UAV"

                action_guess = "maintain" if re.search(r"\bmaintain|hold\b", txt_now, re.I) else ("regulate" if re.search(r"\bregulat", txt_now, re.I) else "achieve")
                object_guess = "temperatures" if re.search(r"\btemp|thermal\b", txt_now, re.I) else ("mission performance" if re.search(r"\buav|uas|drone|gcs\b", txt_now, re.I) else "function")
                trigger_guess = "during all mission phases" if re.search(r"\bmission\b", txt_now, re.I) else ""
                conditions_guess = "in eclipse and full sun" if re.search(r"\beclipse|sun\b", txt_now, re.I) else ("in nominal conditions" if re.search(r"\buav|uas|drone|gcs\b", txt_now, re.I) else "in nominal mode")

                c1, c2 = st.columns(2)
                with c1:
                    actor = _sel_or_custom("Actor / System",
                                           ["System", "Thermal Control Subsystem", "Power Subsystem", "Payload", "Spacecraft", "UAV"],
                                           f"{rid}_actor_sel", f"{rid}_actor_custom", actor_guess)
                    modal = st.selectbox("Modal Verb", ["shall", "will", "must"], index=0, key=f"{rid}_modal")
                    action = _sel_or_custom("Action / Verb",
                                            ["maintain", "regulate", "limit", "detect", "log", "achieve", "provide", "enforce"],
                                            f"{rid}_action_sel", f"{rid}_action_custom", action_guess)
                    obj = _sel_or_custom("Object",
                                         ["temperatures", "payload optics temperature", "battery temperatures", "avionics temperatures", "mission performance", "function"],
                                         f"{rid}_object_sel", f"{rid}_object_custom", object_guess)
                with c2:
                    trigger = _sel_or_custom("Trigger / Event (optional)",
                                             ["during all mission phases", "during eclipse", "during active imaging", "when commanded", "during flight operations", ""],
                                             f"{rid}_trigger_sel", f"{rid}_trigger_custom", trigger_guess)
                    conditions = _sel_or_custom("Operating Conditions / State (optional)",
                                                ["in eclipse and full sun", "in nominal mode", "in safe mode", "in nominal conditions", ""],
                                                f"{rid}_cond_sel", f"{rid}_cond_custom", conditions_guess)
                    perf = st.text_input("Performance / Constraint (optional, measurable)",
                                         value="", placeholder="e.g., 0–40 °C; ±2 °C of T_nom; ≥45 min endurance; ≤200 ms latency",
                                         key=f"{rid}_perf")

                def _norm_trig(t: str) -> str:
                    t = t.strip()
                    if not t:
                        return ""
                    return t if re.match(r'^(when|if|while|during)\b', t, flags=re.I) else f"during {t}"

                trig_part = (_norm_trig(trigger) + ", ") if trigger.strip() else ""
                tail_perf = f" {perf.strip()}" if perf.strip() else ""
                tail_cond = f" {conditions.strip()}" if conditions.strip() else ""
                rebuilt = f"{trig_part}{actor} {modal} {action} {obj}{tail_perf}{tail_cond}".strip()
                if not rebuilt.endswith("."):
                    rebuilt += "."
                rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
                if st.button("Apply structured edit", key=f"apply_{rid}"):
                    S["requirements"][idx]["Text"] = rebuilt
                    _rerun()

            # Inline V&V + traceability rows
            row_vv1 = st.columns([0.26, 0.26, 0.24, 0.24])
            with row_vv1[0]:
                ver_options = ["Test", "Analysis", "Inspection", "Demo"]
                cur = S["requirements"][idx].get("Verification", "Test")
                sel = st.selectbox("Verification Method", ver_options, index=ver_options.index(cur) if cur in ver_options else 0, key=f"{rid}_verif")
                if sel != cur:
                    S["requirements"][idx]["Verification"] = sel
            with row_vv1[1]:
                lvl_opts = ["Unit", "Subsystem", "System", "Mission"]
                cur = S["requirements"][idx].get("VerificationLevel", "Subsystem")
                sel = st.selectbox("Verification Level", lvl_opts, index=lvl_opts.index(cur) if cur in lvl_opts else 1, key=f"{rid}_verlvl")
                if sel != cur:
                    S["requirements"][idx]["VerificationLevel"] = sel
            with row_vv1[2]:
                cur = S["requirements"][idx].get("ValidationNeedID", S.get("need_id", "NEED-001"))
                val = st.text_input("Validation Need ID", value=cur, key=f"{rid}_valneed")
                if val != cur:
                    S["requirements"][idx]["ValidationNeedID"] = val
            with row_vv1[3]:
                cur = S["requirements"][idx].get("AllocatedTo", "")
                val = st.text_input(
                    "Allocated To",
                    value=cur,
                    key=f"{rid}_alloc",
                    placeholder="e.g., Thermal Subsystem / Mobile App / Backend Service / Flight Software"
                )
                if val != cur:
                    S["requirements"][idx]["AllocatedTo"] = val


            row_vv2 = st.columns([0.50, 0.25, 0.25])
            with row_vv2[0]:
                cur = S["requirements"][idx].get("VerificationEvidence", "")
                val = st.text_input("Verification Evidence (link/ID)", value=cur, key=f"{rid}_verevid")
                if val != cur:
                    S["requirements"][idx]["VerificationEvidence"] = val
            with row_vv2[1]:
                cur = S["requirements"][idx].get("TestCaseIDs", "")
                val = st.text_input("Test Case ID(s)", value=cur, key=f"{rid}_tcids", placeholder="e.g., TVAC-OPT-02; T-123")
                if val != cur:
                    S["requirements"][idx]["TestCaseIDs"] = val
            with row_vv2[2]:
                crit_options = ["High", "Medium", "Low"]
                cur_crit = S["requirements"][idx].get("Criticality", "Medium")
                sel_crit = st.selectbox("Criticality", crit_options, index=crit_options.index(cur_crit) if cur_crit in crit_options else 1, key=f"{rid}_crit")
                if sel_crit != cur_crit:
                    S["requirements"][idx]["Criticality"] = sel_crit

            row_status = st.columns([1.0])
            with row_status[0]:
                status_options = ["Draft", "Reviewed", "Approved"]
                cur_status = S["requirements"][idx].get("Status", "Draft")
                sel_status = st.selectbox("Status", status_options, index=status_options.index(cur_status) if cur_status in status_options else 0, key=f"{rid}_status")
                if sel_status != cur_status:
                    S["requirements"][idx]["Status"] = sel_status

            # Quality badges
            st.markdown(_badge_row(S["requirements"][idx]["Text"]))
            st.markdown("</div>", unsafe_allow_html=True)

    # ---------- Export ----------
    st.subheader("⬇️ Export Requirements (CSV)")
    if not S.get("requirements"):
        st.info("No requirements to export yet.")
    else:
        rows = []
        for r in S["requirements"]:
            rows.append({
                "Need ID": S.get("need_id", "NEED-001"),
                "Validation Need ID": r.get("ValidationNeedID", S.get("need_id", "NEED-001")),
                "ID": r["ID"],
                "ParentID": r["ParentID"],
                "Requirement Text": r["Text"],
                "Type": S.get("req_type", "Functional"),
                "Role": r["Role"],
                "Priority": S.get("priority", "Should"),
                "Lifecycle": S.get("lifecycle", "Operations"),
                "Stakeholder": S.get("stakeholder", ""),
                "Source": "Need",
                "Verification": r.get("Verification", ""),
                "Verification Level": r.get("VerificationLevel", ""),
                "Verification Evidence": r.get("VerificationEvidence", ""),
                "Test Case IDs": r.get("TestCaseIDs", ""),
                "Allocated To": r.get("AllocatedTo", ""),
                "Criticality": r.get("Criticality", ""),
                "Status": r.get("Status", ""),
                "Acceptance Criteria": "",
                "Rationale": S.get("rationale", "")
            })
        df_pro = pd.DataFrame(rows, columns=[
            "Need ID", "Validation Need ID", "ID", "ParentID", "Requirement Text", "Type", "Role",
            "Priority", "Lifecycle", "Stakeholder", "Source",
            "Verification", "Verification Level", "Verification Evidence",
            "Test Case IDs", "Allocated To", "Criticality", "Status",
            "Acceptance Criteria", "Rationale"
        ])
        st.download_button(
            "Download CSV",
            data=df_pro.to_csv(index=False).encode("utf-8"),
            file_name="Requirements_Export.csv",
            mime="text/csv",
            key="pro_export_csv"
        )
