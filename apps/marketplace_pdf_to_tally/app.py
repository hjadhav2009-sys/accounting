
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

from shared.paths import OUTPUT_DIR
from shared import database as db
from apps.marketplace_pdf_to_tally.engine import parse_marketplace_pdf, build_xml
from apps.marketplace_pdf_to_tally.smart_audit import audit_files, audit_rows, summary_message

def render_marketplace_pdf_to_tally_app():
    db.init_db()
    st.title("Marketplace PDF → Tally XML")
    st.caption("Smart Audit build: parser + self-check + shared ledger database. Unknown/new items go to REVIEW/Suspense; total hints are shown as INFO, not false blocking errors.")

    company = st.selectbox("Company profile", [c["name"] for c in db.companies()])
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "1 Upload PDFs",
        "2 On-Spot Mapping",
        "3 Preview & Validate",
        "4 Smart Audit",
        "5 Export XML",
        "6 QA Report",
    ])

    with tab1:
        files = st.file_uploader("Upload Amazon / Flipkart / Meesho / Myntra / Valmo PDFs", type=["pdf"], accept_multiple_files=True)
        if files and st.button("Scan PDFs", type="primary"):
            frames = []
            errors = []
            saved_paths = []
            progress = st.progress(0)
            temp_dir = Path(tempfile.mkdtemp(prefix="marketplace_pdf_audit_"))
            for idx, f in enumerate(files, start=1):
                safe_name = Path(f.name).name
                tmp_path = temp_dir / safe_name
                tmp_path.write_bytes(f.read())
                saved_paths.append(str(tmp_path))
                try:
                    frames.append(parse_marketplace_pdf(str(tmp_path), company, safe_name))
                except Exception as e:
                    errors.append(f"{safe_name}: {e}")
                progress.progress(idx / len(files))

            st.session_state["mp_pdf_paths"] = saved_paths
            if frames:
                df = pd.concat(frames, ignore_index=True)
                st.session_state["mp_df"] = df
                fa = audit_files(saved_paths, df)
                ra = audit_rows(df)
                st.session_state["mp_file_audit"] = fa
                st.session_state["mp_row_audit"] = ra

                st.success(f"Scanned {len(files)} PDFs and created {len(df)} rows.")
                st.info(summary_message(fa, ra))
                st.dataframe(df, width="stretch")
            if errors:
                st.error("\n".join(errors))

    with tab2:
        st.header("On-Spot Mapping")
        st.caption("Here you can save fee ledger mapping, party ledgers, and GST ledgers for this selected company.")

        comp_now = db.company(company)
        with st.expander("GST ledgers for this company", expanded=True):
            g1, g2, g3 = st.columns(3)
            new_cgst = g1.text_input("CGST ledger", comp_now.get("cgst_ledger", "INPUT CGST"))
            new_sgst = g2.text_input("SGST ledger", comp_now.get("sgst_ledger", "INPUT SGST"))
            new_igst = g3.text_input("IGST ledger", comp_now.get("igst_ledger", "INPUT IGST"))
            if st.button("Save GST ledgers"):
                comp_now["cgst_ledger"] = new_cgst.strip()
                comp_now["sgst_ledger"] = new_sgst.strip()
                comp_now["igst_ledger"] = new_igst.strip()
                db.save_company(comp_now)
                st.success("GST ledgers saved.")

        with st.expander("Party ledgers quick check", expanded=True):
            party_rows = []
            for pf in ["amazon", "flipkart", "meesho", "meesho_limited", "meesho_technologies", "valmo", "myntra", "unknown"]:
                party_rows.append({"platform": pf, "party_ledger_used_in_xml": db.party_ledger(company, pf)})
            party_df = pd.DataFrame(party_rows)
            st.dataframe(party_df, width="stretch")
            if (party_df[party_df["platform"] != "unknown"]["party_ledger_used_in_xml"].astype(str).str.lower() == "suspense").any():
                st.error("One marketplace party ledger is still Suspense. Fix Party Ledgers in Shared Database before exporting.")
            else:
                st.success("Party ledgers are ready. XML will use these names.")

        df = st.session_state.get("mp_df", pd.DataFrame()).copy()
        if df.empty:
            st.info("Scan PDFs first.")
        else:
            patterns = df.groupby(["Platform", "Description"], dropna=False).agg(
                count=("Description", "count"),
                total_taxable=("Taxable", "sum"),
                current_ledger=("Mapped Ledger", "first"),
                matched_by=("Matched By", "first"),
            ).reset_index().rename(columns={"Description": "pattern"})
            patterns["new_ledger"] = patterns.apply(
                lambda r: "" if r["matched_by"] in ["UNMATCHED_TO_SUSPENSE", "NO_PARSE"] else r["current_ledger"],
                axis=1
            )
            edited = st.data_editor(patterns, num_rows="dynamic", width="stretch")
            if st.button("Save mappings to shared database", type="primary"):
                for _, r in edited.iterrows():
                    ledger = str(r.get("new_ledger", "")).strip()
                    if ledger:
                        db.add_mapping(company, "marketplace", str(r.get("Platform", "")), str(r.get("pattern", "")), ledger)
                st.success("Saved. Scan again to apply mappings automatically.")

    with tab3:
        df = st.session_state.get("mp_df", pd.DataFrame()).copy()
        if df.empty:
            st.warning("Scan PDFs first.")
        else:
            st.info("Check REVIEW rows before export. You can edit ledger/amounts/import checkbox here.")
            edited = st.data_editor(df, num_rows="dynamic", width="stretch")
            st.session_state["mp_df"] = edited
            # Re-audit after manual edits.
            pdf_paths = st.session_state.get("mp_pdf_paths", [])
            if pdf_paths:
                st.session_state["mp_file_audit"] = audit_files(pdf_paths, edited)
                st.session_state["mp_row_audit"] = audit_rows(edited)
            st.subheader("Totals")
            totals = edited.groupby(["Platform", "PDF Doc Type", "Tally Voucher Type", "Status"], dropna=False)[["Taxable", "CGST", "SGST", "IGST", "Total"]].sum().reset_index()
            st.dataframe(totals, width="stretch")

    with tab4:
        st.header("Smart Audit")
        df = st.session_state.get("mp_df", pd.DataFrame()).copy()
        pdf_paths = st.session_state.get("mp_pdf_paths", [])
        if df.empty or not pdf_paths:
            st.warning("Scan PDFs first.")
        else:
            if st.button("Run Smart Audit again"):
                st.session_state["mp_file_audit"] = audit_files(pdf_paths, df)
                st.session_state["mp_row_audit"] = audit_rows(df)

            fa = st.session_state.get("mp_file_audit", audit_files(pdf_paths, df))
            ra = st.session_state.get("mp_row_audit", audit_rows(df))
            msg = summary_message(fa, ra)

            if msg.startswith("SAFE"):
                st.success(msg)
            else:
                st.warning(msg)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("PDFs", len(fa))
            c2.metric("Review PDFs", int((fa["Result"] != "SAFE").sum()) if not fa.empty else 0)
            c3.metric("Parsed rows", len(df))
            c4.metric("Row issues", len(ra))

            st.subheader("PDF-level audit")
            st.dataframe(fa, width="stretch")

            st.subheader("Row-level issues")
            if ra.empty:
                st.success("No row-level issues found.")
            else:
                st.dataframe(ra, width="stretch")

            st.caption("Smart Audit is a safety check. Result=REVIEW blocks attention; Info is only a hint and may happen because marketplace PDFs show totals/signs differently.")

    with tab5:
        df = st.session_state.get("mp_df", pd.DataFrame()).copy()
        if df.empty:
            st.warning("Preview first.")
        else:
            fa = st.session_state.get("mp_file_audit", pd.DataFrame())
            ra = st.session_state.get("mp_row_audit", pd.DataFrame())
            if not fa.empty and ((fa["Result"] != "SAFE").any() or not ra.empty):
                st.warning("Smart Audit found REVIEW items. You can still export, but check them first.")

            export_review = st.checkbox("Export REVIEW rows also", value=False, help="Safer default is OFF. Turn on only after checking review rows.")
            xml = build_xml(df, company, export_review=export_review)
            out = OUTPUT_DIR / "marketplace_pdf_tally.xml"
            out.write_text(xml, encoding="utf-8")
            st.success("XML created.")
            st.download_button("Download marketplace_pdf_tally.xml", xml, file_name="marketplace_pdf_tally.xml", mime="application/xml")
            st.text_area("XML preview", xml[:8000], height=420)

    with tab6:
        st.header("QA Report")
        df = st.session_state.get("mp_df", pd.DataFrame()).copy()
        if df.empty:
            st.info("Scan PDFs first.")
        else:
            total_files = df["Source PDF"].nunique()
            failed_files = df[df["Status"].astype(str).str.contains("PARSE_FAILED", na=False)]["Source PDF"].nunique()
            review_rows = df[~df["Status"].astype(str).str.startswith("OK")]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("PDF files", total_files)
            c2.metric("Rows", len(df))
            c3.metric("Review rows", len(review_rows))
            c4.metric("Parse failed PDFs", failed_files)

            st.subheader("Problem rows")
            st.dataframe(review_rows, width="stretch")

            st.subheader("Invoice totals")
            inv = df.groupby(["Source PDF", "Platform", "PDF Doc Type", "Invoice No"], dropna=False)[["Taxable", "CGST", "SGST", "IGST", "Total"]].sum().reset_index()
            st.dataframe(inv, width="stretch")
