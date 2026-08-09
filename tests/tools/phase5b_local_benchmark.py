"""Run the approved Phase 5B synthetic benchmark against loopback llama.cpp.

This utility never sends customer data and reads the local API key from the
ignored runtime directory. Results contain timings and validated action names,
but never credentials or raw sensitive inputs.
"""
from __future__ import annotations

import json
import argparse
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from v2.backend.app.hybrid_ai.proposal import LOCAL_PROPOSAL_JSON_SCHEMA, ProposalInvalid, validate_proposal


ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = str(ROOT / "local_models" / "Qwen3-1.7B-Q4_K_M.gguf")
KEY_FILE = ROOT / "local_tools" / "llama.cpp" / "api-keys.txt"

CASES = (
    ("simple_invoice", "Invoice INV-SYN-7 dated 2026-08-09. Propose a field for invoice_number.", "create_field"),
    ("mixed_gst", "Two tax rows: IGST 3% taxable 21494 tax 644.82; IGST 18% taxable 4350 tax 783. Propose a table preserving separate GST rows.", "create_table"),
    ("bank_table", "Bank columns Date, Narration, Debit, Credit, Balance. Propose a table mapping, without changing any balance.", "create_table"),
    ("marketplace_invoice", "Marketplace invoice has Order ID, Fee Type, Taxable Value, IGST, Net Settlement. Propose a table mapping.", "create_table"),
    ("unknown_format", "Unknown normalized layout: Ref: X-19 | Bill date: 2026-08-09 | Grand total: 1180. Propose a stable anchor for Ref.", "create_anchor"),
    ("correction_instruction", "Correction: the selected column is Quantity, not Amount. Propose only an update to that field mapping.", "update_field"),
)


def run_case(name: str, text: str, expected_action: str, api_key: str) -> dict[str, object]:
    body = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 400,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": (
                "Return only the required JSON proposal. Use exactly one allowlisted Template Action. "
                "Never approve, post, execute code, use SQL, access files, or alter accounting values. "
                "The action payload must describe a draft mapping and deterministic validation remains required."
            )},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object", "schema": LOCAL_PROPOSAL_JSON_SCHEMA},
    }
    request = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
    })
    started = time.monotonic()
    with urlopen(request, timeout=120) as response:
        raw = json.load(response)
    elapsed = time.monotonic() - started
    content = raw["choices"][0]["message"]["content"]
    payload = json.loads(content) if isinstance(content, str) else content
    try:
        proposal = validate_proposal(payload, provider="LOCAL", model=MODEL, prompt_version="phase5b")
    except ProposalInvalid as exc:
        return {
            "case": name, "elapsed_seconds": round(elapsed, 3),
            "schema_compliant": False, "tool_proposal_correct": False,
            "classification": "FAILED", "error": type(exc).__name__,
            "reason": str(exc), "returned_top_level_keys": sorted(payload) if isinstance(payload, dict) else [],
        }
    actions = [item.action for item in proposal.actions]
    timings = raw.get("timings", {})
    correct = expected_action in actions and len(actions) == 1
    return {
        "case": name,
        "elapsed_seconds": round(elapsed, 3),
        "prompt_tokens": raw.get("usage", {}).get("prompt_tokens", 0),
        "completion_tokens": raw.get("usage", {}).get("completion_tokens", 0),
        "prompt_tokens_per_second": round(float(timings.get("prompt_per_second", 0)), 3),
        "generation_tokens_per_second": round(float(timings.get("predicted_per_second", 0)), 3),
        "schema_compliant": True,
        "actions": actions,
        "expected_action": expected_action,
        "tool_proposal_correct": correct,
        "classification": "SUFFICIENT" if correct else "NEEDS_CLOUD",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=[item[0] for item in CASES])
    args = parser.parse_args()
    api_key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not api_key:
        raise SystemExit("local API key is missing")
    results = []
    selected = [item for item in CASES if not args.case or item[0] == args.case]
    for case in selected:
        try:
            results.append(run_case(*case, api_key))
        except Exception as exc:
            detail = ""
            if isinstance(exc, HTTPError):
                detail = exc.read().decode("utf-8", "replace")[:500]
            results.append({"case": case[0], "schema_compliant": False,
                            "tool_proposal_correct": False, "classification": "FAILED",
                            "error": type(exc).__name__, "reason": str(exc)[:240],
                            "provider_detail": detail})
    print(json.dumps({"model": "Qwen3-1.7B-Q4_K_M", "synthetic_only": True,
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
