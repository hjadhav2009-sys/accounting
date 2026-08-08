from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

OUTPUT_COLUMNS = [
    "DATE",
    "INVOICE NO(Invoice Id).",
    "GSTIN( from ship to )",
    "TRADE NAME( from Ship To Shiv Jagdamba,)",
    "RATE",
    "TAXABLE",
    "HSN CODE",
    "QTY",
    "Platform Name(Optional)",
    "GSTIN of e-commerce operator ( from  shipped from )",
]


def export_excel(rows: List[Dict], item_rows: List[Dict], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLUMNS]

    item_df = pd.DataFrame(item_rows)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="GST Data")
        item_df.to_excel(writer, index=False, sheet_name="Item Details")

        wb = writer.book
        for ws in wb.worksheets:
            for col_cells in ws.columns:
                max_len = 12
                col_letter = col_cells[0].column_letter
                for cell in col_cells:
                    val = "" if cell.value is None else str(cell.value)
                    max_len = max(max_len, min(len(val) + 2, 45))
                ws.column_dimensions[col_letter].width = max_len
            ws.freeze_panes = "A2"
    return output_path
