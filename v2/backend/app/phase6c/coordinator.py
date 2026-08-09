from __future__ import annotations

from typing import Any

from .comparison import compare_documents
from .modes import ExecutionMode
from .reference_engine import LegacyReferenceEngine
from .v2_native import V2NativeDocumentEngine


class IndependentParityCoordinator:
    def __init__(self, native: V2NativeDocumentEngine, reference: LegacyReferenceEngine | None = None) -> None:
        self.native = native
        self.reference = reference or LegacyReferenceEngine()

    def execute(self, mode: ExecutionMode, content: bytes, filename: str) -> dict[str, Any]:
        if mode is ExecutionMode.LEGACY_REFERENCE:
            return {"mode": mode, "reference": self.reference.process(content, filename)}
        if mode is ExecutionMode.V2_NATIVE:
            return {"mode": mode, "v2": self.native.process(content, filename)}
        reference = self.reference.process(content, filename)
        # The native invocation receives only the original bytes/name. Reference output is never a hint.
        native = self.native.process(content, filename)
        return {"mode": mode, "reference": reference, "v2": native,
                "comparison": compare_documents(reference, native)}
