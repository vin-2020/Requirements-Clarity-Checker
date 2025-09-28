# ui/tabs/need_tab.py
import re
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

def render(st, db, rule_engine, CTX):
    """
    Need → Requirement Assistant tab.
    Uses the same logic you had; just split out.
    """
    # ---------- SAFE analyzer/AI helpers pulled from CTX ----------
    safe_call_ambiguity = CTX["safe_call_ambiguity"]
    check_passive_voice = CTX["check_passive_voice"]
    check_incompleteness = CTX["check_incompleteness"]
    check_singularity = CTX["check_singularity"]

    get_ai_suggestion = CTX["get_ai_suggestion"]
    decompose_requirement_with_ai = CTX["decompose_requirement_with_ai"]

    # Strict autofill may be missing; we attempt to import locally (keeps original behavior)
    try:
        from llm.ai_suggestions import analyze_need_autofill as _strict_autofill
    except Exception:
        _strict_autofill = None

    # ---------- Optional alternate rules (kept as-is) ----------
    try:
        from core.rules import RuleEngine as _RealRuleEngine
    except Exception:
        _RealRuleEngine = None

    class _FallbackRuleEngine:
        def is_check_enabled(self, name: str) -> bool: return True
        def get_ambiguity_terms(self): return []
        def get_custom_weak_words(self): return []
        def get_ambiguity_words(self): return []
        def get_weak_words(self): return []

    def _get_rule_engine():
        try:
            return _RealRuleEngine() if _RealRuleEngine is not None else _FallbackRuleEngine()
        except Exception:
            return _FallbackRuleEngine()

    # ---------- State ----------
    def _init_state():
        if "need_ui" not in st.session_state:
            st.session_state.need_ui = {
                # top
                "mode":"Detailed",
                "req_type":"Functional",
                "stakeholder":"", "priority":"Should", "lifecycle":"Operations",
                # content
                "need_text":"", "rationale":"",
                # structured fields (for Detailed)
                "Functional":{"actor":"", "modal":"shall", "action":"", "object":"", "trigger":"", "conditions":"", "performance":""},
                "Performance":{"function":"", "metric":"", "threshold":"", "unit":"", "conditions":"", "measurement":"", "verification":"Test"},
                "Constraint":{"subject":"", "constraint_text":"", "driver":"", "why":""},
                "Interface":{"system":"", "external":"", "standard":"", "direction":"Bi-directional", "data":"", "perf":"", "conditions":""},
                # previews/output
                "preview_req":"",          # now the ONLY editable preview surface
                "final_req":"",            # explicit final requirement (user-loaded)
                "final_ac":[],             # acceptance criteria (editable)
                "last_ai_raw":"",          # latest AI raw (review/decompose)
                # IDs & role (simple)
                "final_role":"Parent",     # "Parent" or "Child"
                "final_id":"",             # ID for the Final Requirement
                "final_parent_id":"",      # only if final is a child
                "child_next":1,            # next child integer suffix for quick generate
                # Decomposition
                "decomp_source":"Need",    # "Need" or "Final Requirement"
                "decomp_parent_text":"",   # parent text used in decomposition section (editable)
                "decomp_parent_id":"",     # parent id used in decomposition section (editable)
                "decomp_rows":[],          # list of {"ID","ParentID","Requirement Text"}
                "scroll_to":""
            }
    _init_state()
    S = st.session_state.need_ui

    # ---------- Header ----------
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    st.header("✍️ Need → Requirement Assistant" + (f" — Project: {pname}" if pname else ""))

    # ---------- Top controls ----------
    c_top = st.columns([1,1,1,1,1])
    with c_top[0]:
        S["mode"] = st.radio("Mode", ["Simple","Detailed"], index=["Simple","Detailed"].index(S["mode"]),
                             horizontal=True, key="need_mode_top")
    with c_top[1]:
        S["req_type"] = st.selectbox("Requirement Type",
            ["Functional","Performance","Constraint","Interface"],
            index=["Functional","Performance","Constraint","Interface"].index(S["req_type"]),
            key="need_reqtype_top")
    with c_top[2]:
        S["priority"] = st.selectbox("Priority", ["Must","Should","Could","Won't (now)"],
                                     index=["Must","Should","Could","Won't (now)"].index(S["priority"]),
                                     key="need_priority_top")
    with c_top[3]:
        S["lifecycle"] = st.selectbox("Life-cycle", ["Concept","Development","P/I/V&V","Operations","Maintenance","Disposal"],
                                      index=["Concept","Development","P/I/V&V","Operations","Maintenance","Disposal"].index(S["lifecycle"]),
                                      key="need_lifecycle_top")
    with c_top[4]:
        S["stakeholder"] = st.text_input("Stakeholder / Role", value=S["stakeholder"],
                                         placeholder="e.g., Field operator, Acquirer", key="need_stakeholder_top")

    # ---------- Need & Rationale ----------
    st.subheader("Stakeholder Need")
    S["need_text"] = st.text_area("Describe the need (no 'shall')", value=S["need_text"], height=110,
                                  placeholder="e.g., The operator needs the drone to warn about low battery to avoid mission aborts.",
                                  key="need_text_area")
    S["rationale"] = st.text_area("Rationale (why this matters)", value=S["rationale"], height=80,
                                  placeholder="e.g., Prevent mission failure and avoid emergency landings.",
                                  key="need_rat_area")

    # ---------- Helpers (formatting only; analyzer unchanged) ----------
    _VAGUE = ("all specified","as needed","as soon as possible","etc.","including but not limited to")
    def _strip_vague(t: str) -> str:
        x = (t or "")
        for b in _VAGUE: x = x.replace(b, "")
        return re.sub(r"\s{2,}", " ", x).strip(" ,.")

    def _strip_perf_from_object(obj: str, perf: str) -> tuple[str,str]:
        o = (obj or "").strip(); p = (perf or "").strip()
        if not o: return o, p
        rxes = [
            r'\bwith (a )?probability of\s*[0-9]*\.?[0-9]+%?',
            r'\b(minimum|maximum|at least|no more than)\s*[0-9]*\.?[0-9]+%?\b',
            r'\b\d+(\.\d+)?\s*(ms|s|sec|m|km|Hz|kHz|MHz|kbps|Mbps|Gbps|fps)\b',
            r'\b\d+(\.\d+)?\s*%(\b|$)'
        ]
        extracted = []
        for rx in rxes:
            m = re.search(rx, o, flags=re.I)
            if m:
                extracted.append(m.group(0))
                o = (o[:m.start()] + o[m.end():]).strip(" ,.")
        if extracted:
            extra = " ".join(extracted)
            if p and extra not in p: p = f"{p}; {extra}"
            if not p: p = extra
        return o, p

    def _push_need_context_to_conditions(conds: str, need_text: str) -> str:
        base = (conds or "")
        nl = (need_text or "").lower()
        bits = []
        if "contested airspace" in nl and "contested airspace" not in base.lower():
            bits.append("in contested airspace")
        if ("avoid" in nl or "avoiding detection" in nl or "stealth" in nl) and not re.search(r"detect|avoid", base, flags=re.I):
            bits.append("while minimizing detectability by adversary sensors")
        if "return" in nl and "return" not in base.lower():
            bits.append("and return safely to base")
        if bits:
            base = (base + " " + " ".join(bits)).strip()
        return re.sub(r"\s{2,}", " ", base)

    def _normalize_trigger(trig: str) -> str:
        t = (trig or "").strip(" ,.")
        if not t: return ""
        t = re.sub(r'^\s*when\s+when\s+', 'when ', t, flags=re.I)
        if not re.match(r'^(when|if|while|during)\b', t, flags=re.I):
            t = "when " + t
        return t

    # ---------- Previews ----------
    def _need_preview():
        raw_need = (S["need_text"] or "").strip()
        if raw_need.lower().startswith(("the ","a ","an ","i ","we ","user ","operator ","stakeholder ","mission")):
            text = raw_need
        else:
            text = f"The {S['stakeholder'] or 'stakeholder'} needs the system to {raw_need or '[describe need]'}"
        text += f" so that {S['rationale'].strip()}." if S["rationale"].strip() else "."
        return text

    def _build_req_preview():
        t = S["req_type"]
        if t == "Functional":
            f = S["Functional"]
            actor = (f["actor"] or "[Actor]").strip()
            modal = (f["modal"] or "shall").strip()
            action = (f["action"] or "[action]").strip()
            obj = (f["object"] or "[object]").strip()
            trig = _normalize_trigger(f["trigger"])
            cond = _strip_vague(f["conditions"])
            perf = _strip_vague(f["performance"])
            prefix = (trig + ", ") if trig else ""
            tail_perf = f" {perf}" if perf and perf.lower() not in obj.lower() else ""
            tail_cond = f" {cond}" if cond else ""
            snt = f"{prefix}{actor} {modal} {action} {obj}{tail_perf}{tail_cond}"
            snt = re.sub(r"\s{2,}", " ", snt).strip()
            if not snt.endswith("."): snt += "."
            return snt
        if t == "Performance":
            p = S["Performance"]
            seg_cond = f" under {p['conditions']}" if p["conditions"] else ""
            seg_meas = f" as measured by {p['measurement']}" if p["measurement"] else ""
            return f"The {p['function'] or '[function]'} shall have {p['metric'] or '[metric]'} {p['threshold'] or '[value]'} {p['unit'] or '[unit]'}{seg_cond}{seg_meas}."
        if t == "Constraint":
            c = S["Constraint"]
            seg = f" per {c['driver']}" if c["driver"] else ""
            return f"The {c['subject'] or '[subject]'} shall comply with {c['constraint_text'] or '[constraint]'}{seg}."
        if t == "Interface":
            i = S["Interface"]
            seg_perf = f" with {i['perf']}" if i["perf"] else ""
            seg_cond = f" under {i['conditions']}" if i["conditions"] else ""
            return f"The {i['system'] or '[system]'} shall interface with {i['external'] or '[external system]'} via {i['standard'] or '[standard]'} ({i['direction']}). It shall exchange {i['data'] or '[data]'}{seg_perf}{seg_cond}."
        return ""

    # Initialize preview once if empty (avoid overwriting user edits each render)
    if not S.get("preview_req"):
        S["preview_req"] = _build_req_preview()

    # ---------- SIMPLE MODE ACTION ROW ----------
    if S["mode"] == "Simple":
        row = st.columns([1.2, 1.2, 1.1, 1.1, 1.0])
        with row[0]:
            if st.button("🚀 Generate Requirement"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need.")
                else:
                    prompt = f"""
You are a systems engineer. Convert the NEED into ONE clear, testable {S['req_type']} requirement (use 'shall') and 3–6 acceptance criteria.

NEED:
\"\"\"{S['need_text'].strip()}\"\"\"\n
RATIONALE:
\"\"\"{S['rationale'].strip()}\"\"\"\n
Return STRICTLY:

REQUIREMENT: <one sentence, active voice, measurable where applicable>

ACCEPTANCE CRITERIA:
- <criterion 1 with setup/conditions + threshold + verification method>
- <criterion 2>
- <criterion 3>
"""
                    raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    S["last_ai_raw"] = raw
                    req = ""
                    m = re.search(r'(?im)^\s*REQUIREMENT\s*:\s*(.+)$', raw)
                    if m: req = m.group(1).strip()
                    if not req:
                        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                        req = next((ln for ln in lines if re.search(r'\bshall\b', ln, re.I)), "")
                    if req:
                        S["preview_req"] = req

                    ac = []
                    ac_block = raw.split("ACCEPTANCE CRITERIA", 1)[-1] if "ACCEPTANCE CRITERIA" in raw else ""
                    for ln in (ac_block or "").splitlines():
                        if re.match(r'^\s*[-*•]\s+', ln):
                            ac.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                    S["final_ac"] = ac
                    st.success("Requirement generated. Review below.")
        with row[1]:
            if st.button("🪄 Improve Requirement"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["preview_req"].strip():
                    st.error("Generate a requirement first.")
                else:
                    base = S["preview_req"].strip()
                    prompt = f"""Rewrite this as a single, clear, unambiguous, testable sentence in active voice using 'shall'. Return only the sentence.

\"\"\"{base}\"\"\""""
                    out = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    if out.strip():
                        S["preview_req"] = out.strip().splitlines()[0]
                        st.success("Requirement refined.")
        with row[2]:
            if st.button("🤖 Review & Generate AC"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["preview_req"].strip():
                    st.error("Enter or generate a requirement first.")
                else:
                    prompt = f"""
Act as a systems engineering reviewer. Provide a short critique and 3–6 testable acceptance criteria (each includes setup/conditions, threshold(s), and verification: Test/Analysis/Inspection/Demonstration).

REQUIREMENT:
\"\"\"{S['preview_req'].strip()}\"\"\""""
                    raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                    S["last_ai_raw"] = raw
                    bullets = []
                    for ln in raw.splitlines():
                        if re.match(r'^\s*[-*•]\s+', ln):
                            bullets.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                    if bullets:
                        S["final_ac"] = bullets
                        st.success("Acceptance Criteria generated.")
        with row[3]:
            if st.button("🧩 Decompose"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                else:
                    src = S.get("decomp_source","Need")
                    base = S["need_text"].strip() if src == "Need" else S["preview_req"].strip()
                    if not base:
                        st.error(f"Enter a {src.lower()} to decompose.")
                    else:
                        S["last_ai_raw"] = decompose_requirement_with_ai(st.session_state.api_key, base) or ""
                        rows, idx = [], 1
                        for ln in (S["last_ai_raw"] or "").splitlines():
                            if re.match(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', ln):
                                txt = re.sub(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', '', ln).strip()
                                if txt:
                                    parent = S.get("final_id","").strip() or S.get("final_parent_id","").strip()
                                    cid = f"{(parent or 'REQ-000')}.{idx}"
                                    rows.append({"ID": cid, "ParentID": parent, "Requirement Text": txt})
                                    idx += 1
                        S["decomp_rows"] = rows
                        S["decomp_parent_text"] = S["preview_req"].strip() if src == "Final Requirement" else ""
                        S["decomp_parent_id"] = S.get("final_id","").strip()
                        S["scroll_to"] = "decomp"
                        st.rerun()
        with row[4]:
            if st.button("↺ Reset"):
                _init_state()
                st.rerun()

    # ---------- DETAILED MODE ----------
    if S["mode"] == "Detailed":
        st.caption("Use **Analyze Need (AI Autofill)** to seed fields; then refine and preview.")
        c_an = st.columns([1,1,2])
        with c_an[0]:
            if st.button("🔎 Analyze Need (AI Autofill)"):
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need first.")
                elif not _strict_autofill:
                    st.info("Autofill helper not available; fill fields manually.")
                else:
                    with st.spinner("Analyzing need..."):
                        kv = _strict_autofill(st.session_state.api_key, S["need_text"], S["req_type"]) or {}
                    if S["req_type"] == "Functional":
                        actor = _strip_vague(kv.get("Actor","")) or "The system"
                        modal = (kv.get("ModalVerb","shall") or "shall").lower()
                        action = _strip_vague(kv.get("Action",""))
                        obj, perf = _strip_perf_from_object(_strip_vague(kv.get("Object","")), _strip_vague(kv.get("Performance","")))
                        trig = _normalize_trigger(_strip_vague(kv.get("Trigger","")))
                        cond = _push_need_context_to_conditions(_strip_vague(kv.get("Conditions","")), S["need_text"])
                        S["Functional"].update({"actor":actor,"modal": modal if modal in ("shall","will","must") else "shall",
                                                "action":action,"object":obj,"trigger":trig,"conditions":cond,"performance":perf})
                    elif S["req_type"] == "Performance":
                        S["Performance"].update({
                            "function":_strip_vague(kv.get("Function","")),
                            "metric":_strip_vague(kv.get("Metric","")),
                            "threshold":_strip_vague(kv.get("Threshold","")),
                            "unit":_strip_vague(kv.get("Unit","")),
                            "conditions":_strip_vague(kv.get("Conditions","")),
                            "measurement":_strip_vague(kv.get("Measurement","")),
                            "verification": kv.get("VerificationMethod","Test") if kv.get("VerificationMethod") in ("Test","Analysis","Inspection","Demonstration") else "Test"
                        })
                    elif S["req_type"] == "Constraint":
                        S["Constraint"].update({
                            "subject":_strip_vague(kv.get("Subject","")),
                            "constraint_text":_strip_vague(kv.get("ConstraintText","")),
                            "driver":_strip_vague(kv.get("DriverOrStandard","")),
                            "why": _strip_vague(kv.get("Rationale","")) or S["rationale"]
                        })
                    else:
                        dr = kv.get("Direction","Bi-directional")
                        S["Interface"].update({
                            "system":_strip_vague(kv.get("System","")),
                            "external":_strip_vague(kv.get("ExternalSystem","")),
                            "standard":_strip_vague(kv.get("InterfaceStandard","")),
                            "direction": dr if dr in ("In","Out","Bi-directional") else "Bi-directional",
                            "data":_strip_vague(kv.get("DataItems","")),
                            "perf":_strip_vague(kv.get("Performance","")),
                            "conditions":_strip_vague(kv.get("Conditions",""))
                        })
                    if not S.get("preview_req"):
                        S["preview_req"] = _build_req_preview()
                    st.success("Autofilled. Review and refine below.")
        with c_an[1]:
            if st.button("↺ Clear Fields (this type)"):
                if S["req_type"] == "Functional":
                    S["Functional"] = {"actor":"", "modal":"shall", "action":"", "object":"", "trigger":"", "conditions":"", "performance":""}
                elif S["req_type"] == "Performance":
                    S["Performance"] = {"function":"", "metric":"", "threshold":"", "unit":"", "conditions":"", "measurement":"", "verification":"Test"}
                elif S["req_type"] == "Constraint":
                    S["Constraint"] = {"subject":"", "constraint_text":"", "driver":"", "why":""}
                else:
                    S["Interface"] = {"system":"", "external":"", "standard":"", "direction":"Bi-directional", "data":"", "perf":"", "conditions":""}
                st.info(f"{S['req_type']} fields cleared.")

        # Fields (type-specific)
        st.subheader("Structured Fields")
        if S["req_type"] == "Functional":
            F = S["Functional"]
            c1, c2 = st.columns(2)
            with c1:
                F["actor"] = st.text_input("Actor / System", value=F["actor"], key="fun_actor")
                F["modal"] = st.selectbox("Modal Verb", ["shall","will","must"], index=["shall","will","must"].index(F["modal"]) if F["modal"] in ["shall","will","must"] else 0, key="fun_modal")
                F["action"] = st.text_input("Action / Verb", value=F["action"], key="fun_action")
                F["object"] = st.text_input("Object", value=F["object"], key="fun_object")
            with c2:
                F["trigger"] = st.text_input("Trigger / Event (optional)", value=F["trigger"], key="fun_trigger")
                F["conditions"] = st.text_input("Operating Conditions / State (optional)", value=F["conditions"], key="fun_cond")
                F["performance"] = st.text_input("Performance / Constraint (optional, measurable)", value=F["performance"], key="fun_perf")
        elif S["req_type"] == "Performance":
            P = S["Performance"]
            c1, c2, c3 = st.columns(3)
            with c1:
                P["function"] = st.text_input("Function (what is measured)", value=P["function"], key="perf_func")
                P["metric"] = st.text_input("Metric (e.g., latency, accuracy)", value=P["metric"], key="perf_metric")
            with c2:
                P["threshold"] = st.text_input("Threshold (number)", value=P["threshold"], key="perf_threshold")
                P["unit"] = st.text_input("Unit", value=P["unit"], key="perf_unit")
            with c3:
                P["conditions"] = st.text_input("Conditions / State", value=P["conditions"], key="perf_cond")
                P["measurement"] = st.text_input("Measurement Method", value=P["measurement"], key="perf_measure")
                P["verification"] = st.selectbox("Verification Method", ["Test","Analysis","Inspection","Demonstration"],
                                                 index=["Test","Analysis","Inspection","Demonstration"].index(P["verification"]),
                                                 key="perf_verif")
        elif S["req_type"] == "Constraint":
            C = S["Constraint"]
            c1, c2 = st.columns(2)
            with c1:
                C["subject"] = st.text_input("Subject (system/subsystem/component)", value=C["subject"], key="con_subject")
                C["constraint_text"] = st.text_input("Constraint (what must hold true)", value=C["constraint_text"], key="con_text")
            with c2:
                C["driver"] = st.text_input("Driver / Standard / Policy", value=C["driver"], key="con_driver")
                C["why"] = st.text_input("Rationale (optional)", value=C["why"], key="con_why")
        else:
            I = S["Interface"]
            c1, c2 = st.columns(2)
            with c1:
                I["system"] = st.text_input("This System", value=I["system"], key="if_sys")
                I["external"] = st.text_input("External System", value=I["external"], key="if_ext")
                I["standard"] = st.text_input("Interface Standard / Protocol", value=I["standard"], key="if_std")
            with c2:
                I["direction"] = st.selectbox("Direction", ["In","Out","Bi-directional"],
                                              index=["In","Out","Bi-directional"].index(I["direction"]), key="if_dir")
                I["data"] = st.text_input("Data Items / Messages", value=I["data"], key="if_data")
                I["perf"] = st.text_input("Performance (e.g., latency/throughput)", value=I["perf"], key="if_perf")
            I["conditions"] = st.text_input("Conditions / Modes (optional)", value=I["conditions"], key="if_cond")

    # ---------- Previews & Quality (always shown) ----------
    st.subheader("Previews & Quality")
    left, right = st.columns(2)
    with left:
        st.markdown("**Need Preview (no 'shall')**")
        st.markdown(f"> {_need_preview()}")

    with right:
        st.markdown("**Requirement Preview (editable)**")
        S["preview_req"] = st.text_area(
            "Edit the requirement preview before sending to Final",
            value=S["preview_req"] or _build_req_preview(),
            height=90,
            key="preview_req_edit_area"
        )
        if st.button("Rebuild Preview from Fields"):
            S["preview_req"] = _build_req_preview()
            st.info("Preview rebuilt from the structured fields.")

        try:
            amb = safe_call_ambiguity(S["preview_req"], _get_rule_engine())
        except TypeError:
            amb = safe_call_ambiguity(S["preview_req"], None)
        except Exception:
            amb = []
        pas = check_passive_voice(S["preview_req"])
        inc = check_incompleteness(S["preview_req"])
        sing = check_singularity(S["preview_req"])
        qc = st.columns(4)
        qc[0].write(("✅" if not amb else "⚠️") + " Unambiguous")
        qc[1].write(("✅" if not pas else "⚠️") + " Active Voice")
        qc[2].write(("✅" if not inc else "⚠️") + " Complete")
        qc[3].write(("✅" if not sing else "⚠️") + " Singular")
        if amb: st.caption(f"Ambiguous terms: {', '.join(amb)}")
        if pas: st.caption(f"Passive voice: {', '.join(pas)}")
        if sing: st.caption(f"Multiple actions: {', '.join(sing)}")

    # ---------- Final Requirement ----------
    st.subheader("Final Requirement")
    cols_fr = st.columns([1,1])
    with cols_fr[0]:
        if st.button("Load Preview → Final"):
            S["final_req"] = (S["preview_req"] or "").strip()
            st.success("Loaded preview into Final.")
    with cols_fr[1]:
        if st.button("🤖 Review & Generate AC (Final)"):
            if not st.session_state.api_key:
                st.warning("Enter your Google AI API Key.")
            elif not S.get("final_req","").strip():
                st.error("Enter or load a Final requirement first.")
            else:
                prompt = f"""
Act as a systems engineering reviewer. Provide a short critique and 3–6 testable acceptance criteria (each includes setup/conditions, threshold(s), and verification: Test/Analysis/Inspection/Demonstration).

REQUIREMENT:
\"\"\"{S['final_req'].strip()}\"\"\""""
                raw = get_ai_suggestion(st.session_state.api_key, prompt) or ""
                S["last_ai_raw"] = raw
                bullets = []
                for ln in raw.splitlines():
                    if re.match(r'^\s*[-*•]\s+', ln):
                        bullets.append(re.sub(r'^\s*[-*•]\s+', '', ln).strip())
                if bullets:
                    S["final_ac"] = bullets
                    st.success("Acceptance Criteria generated below.")
                else:
                    st.info("No bullets detected. See raw output under the expander below.")

    S.setdefault("final_req", "")
    S.setdefault("final_ac", [])

    S["final_req"] = st.text_area("Final Requirement (single sentence, uses 'shall')",
                                  value=S["final_req"], height=90, key="final_req_edit")

    # ---------- Acceptance Criteria ----------
    st.subheader("Acceptance Criteria")
    ac_text = "\n".join(S.get("final_ac", []))
    new_ac_text = st.text_area("One bullet per line", value=ac_text, height=130, key="need_ac_edit")
    S["final_ac"] = [ln.strip() for ln in new_ac_text.splitlines() if ln.strip()]

    # ---------- ID & Role for Final Requirement ----------
    st.subheader("ID & Role for Final Requirement")
    idrow = st.columns([1,1,1,1])
    with idrow[0]:
        S["final_id"] = st.text_input("Final Requirement ID", value=S.get("final_id",""), placeholder="e.g., REQ-001", key="final_req_id")
    with idrow[1]:
        S["final_role"] = st.radio("Role", ["Parent","Child"],
                                   index=["Parent","Child"].index(S.get("final_role","Parent")), horizontal=True, key="final_role_radio")
    with idrow[2]:
        if S["final_role"] == "Child":
            S["final_parent_id"] = st.text_input("Parent ID", value=S.get("final_parent_id",""), placeholder="e.g., REQ-000", key="final_parent_id")
        else:
            st.caption("Parent role: no parent ID needed.")
    with idrow[3]:
        if S["final_role"] == "Child" and (S.get("final_parent_id","").strip()):
            if st.button("Generate Next Child ID"):
                S["final_id"] = f"{S['final_parent_id'].strip()}.{int(S.get("child_next",1))}"
                S["child_next"] = int(S.get("child_next",1)) + 1
                st.success(f"Child: {S['final_id']}")

    # ---------- Decomposition ----------
    st.subheader("Decomposition")
    st.caption("Choose a source and create a parent/children set. You can edit the parent text/ID and the child items, add or delete children.")

    decomp_top = st.columns([1,1,2])
    with decomp_top[0]:
        S["decomp_source"] = st.selectbox("Decompose From", ["Need","Final Requirement"],
                                          index=["Need","Final Requirement"].index(S["decomp_source"]),
                                          key="decomp_source_sel")

    def _parse_children_lines(text: str) -> list[str]:
        out = []
        for ln in (text or "").splitlines():
            if re.match(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', ln):
                out.append(re.sub(r'^(\d+[\.\)]\s+|\-\s+|\*\s+|•\s+)', '', ln).strip())
        return [x for x in out if x]

    def _ai_parent_and_children_from_need(api_key: str, need_text: str) -> tuple[str, list[str]]:
        prompt = f"""
You are a systems engineer. From the following stakeholder NEED, propose exactly:
- PARENT: a single top-level requirement sentence (use 'shall'), covering the overall capability.
- CHILDREN: 3–8 singular child requirements that decompose the parent, each testable.

Return strictly in this format (no extra prose):
PARENT: <one sentence>
CHILDREN:
- <child 1>
- <child 2>
- <child 3>
- ...

NEED:
\"\"\"{(need_text or '').strip()}\"\"\""""
        raw = get_ai_suggestion(api_key, prompt) or ""
        parent = ""
        m = re.search(r'(?im)^\s*PARENT\s*:\s*(.+)$', raw)
        if m: parent = m.group(1).strip()
        children = _parse_children_lines(raw.split("CHILDREN", 1)[-1] if "CHILDREN" in raw else raw)
        return parent, children

    with decomp_top[1]:
        if st.button("🧩 Generate Decomposition"):
            if S["decomp_source"] == "Final Requirement":
                if not S.get("final_req","").strip():
                    st.error("Enter or load a Final requirement first.")
                else:
                    parent_text = S["final_req"].strip()
                    parent_id = (S.get("final_parent_id","").strip()
                                 if S.get("final_role","Parent") == "Child" and S.get("final_parent_id","").strip()
                                 else S.get("final_id","").strip())
                    if not st.session_state.api_key:
                        st.warning("Enter your Google AI API Key to generate children.")
                    else:
                        raw = decompose_requirement_with_ai(st.session_state.api_key, parent_text) or ""
                        S["last_ai_raw"] = raw
                        kids = _parse_children_lines(raw)
                        rows = []
                        base = parent_id or "REQ-000"
                        for i, txt in enumerate(kids, start=1):
                            rows.append({"ID": f"{base}.{i}", "ParentID": parent_id, "Requirement Text": txt})
                        S["decomp_parent_text"] = parent_text
                        S["decomp_parent_id"] = parent_id
                        S["decomp_rows"] = rows
                        S["scroll_to"] = "decomp"
                        st.rerun()
            else:
                if not st.session_state.api_key:
                    st.warning("Enter your Google AI API Key.")
                elif not S["need_text"].strip():
                    st.error("Please enter the stakeholder need first.")
                else:
                    with st.spinner("Creating parent and children…"):
                        ptxt, kids = _ai_parent_and_children_from_need(st.session_state.api_key, S["need_text"])
                    S["decomp_parent_text"] = (ptxt or "").strip()
                    S["decomp_parent_id"] = S.get("final_id","").strip()
                    rows = []
                    base = S["decomp_parent_id"] or "REQ-000"
                    for i, txt in enumerate(kids, start=1):
                        rows.append({"ID": f"{base}.{i}", "ParentID": S["decomp_parent_id"], "Requirement Text": txt})
                    S["decomp_rows"] = rows
                    S["scroll_to"] = "decomp"
                    st.rerun()

    # ---- Editable Parent (for decomposition) ----
    st.markdown("<div id='decomp_section'></div>", unsafe_allow_html=True)
    if S["decomp_parent_text"] or S["decomp_rows"]:
        st.markdown("**Decomposition Parent**")
        dpc1, dpc2 = st.columns([3,1])
        with dpc1:
            S["decomp_parent_text"] = st.text_input("Parent Requirement (editable)",
                                                    value=S["decomp_parent_text"], key="decomp_parent_text_edit")
        with dpc2:
            S["decomp_parent_id"] = st.text_input("Parent ID (editable)",
                                                  value=S["decomp_parent_id"], placeholder="e.g., REQ-010",
                                                  key="decomp_parent_id_edit")

    # ---- Editable Children table ----
    if S.get("decomp_rows"):
        st.markdown("**Children (edit / add / delete)**")
        parent_id = (S.get("decomp_parent_id","") or "").strip()
        new_rows = []
        for idx, row in enumerate(S["decomp_rows"], start=1):
            cols = st.columns([0.07, 0.63, 0.20, 0.10])
            with cols[0]:
                st.write(f"{idx}.")
            with cols[1]:
                txt = st.text_input("Child Requirement", value=row.get("Requirement Text",""), key=f"decomp_child_txt_{idx}")
            with cols[2]:
                cid = st.text_input("Child ID", value=row.get("ID",""), key=f"decomp_child_id_{idx}")
            with cols[3]:
                if st.button("🗑️", key=f"decomp_child_del_{idx}"):
                    S["decomp_rows"].pop(idx-1)
                    st.rerun()
            new_rows.append({"Requirement Text": txt, "ID": cid})

        rows_persist = []
        for r in new_rows:
            rows_persist.append({"ID": r["ID"] or "", "ParentID": parent_id, "Requirement Text": r["Requirement Text"]})
        S["decomp_rows"] = rows_persist

        btns = st.columns([1,1,2])
        with btns[0]:
            if st.button("➕ Add Child"):
                base = parent_id or "REQ-000"
                next_idx = len(S["decomp_rows"]) + 1
                S["decomp_rows"].append({"ID": f"{base}.{next_idx}", "ParentID": parent_id, "Requirement Text":"New child requirement"})
                st.rerun()
        with btns[1]:
            if st.button("🔢 Renumber Children"):
                base = parent_id or "REQ-000"
                ren = []
                for i, r in enumerate(S["decomp_rows"], start=1):
                    ren.append({"ID": f"{base}.{i}", "ParentID": parent_id, "Requirement Text": r["Requirement Text"]})
                S["decomp_rows"] = ren
                st.success("Children renumbered.")

        df = pd.DataFrame(S["decomp_rows"])
        st.download_button("Download Decomposition (CSV)",
                           df.to_csv(index=False).encode("utf-8"),
                           file_name="Decomposition.csv",
                           mime="text/csv",
                           key="dl_decomp_csv")

    else:
        st.info("Use **🧩 Generate Decomposition** to create a parent and children set from the Need or from the Final requirement.")

    # ---------- Raw AI output (optional) ----------
    if S.get("last_ai_raw"):
        with st.expander("Show last AI output (raw)"):
            st.code(S["last_ai_raw"])

    # ---------- Smooth scroll ----------
    if S.get("scroll_to") == "decomp":
        components.html("""
            <script>
              const el = document.getElementById('decomp_section');
              if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
            </script>
        """, height=0)
        S["scroll_to"] = ""

    # =========================
    # Professional CSV Export
    # =========================
    st.subheader("Export Requirements (Professional CSV)")

    def _g(val, default=""):  # safe get
        return (val or default).strip() if isinstance(val, str) else (val if val is not None else default)

    # Decide the "parent" row for export
    parent_text = _g(S.get("decomp_parent_text")) or _g(S.get("final_req")) or _g(S.get("preview_req"))
    parent_id   = _g(S.get("decomp_parent_id"))   or _g(S.get("final_id"))
    role        = S.get("final_role","Parent")
    src         = S.get("decomp_source","Need")  # "Need" or "Final Requirement"
    req_type    = S.get("req_type","Functional")
    priority    = S.get("priority","Should")
    lifecycle   = S.get("lifecycle","Operations")
    stakeholder = S.get("stakeholder","")
    rationale   = _g(S.get("rationale"))
    verification = ""
    if req_type == "Performance":
        verification = S.get("Performance",{}).get("verification","") or ""

    # Acceptance criteria (only for the parent/final)
    ac_joined = " | ".join(S.get("final_ac", [])) if S.get("final_ac") else ""

    rows = []

    # Parent row
    if parent_text or parent_id:
        rows.append({
            "ID": parent_id,
            "ParentID": "",
            "Requirement Text": parent_text,
            "Type": req_type,
            "Role": "Parent" if role == "Parent" or not parent_id else role,
            "Priority": priority,
            "Lifecycle": lifecycle,
            "Stakeholder": stakeholder,
            "Source": src,  # Need / Final Requirement
            "Verification": verification,
            "Acceptance Criteria": ac_joined,
            "Rationale": rationale
        })

    # Child rows from decomposition
    for child in (S.get("decomp_rows") or []):
        rows.append({
            "ID": _g(child.get("ID")),
            "ParentID": _g(child.get("ParentID") or parent_id),
            "Requirement Text": _g(child.get("Requirement Text")),
            "Type": req_type,
            "Role": "Child",
            "Priority": priority,
            "Lifecycle": lifecycle,
            "Stakeholder": stakeholder,
            "Source": src,
            "Verification": "",
            "Acceptance Criteria": "",
            "Rationale": rationale
        })

    if not rows:
        st.info("No requirements to export yet. Enter a Final or Decomposition first.")
    else:
        df_pro = pd.DataFrame(rows, columns=[
            "ID","ParentID","Requirement Text","Type","Role","Priority","Lifecycle","Stakeholder",
            "Source","Verification","Acceptance Criteria","Rationale"
        ])
        st.download_button(
            "⬇️ Download Requirements (CSV)",
            data=df_pro.to_csv(index=False).encode("utf-8"),
            file_name="Requirements_Export.csv",
            mime="text/csv",
            key="pro_export_csv"
        )
