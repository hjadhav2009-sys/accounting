# Business Automation Suite — Current Working Baseline

This folder is the preserved working baseline before the V2 / PostgreSQL / Local-AI / Cloudflare upgrade.

## Current working tools
- Shared Database / Database Pro
- PDF to Excel Core
- Bank Statement -> Tally XML
- Marketplace PDF -> Tally XML
- Clean localhost startup on port 8501

## Important current data
- `data/business_rules.db` is the current shared rule database. Do not delete or replace it casually.
- Current mappings, party ledgers, voucher rules and company configuration are kept in this baseline.

## Verified baseline checks
- Python source compilation: PASS
- Shared database opens: PASS
- Database summary in this baseline: 3 companies, 4 bank accounts, 26 party ledgers, 144 ledger mappings, 42 voucher rules
- Sujal Tax Invoice sample `2600000122`: template auto-detected as `sujal_tax_invoice`; 3 item rows parsed; QTY total 420; GST summary QTY 420
- Previous marketplace QA bundled in this project: 188 parsed rows / 188 OK / 46 XML vouchers / 0 party Suspense in the verified sample set

## Start the software
On Windows, double-click:

`START_CLEAN_DASHBOARD.bat`

It closes an old process using localhost:8501 before launching this folder.

Then open:

`http://localhost:8501`

## Baseline rule
Create V2 work on a new Git branch. Do not rewrite or delete the legacy parsers until replacement tests prove equivalent results.

## Public GitHub warning
This baseline contains your active local `data/business_rules.db` so it works after extraction. The included `.gitignore` blocks DB/JSON/PDF/Excel/CSV/XML/secrets by default. **Do not force-add those files to a public repository.**
