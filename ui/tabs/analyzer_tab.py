# ui/tabs/analyzer_tab.py
import os
import re
import docx
import pandas as pd
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import streamlit as st

def render(st, db, rule_engine, CTX):
    """
    Document Analyzer tab.
    Expects:
      - db: your db module (already imported/reloaded in app.py)
      - rule_engine: RuleEngine instance (or stub)
      - CTX: dict of helpers injected from app.py
    """
    # pull helpers from CTX (exact same logic as before)
    HAS_AI_PARSER = CTX.get("HAS_AI_PARSER", False)
    get_ai_suggestion = CTX["get_ai_suggestion"]
    decompose_requirement_with_ai = CTX["decompose_requirement_with_ai"]
    extract_requirements_with_ai = CTX.get("extract_requirements_with_ai")

    _read_docx_text_and_rows = CTX["_read_docx_text_and_rows"]
    _read_docx_text_and_rows_from_path = CTX["_read_docx_text_and_rows_from_path"]
    _extract_requirements_from_table_rows = CTX["_extract_requirements_from_table_rows"]
    extract_requirements_from_string = CTX["extract_requirements_from_string"]
    extract_requirements_from_file = CTX["extract_requirements_from_file"]

    format_requirement_with_highlights = CTX["format_requirement_with_highlights"]
    safe_call_ambiguity = CTX["safe_call_ambiguity"]
    check_passive_voice = CTX["check_passive_voice"]
    check_incompleteness = CTX["check_incompleteness"]
    check_singularity = CTX["check_singularity"]
    safe_clarity_score = CTX["safe_clarity_score"]

    _save_uploaded_file_for_doc = CTX["_save_uploaded_file_for_doc"]

    # ------------------------------ Tab: Analyzer (Unified) ------------------------------
    pname = st.session_state.selected_project[1] if st.session_state.selected_project else None
    if st.session_state.selected_project is None:
        st.header("Analyze Documents & Text")
        st.warning("You can analyze documents without a project, but results won’t be saved.")
    else:
        project_name = st.session_state.selected_project[1]
        st.header(f"Analyze & Add Documents to: {project_name}")

    # ===== Quick Paste Analyzer — persist results so AI buttons work after rerun =====
    st.subheader("🔍 Quick Paste Analyzer — single or small set")
    quick_text = st.text_area(
        "Paste one or more requirements (one per line). You may prefix with an ID like `REQ-001:`",
        height=160,
        key="quick_paste_area"
    )
    st.caption("Example:\nREQ-001: The system shall report position within 500 ms.\nREQ-001.1.")

    # session keys for persistence
    if "quick_results" not in st.session_state:
        st.session_state.quick_results = []   # list of dicts with analysis
    if "quick_issue_counts" not in st.session_state:
        st.session_state.quick_issue_counts = {"Ambiguity":0,"Passive Voice":0,"Incompleteness":0,"Singularity":0}
    if "quick_analyzed" not in st.session_state:
        st.session_state.quick_analyzed = False
    if "quick_text_snapshot" not in st.session_state:
        st.session_state.quick_text_snapshot = ""

    def _parse_quick_lines(raw: str):
        rows = []
        idx = 1
        for ln in (raw or "").splitlines():
            t = ln.strip()
            if not t:
                continue
            if ":" in t:
                left, right = t.split(":", 1)
                rid = left.strip()
                rtx = right.strip()
                if not rtx:
                    continue
            else:
                rid = f"R-{idx:03d}"
                rtx = t
            rows.append((rid, rtx))
            idx += 1
        return rows

    # Local AI helpers
    def _ai_rewrite_clarity(api_key: str, req_text: str) -> str:
        prompt = f"""
You are a senior systems engineer. Rewrite the requirement below to be:
- single sentence, active voice, using "shall"
- unambiguous (no vague terms), testable (include precise conditions/thresholds if implied)
- keep the original intent; do not add scope
- no extra commentary; OUTPUT ONLY the rewritten sentence

Requirement:
\"\"\"{(req_text or '').strip()}\"\"\""""
        out = get_ai_suggestion(api_key, prompt) or ""
        for ln in out.splitlines():
            ln = ln.strip()
            if ln:
                return ln
        return out.strip()

    def _ai_decompose_clean(api_key: str, req_text: str) -> str:
        return decompose_requirement_with_ai(api_key, req_text) or ""

    # Analyze button stores results in session so later AI button clicks don't lose state
    if st.button("Analyze Pasted Lines", key="quick_analyze_btn"):
        pairs = _parse_quick_lines(quick_text)
        if not pairs:
            st.warning("No non-empty lines found.")
            st.session_state.quick_results = []
            st.session_state.quick_issue_counts = {"Ambiguity":0,"Passive Voice":0,"Incompleteness":0,"Singularity":0}
            st.session_state.quick_analyzed = False
            st.session_state.quick_text_snapshot = ""
        else:
            issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0, "Singularity": 0}
            quick_results = []
            for rid, rtx in pairs:
                amb = safe_call_ambiguity(rtx, rule_engine)
                pas = check_passive_voice(rtx)
                inc = check_incompleteness(rtx)
                try:
                    sing = check_singularity(rtx)
                except Exception:
                    sing = []
                if amb: issue_counts["Ambiguity"] += 1
                if pas: issue_counts["Passive Voice"] += 1
                if inc: issue_counts["Incompleteness"] += 1
                if sing: issue_counts["Singularity"] += 1
                quick_results.append({
                    "id": rid, "text": rtx,
                    "ambiguous": amb, "passive": pas, "incomplete": inc, "singularity": sing
                })
            # persist
            st.session_state.quick_results = quick_results
            st.session_state.quick_issue_counts = issue_counts
            st.session_state.quick_analyzed = True
            st.session_state.quick_text_snapshot = quick_text

    # ---- Render quick results if we have them in session ----
    if st.session_state.quick_analyzed and st.session_state.quick_results:
        quick_results = st.session_state.quick_results
        issue_counts = st.session_state.quick_issue_counts

        total = len(quick_results)
        flagged = sum(1 for r in quick_results if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"])
        st.markdown(f"**Analyzed:** {total} • **Flagged:** {flagged}")
        cqa = st.columns(4)
        cqa[0].metric("Ambiguity", issue_counts["Ambiguity"])
        cqa[1].metric("Passive", issue_counts["Passive Voice"])
        cqa[2].metric("Incomplete", issue_counts["Incompleteness"])
        cqa[3].metric("Multiple actions", issue_counts["Singularity"])

        flagged_list = [r for r in quick_results if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]]
        clear_list   = [r for r in quick_results if not (r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"])]

        st.subheader("Flagged")
        if not flagged_list:
            st.caption("None 🎉")
        for r in flagged_list:
            with st.container():
                st.markdown(
                    format_requirement_with_highlights(r["id"], r["text"], r),
                    unsafe_allow_html=True,
                )

                # Always offer AI Rewrite for flagged lines; persist output to CSV via cache key
                col_rw, col_dc = st.columns(2)
                with col_rw:
                    if st.session_state.api_key and st.button(f"✨ AI Rewrite {r['id']}", key=f"quick_rew_{r['id']}"):
                        try:
                            hints = []
                            if r["ambiguous"]: hints.append(f"remove ambiguity ({', '.join(r['ambiguous'])})")
                            if r["passive"]:   hints.append("use active voice")
                            if r["incomplete"]:hints.append("complete the sentence")
                            guidance = "; ".join(hints) if hints else "ensure clarity, singularity, and testability"
                            prompt = f"""Rewrite as ONE clear, singular, verifiable requirement using 'shall' in active voice; {guidance}.
Original: \"\"\"{r['text']}\"\"\""""
                            suggestion = get_ai_suggestion(st.session_state.api_key, prompt)
                            st.session_state[f"rewritten_cache_{r['id']}"] = (suggestion or "").strip()
                            st.info("AI Rewrite:")
                            st.markdown(f"> {suggestion}")
                        except Exception as e:
                            st.warning(f"AI rewrite failed: {e}")

                with col_dc:
                    if st.session_state.api_key and r["singularity"] and st.button(f"🧩 Decompose {r['id']}", key=f"quick_dec_{r['id']}"):
                        try:
                            d = _ai_decompose_clean(st.session_state.api_key, f"{r['id']} {r['text']}")
                            st.info("AI Decomposition:")
                            st.markdown(d)
                        except Exception as e:
                            st.warning(f"AI decomposition failed: {e}")

        st.subheader("Clear")
        for r in clear_list:
            st.markdown(
                f'<div style="background-color:#D4EDDA;color:#155724;padding:10px;'
                f'border-radius:5px;margin-bottom:10px;">✅ <strong>{r["id"]}</strong> {r["text"]}</div>',
                unsafe_allow_html=True,
            )

        # CSV export (includes any AI rewrites the user triggered)
        exp_rows = []
        for r in quick_results:
            issues = []
            if r["ambiguous"]: issues.append(f"Ambiguity: {', '.join(r['ambiguous'])}")
            if r["passive"]:   issues.append(f"Passive Voice: {', '.join(r['passive'])}")
            if r["incomplete"]:issues.append("Incompleteness")
            if r["singularity"]:issues.append(f"Singularity: {', '.join(r['singularity'])}")
            ai_rew = st.session_state.get(f"rewritten_cache_{r['id']}", "")
            exp_rows.append({
                "Requirement ID": r["id"],
                "Requirement Text": r["text"],
                "Status": "Clear" if not issues else "Flagged",
                "Issues Found": "; ".join(issues),
                "AI Rewrite (if generated)": ai_rew,
            })
        df_quick = pd.DataFrame(exp_rows)
        st.download_button(
            "Download Quick Analysis (CSV)",
            data=df_quick.to_csv(index=False).encode("utf-8"),
            file_name="ReqCheck_Quick_Analysis.csv",
            mime="text/csv",
            key="dl_quick_csv"
        )

    # ===================== Full Document Analyzer (unchanged logic) =====================
    st.subheader("📁 Upload Documents — analyze one or more files")
    use_ai_parser = st.toggle("Use Advanced AI Parser (requires API key)")
    if use_ai_parser and not (HAS_AI_PARSER and st.session_state.api_key):
        st.info("AI Parser not available (missing function or API key). Falling back to Standard Parser.")

    project_id = st.session_state.selected_project[0] if st.session_state.selected_project else None

    stored_to_analyze = None
    if project_id is not None and hasattr(db, "get_documents_for_project"):
        try:
            _rows = db.get_documents_for_project(project_id)
            stored_docs, labels = [], []
            for (doc_id, file_name, version, uploaded_at, clarity_score) in _rows:
                conv_path = os.path.join("data", "projects", str(project_id), "documents",
                                         f"{doc_id}_{CTX['_sanitize_filename'](file_name)}")
                if os.path.exists(conv_path):
                    stored_docs.append((doc_id, file_name, version, conv_path))
                    labels.append(f"{file_name} (v{version})")
            if stored_docs:
                sel = st.selectbox("Re-analyze a saved document:", ["— Select —"] + labels, key="rean_select")
                if sel != "— Select —":
                    if st.button("Analyze Selected", key="rean_btn"):
                        idx = labels.index(sel)
                        _doc_id, _fn, _ver, _path = stored_docs[idx]
                        stored_to_analyze = (_fn, _path)
        except Exception:
            pass

    uploaded_files = st.file_uploader(
        "Upload one or more requirements documents (.txt or .docx)",
        type=['txt', 'docx'],
        accept_multiple_files=True,
        key=f"uploader_unified_{project_id or 'none'}",
    )

    example_files = {"Choose an example...": None, "Drone System SRS (Complex Example)": "DRONE_SRS_v1.0.docx"}
    selected_example = st.selectbox(
        "Or, select an example to analyze:",
        options=list(example_files.keys()),
        key="example_unified",
    )

    docs_to_process = []
    if uploaded_files:
        for up in uploaded_files:
            docs_to_process.append(("upload", up.name, up))
    if selected_example != "Choose an example...":
        example_path = example_files[selected_example]
        try:
            if example_path.endswith(".docx"):
                d = docx.Document(example_path)
                example_text = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
            else:
                with open(example_path, "r", encoding="utf-8") as f:
                    example_text = f.read()
            docs_to_process.append(("example", selected_example, example_text))
        except FileNotFoundError:
            st.error(f"Example file not found: {example_path}. Place it in the project folder.")
    if stored_to_analyze:
        _fn, _path = stored_to_analyze
        docs_to_process.append(("stored", _fn, _path))

    # ===================== Analyzer-local AI helpers (shared) =====================
    def _ai_rewrite_clarity_doc(api_key: str, req_text: str) -> str:
        prompt = f"""
You are a senior systems engineer. Rewrite the requirement below to be:
- single sentence, active voice, using "shall"
- unambiguous and testable
- keep the original intent; no scope changes
- OUTPUT ONLY the rewritten sentence
Requirement:
\"\"\"{(req_text or '').strip()}\"\"\""""
        out = get_ai_suggestion(st.session_state.api_key, prompt) or ""
        for ln in out.splitlines():
            ln = ln.strip()
            if ln:
                return ln
        return out.strip()

    def _ai_decompose_clean_doc(api_key: str, req_text: str) -> str:
        return decompose_requirement_with_ai(api_key, req_text) or ""
    # ============================================================================

    if docs_to_process:
        with st.spinner("Processing and analyzing documents..."):
            saved_count = 0
            for src_type, display_name, payload in docs_to_process:
                # --- Extract requirements (AI or standard) ---
                if src_type == "upload":
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        if payload.name.endswith(".txt"):
                            raw = payload.getvalue().decode("utf-8", errors="ignore")
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                            if not reqs and raw:
                                reqs = extract_requirements_from_string(raw)
                        elif payload.name.endswith(".docx"):
                            flat_text, table_rows = _read_docx_text_and_rows(payload)
                            table_reqs = _extract_requirements_from_table_rows(table_rows)
                            if table_reqs:
                                reqs = table_reqs
                                raw = None
                            else:
                                raw = flat_text
                                reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                                if not reqs and raw:
                                    reqs = extract_requirements_from_string(raw)
                        else:
                            raw = ""
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw)
                    else:
                        reqs = extract_requirements_from_file(payload)

                elif src_type == "stored":
                    path = payload
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        if path.endswith(".txt"):
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                raw = f.read()
                            reqs = extract_requirements_with_ai(st.session_state.api_key, raw) or extract_requirements_from_string(raw)
                        elif path.endswith(".docx"):
                            flat_text, table_rows = _read_docx_text_and_rows_from_path(path)
                            table_reqs = _extract_requirements_from_table_rows(table_rows)
                            if table_reqs:
                                reqs = table_reqs
                            else:
                                reqs = extract_requirements_with_ai(st.session_state.api_key, flat_text) or extract_requirements_from_string(flat_text)
                        else:
                            reqs = []
                    else:
                        if path.endswith(".txt"):
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                raw = f.read()
                            reqs = extract_requirements_from_string(raw)
                        elif path.endswith(".docx"):
                            flat_text, table_rows = _read_docx_text_and_rows_from_path(path)
                            reqs = _extract_requirements_from_table_rows(table_rows) or extract_requirements_from_string(flat_text)
                        else:
                            reqs = []

                else:  # example
                    if use_ai_parser and HAS_AI_PARSER and st.session_state.api_key:
                        reqs = extract_requirements_with_ai(st.session_state.api_key, payload)
                    else:
                        reqs = extract_requirements_from_string(payload)

                total_reqs = len(reqs)
                if total_reqs == 0:
                    st.warning(f"⚠️ No recognizable requirements in **{display_name}**.")
                    continue

                # --- Analyze requirements ---
                results = []
                issue_counts = {"Ambiguity": 0, "Passive Voice": 0, "Incompleteness": 0, "Singularity": 0}

                for rid, rtext in reqs:
                    ambiguous = safe_call_ambiguity(rtext, rule_engine)
                    passive = check_passive_voice(rtext)
                    incomplete = check_incompleteness(rtext)
                    try:
                        singular = check_singularity(rtext)
                    except Exception:
                        singular = []

                    if ambiguous:
                        issue_counts["Ambiguity"] += 1
                    if passive:
                        issue_counts["Passive Voice"] += 1
                    if incomplete:
                        issue_counts["Incompleteness"] += 1
                    if singular:
                        issue_counts["Singularity"] += 1

                    results.append({
                        "id": rid,
                        "text": rtext,
                        "ambiguous": ambiguous,
                        "passive": passive,
                        "incomplete": incomplete,
                        "singularity": singular,
                    })

                flagged_total = sum(
                    1 for r in results
                    if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                )
                clarity_score = int(((total_reqs - flagged_total) / total_reqs) * 100) if total_reqs else 100

                # --- Save to DB if helpers exist and a project is selected (new inputs only) ---
                if (st.session_state.selected_project is not None) and (src_type in ("upload", "example")):
                    project_id = st.session_state.selected_project[0]
                    try:
                        if hasattr(db, "add_document") and hasattr(db, "add_requirements") and hasattr(db, "get_documents_for_project"):
                            existing = []
                            try:
                                existing = [d for d in db.get_documents_for_project(project_id) if d[1] == display_name]
                            except Exception:
                                existing = []
                            next_version = (max([d[2] for d in existing], default=0) + 1)
                            doc_id = db.add_document(project_id, display_name, next_version, clarity_score)
                            db.add_requirements(doc_id, reqs)

                            if src_type == "upload":
                                try:
                                    file_path = _save_uploaded_file_for_doc(project_id, doc_id, display_name, payload)
                                    if hasattr(db, "add_document_file"):
                                        try:
                                            db.add_document_file(doc_id, file_path)
                                        except Exception:
                                            pass
                                    elif hasattr(db, "set_document_file_path"):
                                        try:
                                            db.set_document_file_path(doc_id, file_path)
                                        except Exception:
                                            pass
                                except Exception as _e:
                                    st.warning(f"Saved analysis, but file persistence failed for '{display_name}': {_e}")

                        elif hasattr(db, "add_document_to_project") and hasattr(db, "add_requirements_to_document"):
                            doc_id = db.add_document_to_project(project_id, display_name, clarity_score)
                            db.add_requirements_to_document(doc_id, reqs)

                            if src_type == "upload":
                                try:
                                    file_path = _save_uploaded_file_for_doc(project_id, doc_id, display_name, payload)
                                    if hasattr(db, "add_document_file"):
                                        try:
                                            db.add_document_file(doc_id, file_path)
                                        except Exception:
                                            pass
                                    elif hasattr(db, "set_document_file_path"):
                                        try:
                                            db.set_document_file_path(doc_id, file_path)
                                        except Exception:
                                            pass
                                except Exception as _e:
                                    st.warning(f"Saved analysis, but file persistence failed for '{display_name}': {_e}")
                        else:
                            st.info("Analysis done — DB helpers not found, so nothing was saved.")
                    except Exception as e:
                        st.warning(f"Saved analysis for **{display_name}**, but DB write failed: {e}")

                # --- Per-document results UI ---
                with st.expander(f"📄 {display_name} — Clarity {clarity_score}/100 • {total_reqs} requirements"):
                    flagged_total = sum(
                        1 for r in results
                        if r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                    )
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Requirements", total_reqs)
                    c2.metric("Flagged", flagged_total)
                    c3.metric("Clarity Score", f"{clarity_score} / 100")
                    st.progress(clarity_score)

                    # --- Export CSV for this single document (includes AI Rewrite) ---
                    export_rows = []
                    for r in results:
                        issues = []
                        if r["ambiguous"]:
                            issues.append(f"Ambiguity: {', '.join(r['ambiguous'])}")
                        if r["passive"]:
                            issues.append(f"Passive Voice: {', '.join(r['passive'])}")
                        if r["incomplete"]:
                            issues.append("Incompleteness")
                        if r["singularity"]:
                            issues.append(f"Singularity: {', '.join(r['singularity'])}")

                        ai_rew = st.session_state.get(f"rewritten_cache_{r['id']}", "")

                        export_rows.append({
                            "Document": display_name,
                            "Requirement ID": r["id"],
                            "Requirement Text": r["text"],
                            "Status": "Clear" if not issues else "Flagged",
                            "Issues Found": "; ".join(issues),
                            "AI Rewrite (if generated)": ai_rew,
                        })

                    df_doc = pd.DataFrame(export_rows)
                    csv_doc = df_doc.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"Download '{display_name}' Analysis (CSV)",
                        data=csv_doc,
                        file_name=f"{os.path.splitext(display_name)[0]}_ReqCheck_Report.csv",
                        mime="text/csv",
                        key=f"dl_csv_{display_name}",
                    )

                    st.subheader("Issues by Type")
                    st.bar_chart(issue_counts)

                    # Word cloud of ambiguous terms
                    all_ambiguous_words = []
                    for r in results:
                        if r["ambiguous"]:
                            all_ambiguous_words.extend(r["ambiguous"])
                    with st.expander("Common Weak Words (Word Cloud)"):
                        if all_ambiguous_words:
                            text_for_cloud = " ".join(all_ambiguous_words)
                            wordcloud = WordCloud(
                                width=800, height=300, background_color="white", collocations=False
                            ).generate(text_for_cloud)
                            fig, ax = plt.subplots()
                            ax.imshow(wordcloud, interpolation="bilinear")
                            ax.axis("off")
                            st.pyplot(fig)
                        else:
                            st.write("No ambiguous words found.")

                    st.subheader("Detailed Analysis")
                    for r in results:
                        is_flagged = r["ambiguous"] or r["passive"] or r["incomplete"] or r["singularity"]
                        if is_flagged:
                            with st.container(border=True):
                                st.markdown(
                                    format_requirement_with_highlights(r["id"], r["text"], r),
                                    unsafe_allow_html=True,
                                )
                                if r["ambiguous"]:
                                    st.caption(f"ⓘ **Ambiguity:** {', '.join(r['ambiguous'])}")
                                if r["passive"]:
                                    st.caption(f"ⓘ **Passive Voice:** {', '.join(r['passive'])}")
                                if r["incomplete"]:
                                    st.caption("ⓘ **Incompleteness** detected.")
                                if r["singularity"]:
                                    st.caption(f"ⓘ **Singularity:** {', '.join(r['singularity'])}")

                                # Count issue categories
                                issue_types_present = sum([
                                    1 if r["ambiguous"] else 0,
                                    1 if r["passive"] else 0,
                                    1 if r["incomplete"] else 0,
                                    1 if r["singularity"] else 0,
                                ])

                                if issue_types_present >= 2:
                                    # Enhanced flow: Fix → Decompose
                                    with st.expander("✨ AI Suggestions (Fix clarity first, then decompose)"):
                                        if not st.session_state.api_key:
                                            st.warning("Please enter your Google AI API Key.")
                                        else:
                                            issues_summary = []
                                            if r["ambiguous"]:    issues_summary.append("Ambiguity")
                                            if r["passive"]:      issues_summary.append("Passive Voice")
                                            if r["incomplete"]:   issues_summary.append("Incompleteness")
                                            if r["singularity"]:  issues_summary.append("Non-singular")
                                            if issues_summary:
                                                st.caption("Issues detected: " + ", ".join(issues_summary))

                                            cache_key = f"rewritten_cache_{r['id']}"
                                            if cache_key not in st.session_state:
                                                st.session_state[cache_key] = ""

                                            btn_row = st.columns([1.3, 1.6, 1.6])
                                            with btn_row[0]:
                                                if st.button(f"⚒️ Fix Clarity (Rewrite) [{r['id']}]", key=f"fix_{r['id']}"):
                                                    with st.spinner("Rewriting to remove ambiguity/passive/incompleteness..."):
                                                        st.session_state[cache_key] = _ai_rewrite_clarity_doc(st.session_state.api_key, r["text"])
                                                    if st.session_state[cache_key]:
                                                        st.success("Rewritten draft ready (see below).")
                                                    else:
                                                        st.info("No rewrite returned.")

                                            with btn_row[1]:
                                                if st.button(f"🧩 Decompose (After Fix) [{r['id']}]", key=f"decomp_after_fix_{r['id']}"):
                                                    with st.spinner("Preparing clean text, then decomposing..."):
                                                        base = st.session_state[cache_key].strip() or _ai_rewrite_clarity_doc(st.session_state.api_key, r["text"])
                                                        decomp = _ai_decompose_clean_doc(st.session_state.api_key, base)
                                                    if decomp.strip():
                                                        st.info("Decomposition (based on cleaned requirement):")
                                                        st.markdown(decomp)
                                                    else:
                                                        st.info("No decomposition returned.")

                                            with btn_row[2]:
                                                if st.button(f"Auto: Fix → Decompose [{r['id']}]", key=f"pipeline_{r['id']}]"):
                                                    with st.spinner("Rewriting, then decomposing..."):
                                                        cleaned = st.session_state[cache_key].strip() or _ai_rewrite_clarity_doc(st.session_state.api_key, r["text"])
                                                        st.session_state[cache_key] = cleaned
                                                        decomp = _ai_decompose_clean_doc(st.session_state.api_key, cleaned)
                                                    if cleaned:
                                                        st.success("Rewritten requirement:")
                                                        st.markdown(f"> {cleaned}")
                                                    if decomp.strip():
                                                        st.info("Decomposition:")
                                                        st.markdown(decomp)

                                            if st.session_state.get(cache_key, ""):
                                                st.caption("Rewritten requirement (this will appear in CSV):")
                                                st.code(st.session_state[cache_key])

                                else:
                                    # Lightweight tools
                                    with st.expander("✨ Get AI Rewrite / Decomposition"):
                                        if not st.session_state.api_key:
                                            st.warning("Please enter your Google AI API Key.")
                                        else:
                                            if r["singularity"]:
                                                col1, col2 = st.columns(2)
                                            else:
                                                col1 = st.columns(1)[0]

                                            with col1:
                                                if st.button(f"Rewrite Requirement {r['id']}", key=f"rewrite_{r['id']}"):
                                                    with st.spinner("AI is thinking..."):
                                                        suggestion = _ai_rewrite_clarity_doc(st.session_state.api_key, r['text'])
                                                    st.session_state[f"rewritten_cache_{r['id']}"] = (suggestion or "").strip()
                                                    st.info("AI Suggestion (Rewrite):")
                                                    st.markdown(f"> {suggestion}")

                                            if r["singularity"]:
                                                with col2:
                                                    if st.button(f"Decompose Requirement {r['id']}", key=f"decompose_{r['id']}"):
                                                        with st.spinner("AI is decomposing..."):
                                                            decomposed_reqs = _ai_decompose_clean_doc(
                                                                st.session_state.api_key,
                                                                f"{r['id']} {r['text']}"
                                                            )
                                                        st.info("AI Suggestion (Decomposition):")
                                                        st.markdown(decomposed_reqs)
                        else:
                            st.markdown(
                                f'<div style="background-color:#D4EDDA;color:#155724;padding:10px;'
                                f'border-radius:5px;margin-bottom:10px;">✅ <strong>{r["id"]}</strong> {r["text"]}</div>',
                                unsafe_allow_html=True,
                            )

            # persisted uploader/example resets handled in parent if needed
            st.success("Analysis complete.")

    # --- Project library (document versions) ---
    st.divider()
    st.header("Documents in this Project")

    if st.session_state.selected_project is None:
        st.info("Select a project to view its saved documents.")
    else:
        pid = st.session_state.selected_project[0]
        try:
            if hasattr(db, "get_documents_for_project"):
                rows = db.get_documents_for_project(pid)  # (doc_id, file_name, version, uploaded_at, clarity_score)
                if not rows:
                    st.info("No documents have been added to this project yet.")
                else:
                    # One row per version
                    doc_data = []
                    for (doc_id, file_name, version, uploaded_at, clarity_score) in rows:
                        doc_data.append({
                            "File Name": file_name,
                            "Version": version,
                            "Uploaded On": uploaded_at.replace("T", " ")[:19] if isinstance(uploaded_at, str) else uploaded_at,
                            "Clarity Score": f"{clarity_score} / 100" if clarity_score is not None else "—",
                        })
                    df_docs = pd.DataFrame(doc_data).sort_values(["File Name","Version"], ascending=[True, False])
                    st.dataframe(df_docs, use_container_width=True)

                    # Export summary
                    proj_csv = df_docs.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="Download Project Documents Summary (CSV)",
                        data=proj_csv,
                        file_name=f"Project_{pid}_Documents_Summary.csv",
                        mime="text/csv",
                        key="dl_csv_project_docs",
                    )
            else:
                st.info("get_documents_for_project() not found in db.database.")
        except Exception as e:
            st.error(f"Failed to load documents for this project: {e}")
