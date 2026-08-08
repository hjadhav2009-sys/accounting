from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from extractor.pdf_reader import read_pdf
from extractor.parsers import detect_template, parse_by_template
from rules.excel_rules import OUTPUT_COLUMNS, export_excel

APP_DIR = Path(__file__).parent
OUTPUT_DIR = APP_DIR / "output"
TEMPLATE_DIR = APP_DIR / "templates"
DATABASE_DIR = APP_DIR / "database"
OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)


st.title("PDF to Excel Dashboard Core")
st.caption("Local rule-based PDF scanner. Upload PDFs, auto-detect templates, preview, edit, and export Excel.")

with st.sidebar:
    st.header("Control")
    template_mode = st.selectbox(
        "Template mode",
        ["Auto detect", "Flipkart Stock Transfer", "Sujal Tax Invoice"],
    )
    st.divider()
    st.subheader("Output rules")
    ignore_zero = st.checkbox("Ignore 0 taxable rows", value=True)
    force_18 = st.text_input("Force HSN for 18% rate", value="73269099")
    no_color = st.checkbox("No Excel colors", value=True, disabled=True)
    st.caption("Excel export is plain/no color by default.")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []
if "gst_rows" not in st.session_state:
    st.session_state.gst_rows = []
if "item_rows" not in st.session_state:
    st.session_state.item_rows = []
if "raw_texts" not in st.session_state:
    st.session_state.raw_texts = {}
if "pdf_excel_uploader_key" not in st.session_state:
    st.session_state.pdf_excel_uploader_key = 0


def selected_template_name(mode: str, text: str) -> str:
    if mode == "Flipkart Stock Transfer":
        return "flipkart_stock_transfer"
    if mode == "Sujal Tax Invoice":
        return "sujal_tax_invoice"
    return detect_template(text)


tab1, tab2, tab3, tab4 = st.tabs(["1 Upload & Scan", "2 Preview/Edit", "3 Rule Builder", "4 Export"])

with tab1:
    st.subheader("Upload PDFs")
    files = st.file_uploader("Upload one or many PDF files", type=["pdf"], accept_multiple_files=True, key=f"pdf_excel_upload_{st.session_state.pdf_excel_uploader_key}")
    c1, c2 = st.columns([1, 4])
    scan_clicked = c1.button("Scan PDFs", type="primary", use_container_width=True)
    clear_clicked = c2.button("Clear", use_container_width=False)

    if clear_clicked:
        st.session_state.scan_results = []
        st.session_state.gst_rows = []
        st.session_state.item_rows = []
        st.session_state.raw_texts = {}
        st.session_state.pdf_excel_uploader_key += 1
        st.rerun()

    if scan_clicked:
        st.session_state.scan_results = []
        st.session_state.gst_rows = []
        st.session_state.item_rows = []
        st.session_state.raw_texts = {}

        if not files:
            st.warning("Upload PDF files first.")
        else:
            progress = st.progress(0)
            for idx, uploaded in enumerate(files, start=1):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.getbuffer())
                    tmp_path = tmp.name

                try:
                    doc = read_pdf(tmp_path)
                    text = doc.full_text
                    template = selected_template_name(template_mode, text)
                    gst_rows, item_rows = parse_by_template(
                        template,
                        text,
                        uploaded.name,
                        force_18_hsn=force_18.strip(),
                        ignore_zero_taxable=ignore_zero,
                    )
                    status = "OK" if gst_rows else ("NEW FORMAT - map template" if template == "unknown" else "NO ROWS - check raw text")
                    st.session_state.gst_rows.extend(gst_rows)
                    st.session_state.item_rows.extend(item_rows)
                    st.session_state.raw_texts[uploaded.name] = text
                    st.session_state.scan_results.append({
                        "file": uploaded.name,
                        "status": status,
                        "template": template,
                        "gst_rows": len(gst_rows),
                        "item_rows": len(item_rows),
                        "pages": len(doc.pages),
                    })
                except Exception as exc:
                    st.session_state.scan_results.append({
                        "file": uploaded.name,
                        "status": f"ERROR: {exc}",
                        "template": "",
                        "gst_rows": 0,
                        "item_rows": 0,
                        "pages": 0,
                    })
                progress.progress(idx / len(files))
            st.success("Scan complete.")

    st.subheader("Scan result")
    if st.session_state.scan_results:
        st.dataframe(pd.DataFrame(st.session_state.scan_results), use_container_width=True, hide_index=True)
    else:
        st.info("No scan yet.")

    st.subheader("Raw PDF text viewer")
    if st.session_state.raw_texts:
        chosen = st.selectbox("Choose scanned PDF", list(st.session_state.raw_texts.keys()))
        st.text_area("Extracted text", st.session_state.raw_texts[chosen], height=360)

with tab2:
    st.subheader("GST Excel Preview")
    if st.session_state.gst_rows:
        df = pd.DataFrame(st.session_state.gst_rows)
        for col in OUTPUT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[OUTPUT_COLUMNS]
        edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", height=420)
        st.session_state.gst_rows = edited.to_dict("records")

        st.subheader("Item Details")
        if st.session_state.item_rows:
            st.dataframe(pd.DataFrame(st.session_state.item_rows), use_container_width=True, height=300)
    else:
        st.info("Scan PDFs first. If status says NEW FORMAT, use Rule Builder notes and send me sample format to add parser.")

with tab3:
    st.subheader("Rule Builder")
    st.write("This screen saves your notes/settings for new formats. Built-in parser currently supports Flipkart Stock Transfer and Sujal Tax Invoice.")
    template_files = sorted(TEMPLATE_DIR.glob("*.json"))
    selected_file = st.selectbox("Open template JSON", [p.name for p in template_files]) if template_files else None
    if selected_file:
        path = TEMPLATE_DIR / selected_file
        text = path.read_text(encoding="utf-8")
        edited_json = st.text_area("Template JSON", text, height=400)
        if st.button("Save template JSON"):
            try:
                json.loads(edited_json)
                path.write_text(edited_json, encoding="utf-8")
                st.success("Template saved.")
            except Exception as exc:
                st.error(f"Invalid JSON: {exc}")

    st.divider()
    st.subheader("Create new template note")
    new_name = st.text_input("New template name")
    new_note = st.text_area("Rules/notes for this format", height=180, placeholder="Example: Invoice No is after 'Bill No'. Table starts after 'Product Details'. Split one invoice into new row when rate changes...")
    if st.button("Create new template note"):
        if not new_name.strip():
            st.warning("Enter template name.")
        else:
            safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in new_name).strip("_")
            data = {"template_name": new_name, "template_id": safe, "note": new_note}
            out = TEMPLATE_DIR / f"{safe}.json"
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            st.success(f"Created {out.name}")

with tab4:
    st.subheader("Export Excel")
    if st.session_state.gst_rows:
        out_path = OUTPUT_DIR / "final_excel.xlsx"
        export_excel(st.session_state.gst_rows, st.session_state.item_rows, out_path)
        with open(out_path, "rb") as f:
            st.download_button(
                "Download Excel",
                data=f.read(),
                file_name="final_excel.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
        st.caption(f"Saved locally also at: {out_path}")
    else:
        st.info("No GST rows to export yet.")