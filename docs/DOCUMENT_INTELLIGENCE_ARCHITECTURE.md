# Document intelligence architecture

The V2 path is `FastAPI -> intake service -> filesystem storage + PostgreSQL metadata -> extraction -> routing -> deterministic validation -> review/reporting`. Original bytes never enter PostgreSQL. Native text is preferred, local OCR is conditional, and no external inference call exists. Certified legacy parser logic is reached through an adapter rather than copied. SQLite and Streamlit remain authoritative production systems.
