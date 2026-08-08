# Optional pdfplumber table helper. The regex parsers are used first.

def read_tables(path: str):
    try:
        import pdfplumber
    except Exception:
        return []
    tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                tables.append(table)
    return tables
