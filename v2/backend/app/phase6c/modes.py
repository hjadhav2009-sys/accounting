from enum import StrEnum


class ExecutionMode(StrEnum):
    LEGACY_REFERENCE = "LEGACY_REFERENCE"
    V2_NATIVE = "V2_NATIVE"
    COMPARE = "COMPARE"
