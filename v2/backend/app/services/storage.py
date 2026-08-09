from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from typing import Protocol
from uuid import UUID

from .fingerprints import sha256_bytes


@dataclass(frozen=True)
class StoredDocument:
    storage_key: str
    sha256: str
    size: int


class DocumentStorage(Protocol):
    def put(self, organization_id: UUID, company_id: UUID, document_id: UUID, filename: str, content: bytes) -> StoredDocument: ...
    def read(self, storage_key: str) -> bytes: ...


class LocalFilesystemStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("storage key escapes configured root")
        return candidate

    def put(self, organization_id: UUID, company_id: UUID, document_id: UUID, filename: str, content: bytes) -> StoredDocument:
        suffix = Path(filename).suffix.lower()[:12]
        key = f"{organization_id}/{company_id}/{document_id}{suffix}"
        target = self._resolve_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredDocument(key, sha256_bytes(content), len(content))

    def read(self, storage_key: str) -> bytes:
        return self._resolve_key(storage_key).read_bytes()

    def put_pending(self, organization_id: UUID, company_id: UUID, job_id: UUID,
                    filename: str, content: bytes) -> StoredDocument:
        suffix=Path(filename).suffix.lower() or ".bin"
        key=f"_queue/{organization_id}/{company_id}/{job_id}{suffix}"
        target=self._resolve_key(key);target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(content);temporary.replace(target)
        digest=sha256_bytes(content)
        return StoredDocument(key,digest,len(content))

    def delete_pending(self,storage_key:str) -> None:
        if not storage_key.startswith("_queue/"): raise ValueError("only queued source files can be deleted")
        target=self._resolve_key(storage_key)
        if target.exists(): target.unlink()
