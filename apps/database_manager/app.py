
import io
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st
from shared import database as db

TABLES = {
    "companies": ["name", "tally_company_name", "gstin", "state", "suspense_ledger", "cgst_ledger", "sgst_ledger", "igst_ledger"],
    "bank_accounts": ["account_hint", "bank_ledger", "notes"],
    "party_ledgers": ["platform", "party_ledger", "party_gstin", "state"],
    "ledger_mappings": ["tool", "platform", "pattern", "voucher_type", "ledger", "match_type", "enabled", "notes"],
    "voucher_rules": ["platform", "pdf_doc_type", "tally_voucher_type", "sign_mode"],
}

HELP = {
    "bank_accounts": "Bank account hints connect bank statements to exact Tally bank ledgers.",
    "party_ledgers": "Marketplace party ledgers. Use platform keys: amazon, flipkart, meesho, meesho_limited, meesho_technologies, valmo, myntra, unknown.",
    "ledger_mappings": "Main mapping table. tool = bank or marketplace. platform may be blank for bank. pattern is matched against narration/description.",
    "voucher_rules": "Marketplace voucher type rules. Tax Invoice → Purchase, Credit Note → Debit Note.",
}

def _get_company_names():
    names = [c["name"] for c in db.companies()]
    return names or ["Default Company"]

def _df_for_export(company_name):
    data = {}
    data["companies"] = pd.DataFrame(db.companies())
    for table in ["bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"]:
        data[table] = db.df_table(table, company_name)
    data["summary"] = pd.DataFrame([db.database_summary(company_name)])
    return data

def _excel_bytes(company_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, df in _df_for_export(company_name).items():
            if df.empty:
                df = pd.DataFrame(columns=TABLES.get(sheet, []))
            df.to_excel(writer, index=False, sheet_name=sheet[:31])
    return output.getvalue()

def _read_excel_upload(file):
    return pd.read_excel(file, sheet_name=None)

def _clean_df(df, table):
    if df is None or df.empty:
        return pd.DataFrame(columns=TABLES.get(table, []))
    df = df.copy()
    # Remove id and accidental unnamed columns for imports.
    for c in list(df.columns):
        if str(c).startswith("Unnamed"):
            df.drop(columns=[c], inplace=True)
    if "id" in df.columns:
        df.drop(columns=["id"], inplace=True)
    for col in TABLES.get(table, []):
        if col not in df.columns:
            df[col] = ""
    df = df[TABLES.get(table, list(df.columns))]
    df = df.fillna("")
    if "enabled" in df.columns:
        df["enabled"] = df["enabled"].apply(lambda x: bool(x) if str(x).strip() != "" else True)
    return df

def _save_imported_sheet(table, company_name, df, mode):
    df = _clean_df(df, table)
    if table == "companies":
        count = 0
        for _, row in df.iterrows():
            if str(row.get("name", "")).strip():
                db.save_company(row.to_dict())
                count += 1
        return count

    if mode == "Replace selected company table":
        db.replace_table(table, company_name, df.to_dict("records"))
        return len(df)

    # Append / upsert mode
    count = 0
    if table == "ledger_mappings":
        for _, r in df.iterrows():
            if str(r.get("pattern", "")).strip() and str(r.get("ledger", "")).strip():
                db.add_mapping(
                    company_name,
                    r.get("tool", ""),
                    r.get("platform", ""),
                    r.get("pattern", ""),
                    r.get("ledger", ""),
                    r.get("voucher_type", ""),
                )
                count += 1
    elif table == "party_ledgers":
        for _, r in df.iterrows():
            if str(r.get("platform", "")).strip():
                db.upsert_party_ledger(
                    company_name,
                    r.get("platform", ""),
                    r.get("party_ledger", ""),
                    r.get("party_gstin", ""),
                    r.get("state", ""),
                )
                count += 1
    else:
        existing = db.df_table(table, company_name)
        merged = pd.concat([existing.drop(columns=["id"], errors="ignore"), df], ignore_index=True)
        db.replace_table(table, company_name, merged.to_dict("records"))
        count = len(df)
    db.cleanup_database()
    return count

def _show_metrics(company):
    summary = db.database_summary(company)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Companies", summary.get("companies", 0))
    c2.metric("Bank accounts", summary.get("bank_accounts", 0))
    c3.metric("Party ledgers", summary.get("party_ledgers", 0))
    c4.metric("Ledger mappings", summary.get("ledger_mappings", 0))
    c5.metric("Voucher rules", summary.get("voucher_rules", 0))

def render_database_manager_app():
    db.init_db()
    st.title("Shared Database Pro")
    st.caption("One database for Marketplace, Bank Statement and future tools. Export/import Excel, delete safely, cleanup, backup, and company-wise sync.")

    company_names = _get_company_names()
    selected = st.selectbox("Company", company_names, key="db_company_select")

    tabs = st.tabs([
        "Dashboard",
        "Company",
        "Bank Accounts",
        "Party Ledgers",
        "Ledger Mapping",
        "Voucher Rules",
        "Export / Import Excel",
        "Delete / Cleanup",
    ])

    with tabs[0]:
        st.subheader("Database dashboard")
        _show_metrics(selected)
        st.divider()

        ledger_df = db.df_table("ledger_mappings", selected)
        if not ledger_df.empty:
            unmapped = ledger_df[(ledger_df["ledger"].astype(str).str.strip() == "") | (ledger_df["ledger"].astype(str).str.lower() == "suspense")]
            blank_patterns = ledger_df[ledger_df["pattern"].astype(str).str.strip() == ""]
            c1, c2, c3 = st.columns(3)
            c1.metric("Unmapped/Suspense mappings", len(unmapped))
            c2.metric("Blank patterns", len(blank_patterns))
            c3.metric("Disabled mappings", int((ledger_df.get("enabled", True) == False).sum()) if "enabled" in ledger_df else 0)
            if len(unmapped):
                st.warning("These mappings still need ledger names.")
                st.dataframe(unmapped, width="stretch")
        else:
            st.info("No ledger mappings for this company yet.")

        party_df = db.df_table("party_ledgers", selected)
        if not party_df.empty:
            bad_party = party_df[(party_df["party_ledger"].astype(str).str.strip() == "") | (party_df["party_ledger"].astype(str).str.lower() == "suspense")]
            if len(bad_party):
                st.warning("Some party ledgers are blank/Suspense.")
                st.dataframe(bad_party, width="stretch")

        st.subheader("Database file")
        st.code(str(db.DB_PATH), language="text")

    with tabs[1]:
        st.subheader("Company settings")
        comp = db.company(selected)
        row = dict(comp)
        row["name"] = st.text_input("Company name", row.get("name", ""))
        row["tally_company_name"] = st.text_input("Tally company name", row.get("tally_company_name", ""))
        row["gstin"] = st.text_input("GSTIN", row.get("gstin", ""))
        row["state"] = st.text_input("State", row.get("state", ""))
        c1, c2, c3, c4 = st.columns(4)
        row["suspense_ledger"] = c1.text_input("Suspense ledger", row.get("suspense_ledger", "Suspense"))
        row["cgst_ledger"] = c2.text_input("CGST ledger", row.get("cgst_ledger", "INPUT CGST"))
        row["sgst_ledger"] = c3.text_input("SGST ledger", row.get("sgst_ledger", "INPUT SGST"))
        row["igst_ledger"] = c4.text_input("IGST ledger", row.get("igst_ledger", "INPUT IGST"))
        if st.button("Save company", type="primary"):
            db.save_company(row)
            st.success("Company saved.")

        st.divider()
        st.subheader("Create / copy company")
        new_company = st.text_input("New company name")
        col1, col2 = st.columns(2)
        if col1.button("Add blank company") and new_company.strip():
            db.save_company({
                "name": new_company.strip(),
                "tally_company_name": new_company.strip(),
                "gstin": "",
                "state": "",
                "suspense_ledger": "Suspense",
                "cgst_ledger": "INPUT CGST",
                "sgst_ledger": "INPUT SGST",
                "igst_ledger": "INPUT IGST",
            })
            st.success("Blank company added. Refresh page.")
        if col2.button("Copy selected company to new company") and new_company.strip():
            if db.copy_company(selected, new_company.strip()):
                st.success("Company copied with mappings. Refresh page.")
            else:
                st.error("Could not copy company.")

    def edit_table(table, cols, label):
        st.info(HELP.get(table, ""))
        df = db.df_table(table, selected)
        if df.empty:
            df = pd.DataFrame(columns=["id"] + cols)
        show_cols = ["id"] + cols if "id" in df.columns else cols
        edited = st.data_editor(df[show_cols], num_rows="dynamic", width="stretch", key=f"edit_{table}")
        c1, c2 = st.columns([1, 2])
        if c1.button("Save " + label, key=f"save_{table}"):
            db.replace_table(table, selected, edited.drop(columns=["id"], errors="ignore").to_dict("records"))
            st.success(label + " saved and synced.")
        ids_text = c2.text_input(f"Delete {label} row IDs, comma separated", key=f"delete_ids_{table}")
        if st.button("Delete selected row IDs from " + label, key=f"delete_btn_{table}"):
            ids = [x.strip() for x in ids_text.split(",")]
            deleted = db.delete_rows(table, ids)
            st.success(f"Deleted {deleted} row(s). Refresh page.")

    with tabs[2]:
        edit_table("bank_accounts", TABLES["bank_accounts"], "bank accounts")
    with tabs[3]:
        st.caption("Recommended platform keys: amazon, flipkart, meesho, meesho_limited, meesho_technologies, valmo, myntra, unknown")
        edit_table("party_ledgers", TABLES["party_ledgers"], "party ledgers")
    with tabs[4]:
        st.caption("You can export this sheet, fill ledger names in Excel, and import it back.")
        edit_table("ledger_mappings", TABLES["ledger_mappings"], "ledger mappings")
    with tabs[5]:
        edit_table("voucher_rules", TABLES["voucher_rules"], "voucher rules")

    with tabs[6]:
        st.subheader("Export mapping Excel")
        st.write("Use this when you want to fill ledger mapping in Excel and import back.")
        excel_bytes = _excel_bytes(selected)
        st.download_button(
            "Download database mapping Excel",
            excel_bytes,
            file_name=f"{selected}_business_rules_mapping.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.divider()
        st.subheader("Import mapping Excel")
        mode = st.radio("Import mode", ["Append / upsert mappings", "Replace selected company table"], horizontal=True)
        upload = st.file_uploader("Upload edited mapping Excel", type=["xlsx"])
        if upload:
            sheets = _read_excel_upload(upload)
            st.write("Sheets found:", ", ".join(sheets.keys()))
            import_tables = st.multiselect(
                "Choose sheets/tables to import",
                [s for s in ["companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"] if s in sheets],
                default=[s for s in ["bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"] if s in sheets],
            )
            if st.button("Import selected sheets", type="primary"):
                results = {}
                # Backup first
                backup = db.backup_database("before_excel_import")
                for table in import_tables:
                    results[table] = _save_imported_sheet(table, selected, sheets[table], mode)
                st.success(f"Imported successfully. Backup made: {backup.name}")
                st.json(results)

    with tabs[7]:
        st.subheader("Backup / cleanup / delete")
        c1, c2, c3 = st.columns(3)
        if c1.button("Backup database now"):
            backup = db.backup_database("manual")
            st.success(f"Backup created: {backup.name}")
        if c2.button("Normalize + remove duplicates"):
            db.cleanup_database()
            st.success("Database normalized and duplicates removed.")
        st.warning("Delete company removes its bank accounts, party ledgers, ledger mappings, voucher rules, and history.")
        confirm = st.checkbox(f"I understand and want to delete company: {selected}")
        if c3.button("Delete selected company", disabled=(not confirm or selected == "Default Company")):
            if db.delete_company(selected):
                st.success("Company deleted. Refresh page.")
            else:
                st.error("Cannot delete Default Company or delete failed.")

        st.divider()
        st.subheader("Raw database backup download")
        db.init_db()
        raw = Path(db.DB_PATH).read_bytes()
        st.download_button("Download business_rules.db", raw, file_name="business_rules.db", mime="application/octet-stream")
