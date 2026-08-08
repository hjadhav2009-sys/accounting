
import os
import sys
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Business Automation Suite", layout="wide")

ROOT = Path(__file__).resolve().parent

st.sidebar.title("Business Automation Suite")
tool = st.sidebar.radio(
    "Choose tool",
    ["Home", "Shared Database", "PDF to Excel Core", "Bank Statement → Tally XML", "Marketplace PDF → Tally XML", "Settings / Notes"]
)

if tool == "Home":
    st.title("Business Automation Suite")
    st.caption("One local page with Shared Database for all tools.")
    st.info("All tools run in this same browser page/port.")
    st.code("http://localhost:8501", language="text")
    st.write("Use the left menu to switch between tools.")
    st.subheader("Current running folder")
    st.code(str(ROOT), language="text")
    st.subheader("Database file path")
    try:
        from shared import database as _db
        st.code(str(_db.DB_PATH), language="text")
    except Exception as e:
        st.error(f"Database path check failed: {e}")
    st.warning("Before Tally XML import, take backup and test small first.")

elif tool == "Shared Database":
    from apps.database_manager.app import render_database_manager_app
    render_database_manager_app()

elif tool == "PDF to Excel Core":
    # Run the old working PDF core inside this single main app.
    # Important: PDF Core imports local folders like extractor/, rules/, templates/.
    # So we temporarily add its folder to sys.path and cwd.
    pdf_core_dir = ROOT / "apps" / "pdf_to_excel_core"
    pdf_core_path = pdf_core_dir / "app_embedded.py"

    old_cwd = os.getcwd()
    old_path = list(sys.path)

    try:
        os.chdir(str(pdf_core_dir))
        sys.path.insert(0, str(pdf_core_dir))
        code = pdf_core_path.read_text(encoding="utf-8")
        globs = {
            "__name__": "__embedded_pdf_core__",
            "__file__": str(pdf_core_path),
        }
        exec(compile(code, str(pdf_core_path), "exec"), globs)
    finally:
        os.chdir(old_cwd)
        sys.path = old_path

elif tool == "Bank Statement → Tally XML":
    from apps.bank_to_tally_xml.app import render_bank_xml_app
    render_bank_xml_app()


elif tool == "Marketplace PDF → Tally XML":
    from apps.marketplace_pdf_to_tally.app import render_marketplace_pdf_to_tally_app
    render_marketplace_pdf_to_tally_app()

else:
    st.title("Settings / Notes")
    st.write("This is local-only. Files stay on your PC.")
    st.write("Single dashboard port: 8501")
    st.write("Bank XML:")
    st.write("- Multiple bank files supported.")
    st.write("- Blank/unmatched ledger goes to Suspense.")
    st.write("- Create missing ledgers is OFF by default.")
    st.write("PDF:")
    st.write("- Uses your working PDF to Excel Core.")
    st.write("- For new PDF templates, send sample PDF + output columns.")
