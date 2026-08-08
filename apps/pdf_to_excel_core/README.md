PDF to Excel Dashboard Core - Windows
====================================

How to run:
1. Unzip this folder.
2. Double-click install_and_run.bat the first time.
3. Later, double-click run_dashboard.bat.
4. Open http://localhost:8501 if browser does not open.

If it crashes:
- Double-click OPEN_LOG.bat and send the text.
- Or run RESET_AND_RUN.bat.

This is a local Streamlit dashboard. Streamlit is only the local UI web app. It runs on your PC.

Current built-in mappings:
- Flipkart Stock Transfer Invoice:
  DATE = Invoice Date
  INVOICE NO. = Invoice Id
  GSTIN = GSTIN from Ship To
  TRADE NAME = name from Ship To
  RATE = IGST Rate
  TAXABLE = Base Price
  HSN CODE = HSN; optional force 18% HSN to 73269099
  QTY = Qty
  Platform Name(Optional) = Flipkart
  GSTIN of e-commerce operator = GSTIN from Shipped From

- Sujal Tax Invoice:
  Uses invoice details + tax summary.

No AI is used.
