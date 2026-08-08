from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def accounting_duplicate_signature(
    company: str,
    supplier: str,
    document_type: str,
    invoice_number: str,
    invoice_date: str,
    total_amount: str,
) -> tuple[str, ...]:
    normalize = lambda value: " ".join(str(value or "").split()).casefold()
    return tuple(normalize(value) for value in (company, supplier, document_type, invoice_number, invoice_date, total_amount))
