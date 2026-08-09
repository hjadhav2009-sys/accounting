from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class PdfSample:
    document_id: str
    fingerprint: str
    page_count: int
    layout_complexity: int


def cluster_samples(samples: Iterable[PdfSample]) -> dict[str, tuple[PdfSample, ...]]:
    clusters: dict[str, list[PdfSample]] = {}
    for sample in sorted(samples, key=lambda item: (item.fingerprint, item.document_id)):
        clusters.setdefault(sample.fingerprint, []).append(sample)
    return {key: tuple(value) for key, value in clusters.items()}


def representative_samples(samples: Sequence[PdfSample], limit: int = 3) -> tuple[PdfSample, ...]:
    if not 1 <= limit <= 3: raise ValueError("representative limit must be 1-3")
    if not samples: return ()
    ordered = sorted(samples, key=lambda item: item.document_id)
    target = median(item.layout_complexity for item in ordered)
    typical = min(ordered, key=lambda item: (abs(item.layout_complexity-target), item.document_id))
    largest = max(ordered, key=lambda item: (item.page_count, item.layout_complexity, item.document_id))
    outlier = max(ordered, key=lambda item: (abs(item.layout_complexity-target), item.page_count, item.document_id))
    selected: list[PdfSample] = []
    for item in (typical, largest, outlier):
        if item not in selected: selected.append(item)
    return tuple(selected[:limit])


@dataclass(frozen=True)
class RefinementResult:
    proposal: dict
    rounds: int
    passed: bool
    sample_results: tuple[dict, ...]


def bounded_refinement(initial: dict, samples: Sequence[PdfSample],
                       test_all: Callable[[dict, Sequence[PdfSample]], Sequence[dict]],
                       correct: Callable[[dict, Sequence[dict]], dict], max_rounds: int = 3) -> RefinementResult:
    if not 1 <= max_rounds <= 3: raise ValueError("refinement rounds must be 1-3")
    proposal = initial
    results: Sequence[dict] = ()
    for round_number in range(1, max_rounds + 1):
        results = tuple(test_all(proposal, samples))
        if len(results) != len(samples): raise ValueError("every sample must be tested deterministically")
        if all(bool(item.get("passed")) for item in results):
            return RefinementResult(proposal, round_number, True, tuple(results))
        if round_number < max_rounds:
            failures = tuple({"document_id": item.get("document_id"),
                              "codes": tuple(item.get("codes", ())) } for item in results if not item.get("passed"))
            proposal = correct(proposal, failures)
    return RefinementResult(proposal, max_rounds, False, tuple(results))
