from __future__ import annotations

import html
from typing import Any

from .models import ALLOWED_TEMPLATE_ACTIONS, AiAction, AiTemplateProposal, ConfidenceBand


class ProposalInvalid(ValueError): pass


def _clean(value: Any, limit: int) -> str:
    return html.escape(str(value or "").strip(), quote=True)[:limit]


def validate_proposal(payload: dict[str, Any], *, provider: str, model: str,
                      prompt_version: str) -> AiTemplateProposal:
    if set(payload) - {"summary", "actions"}: raise ProposalInvalid("proposal contains unknown properties")
    actions = payload.get("actions")
    if not isinstance(actions, list) or len(actions) > 30: raise ProposalInvalid("actions must be a bounded list")
    validated: list[AiAction] = []
    for raw in actions:
        if not isinstance(raw, dict): raise ProposalInvalid("each action must be an object")
        if set(raw) - {"action", "payload", "rationale", "source_references", "confidence", "validation_impact", "risk"}:
            raise ProposalInvalid("action contains unknown properties")
        action = str(raw.get("action", ""))
        if action not in ALLOWED_TEMPLATE_ACTIONS: raise ProposalInvalid(f"action is not allowed: {action}")
        action_payload = raw.get("payload")
        if not isinstance(action_payload, dict): raise ProposalInvalid("action payload must be an object")
        encoded_size = len(str(action_payload).encode())
        if encoded_size > 20_000: raise ProposalInvalid("action payload is too large")
        try: confidence = ConfidenceBand(str(raw.get("confidence", "LOW")).upper())
        except ValueError as exc: raise ProposalInvalid("confidence must be HIGH, MEDIUM or LOW") from exc
        sources = raw.get("source_references", [])
        if not isinstance(sources, list) or len(sources) > 20: raise ProposalInvalid("source references must be bounded")
        validated.append(AiAction(action, action_payload, _clean(raw.get("rationale"), 1000),
                                  tuple(_clean(item, 200) for item in sources), confidence,
                                  _clean(raw.get("validation_impact"), 500),
                                  str(raw.get("risk", "HIGH")).upper()))
    return AiTemplateProposal(_clean(payload.get("summary"), 2000), tuple(validated), provider[:80],
                              model[:160], prompt_version[:80])


PROPOSAL_JSON_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "actions"],
    "properties": {
        "summary": {"type": "string", "maxLength": 2000},
        "actions": {"type": "array", "maxItems": 30, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["action", "payload", "rationale", "confidence", "validation_impact"],
            "properties": {
                "action": {"type": "string", "enum": sorted(ALLOWED_TEMPLATE_ACTIONS)},
                "payload": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"}, "label": {"type": "string"},
                        "role": {"type": "string"}, "source": {"type": "string"},
                        "value_type": {"type": "string"}, "selector": {"type": "string"},
                        "anchor": {"type": "string"}, "table": {"type": "string"},
                        "columns": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                        "change": {"type": "string"}, "expected": {"type": "string"},
                    },
                }, "rationale": {"type": "string"},
                "source_references": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "validation_impact": {"type": "string"}, "risk": {"type": "string"},
            },
        }},
    },
}

# llama.cpp b10329 cannot compile the full validation schema (notably the
# bounds/additionalProperties combination) into a sampler grammar. This smaller
# generation schema constrains the shape and enums; validate_proposal remains
# the authoritative, fail-closed validator for every returned property/value.
LOCAL_PROPOSAL_JSON_SCHEMA = {
    "type": "object", "required": ["summary", "actions"],
    "properties": {
        "summary": {"type": "string"},
        "actions": {"type": "array", "items": {
            "type": "object",
            "required": ["action", "payload", "rationale", "confidence", "validation_impact"],
            "properties": {
                "action": {"type": "string", "enum": sorted(ALLOWED_TEMPLATE_ACTIONS)},
                "payload": {"type": "object", "properties": {
                    "field": {"type": "string"}, "label": {"type": "string"},
                    "role": {"type": "string"}, "source": {"type": "string"},
                    "value_type": {"type": "string"}, "selector": {"type": "string"},
                    "anchor": {"type": "string"}, "table": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "change": {"type": "string"}, "expected": {"type": "string"},
                }},
                "rationale": {"type": "string"},
                "source_references": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "validation_impact": {"type": "string"}, "risk": {"type": "string"},
            },
        }},
    },
}
