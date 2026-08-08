
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

from shared.paths import OUTPUT_DIR
from shared import database as db
from apps.bank_to_tally_xml.engine import load_statement, make_pattern_suggestions, build_xml

def render_bank_xml_app():
    db.init_db()
    st.title("Bank Statement → Tally XML")
    st.caption("Uses Shared Database. Map bank narration one time and reuse for every company.")

    company = st.selectbox("Company profile", [c["name"] for c in db.companies()])
    comp = db.company(company)
    tab1, tab2, tab3, tab4 = st.tabs(["1 Upload & Scan", "2 On-Spot Mapping", "3 Preview/Edit", "4 Export XML"])

    with tab1:
        files = st.file_uploader("Upload one or many bank PDFs / Excel / CSV", type=["pdf","xlsx","xls","csv"], accept_multiple_files=True)
        if files:
            frames = []
            for f in files:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix)
                tmp.write(f.read())
                tmp.close()
                df, account_text = load_statement(tmp.name)
                if not df.empty:
                    df.insert(0, "Source File", f.name)
                frames.append(df)
            if frames:
                df = pd.concat(frames, ignore_index=True)
                st.session_state["bank_df"] = df
                st.session_state["bank_patterns"] = make_pattern_suggestions(df)
                st.success(f"Loaded {len(df)} bank transactions.")
                st.dataframe(df, width="stretch")

    with tab2:
        patterns = st.session_state.get("bank_patterns", pd.DataFrame()).copy()
        if patterns.empty:
            st.info("Upload bank statement first.")
        else:
            ledgers = []
            matches = []
            for _, r in patterns.iterrows():
                ledger, by = db.map_ledger(company, "bank", "", r.get("narration_pattern", ""))
                ledgers.append("" if by == "UNMATCHED_TO_SUSPENSE" else ledger)
                matches.append(by)
            patterns["ledger"] = ledgers
            patterns["matched_by"] = matches
            edited = st.data_editor(patterns, num_rows="dynamic", width="stretch")
            if st.button("Save bank mappings to shared database", type="primary"):
                for _, r in edited.iterrows():
                    ledger = str(r.get("ledger", "")).strip()
                    if ledger:
                        db.add_mapping(company, "bank", "", str(r.get("narration_pattern", "")), ledger)
                st.success("Saved. Upload/preview again to apply.")

    with tab3:
        df = st.session_state.get("bank_df", pd.DataFrame()).copy()
        if df.empty:
            st.warning("Upload bank statement first.")
        else:
            mapped = []
            matched = []
            for _, row in df.iterrows():
                ledger, by = db.map_ledger(company, "bank", "", row.get("Description", ""))
                mapped.append(ledger)
                matched.append(by)
            df["Mapped Ledger"] = mapped
            df["Matched By"] = matched
            df["Voucher Type"] = df.apply(lambda r: "Receipt" if float(r.get("Deposit") or 0) > 0 else ("Payment" if float(r.get("Withdrawal") or 0) > 0 else ""), axis=1)
            df["Import?"] = True
            edited = st.data_editor(df, num_rows="dynamic", width="stretch")
            st.session_state["bank_preview"] = edited

    with tab4:
        df = st.session_state.get("bank_preview", pd.DataFrame()).copy()
        if df.empty:
            st.warning("Preview first.")
        else:
            bdf = db.df_table("bank_accounts", company)
            bank_ledger = str(bdf.iloc[0]["bank_ledger"]) if not bdf.empty else "IDBI BANK -CURRENT"
            settings = {
                "bank_ledger": bank_ledger,
                "unmatched_ledger": comp.get("suspense_ledger", "Suspense"),
                "create_missing_ledgers": False,
                "voucher_number_prefix": "BANK-",
            }
            if "Import?" in df.columns:
                df = df[df["Import?"] == True]
            xml = build_xml(df, settings)
            out = OUTPUT_DIR / "tally_bank_import.xml"
            out.write_text(xml, encoding="utf-8")
            st.success(f"XML created for {len(df)} vouchers.")
            st.download_button("Download tally_bank_import.xml", xml, file_name="tally_bank_import.xml", mime="application/xml")
            st.text_area("XML preview", xml[:6000], height=350)
