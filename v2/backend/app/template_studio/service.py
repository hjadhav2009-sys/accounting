from __future__ import annotations

import copy
import re
import time
from typing import Any
from uuid import UUID, uuid4

from .engine import TemplateRuleEngine
from .models import StudioContext, TemplateImmutable, TemplateInvalid, TemplatePermissionDenied
from .repository import TemplateRepository
from .schema import ENGINES, VALIDATION_PROFILES, empty_definition, sanitized_export, validate_definition
from ..document_intelligence.validation import (AccountingValidationEngine,BankBalanceValidator,InvoiceTotalValidator,
    LineAmountValidator,QuantityValidator,RequiredFieldValidator,TaxBucketValidator)


CREATE_ROLES = {"OWNER", "ADMIN", "REVIEWER"}
TEST_ROLES = {"OWNER", "ADMIN", "REVIEWER", "ACCOUNTANT", "OPERATOR"}
APPROVE_ROLES = {"OWNER", "ADMIN"}
VIEW_ROLES = CREATE_ROLES | TEST_ROLES | {"VIEWER"}


class TemplateStudioService:
    def __init__(self, repository: TemplateRepository, engine: TemplateRuleEngine | None = None) -> None:
        self.repository = repository
        self.engine = engine or TemplateRuleEngine()

    @staticmethod
    def _require(context: StudioContext, allowed: set[str], action: str) -> None:
        if not (set(context.roles) & allowed):
            raise TemplatePermissionDenied(f"{action} is not permitted for this role")

    def create_family(self, context: StudioContext, name: str, document_type: str, supplier: str = "",
                      description: str = "", mode: str = "GENERIC") -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "create template family")
        name = " ".join(name.split())
        if not 2 <= len(name) <= 160: raise TemplateInvalid("family name must be 2-160 characters")
        definition = empty_definition(mode)
        family = self.repository.create_family(context.organization_id, context.company_id, context.user_id,
                                               name, document_type[:100], supplier[:200], description[:1000])
        version = self.repository.create_version(context.organization_id, context.company_id, family["id"], context.user_id,
                                                 definition, validation_profile=definition["validation_profile"])
        self.repository.record_activity(context.organization_id, context.company_id, family["id"], version["id"],
                                        context.user_id, "TEMPLATE_CREATED", {"version": version["version"]})
        return {"family": family, "version": version}

    def clone_version(self, context: StudioContext, version_id: UUID, change_summary: str = "") -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "clone template version")
        source = self._version(context, version_id)
        clone = self.repository.create_version(context.organization_id, context.company_id, source["family_id"],
            context.user_id, copy.deepcopy(source["definition"]), parent_version_id=source["id"],
            validation_profile=source["validation_profile"], engine=source["engine"], change_summary=change_summary[:1000])
        self.repository.record_activity(context.organization_id, context.company_id, source["family_id"], clone["id"],
            context.user_id, "VERSION_CREATED", {"parent_version": source["version"], "version": clone["version"]})
        return clone

    def _version(self, context: StudioContext, version_id: UUID) -> dict[str, Any]:
        self._require(context, VIEW_ROLES, "view template")
        version = self.repository.get_version(context.organization_id, context.company_id, version_id)
        if not version: raise KeyError("template version not found")
        if version.get("engine") in {"LEGACY_ADAPTER", "LEGACY_PARSER"} and version.get("definition", {}).get("schema_version") != 1:
            legacy = copy.deepcopy(version["definition"])
            wrapper = empty_definition("GENERIC")
            wrapper["metadata"] = {
                "assistant": "disabled", "source": version["engine"].lower(),
                "legacy_route": str(legacy.get("route", ""))[:200],
                "limitations": "Certified legacy extraction is wrapped, not silently reinterpreted as visual rules.",
            }
            version["definition"] = wrapper
            version["legacy_compatibility"] = {"mode": version["engine"], "wrapped": True, "editable": False}
        return version

    def save(self, context: StudioContext, version_id: UUID, definition: dict[str, Any], expected_revision: int,
             event_type: str = "TEMPLATE_SAVED") -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "edit template")
        version = self._version(context, version_id)
        validate_definition(definition)
        saved = self.repository.save_definition(context.organization_id, context.company_id, version_id,
                                                 context.user_id, definition, expected_revision)
        self.repository.record_activity(context.organization_id, context.company_id, version["family_id"], version_id,
                                        context.user_id, event_type, {"revision": saved["revision"]})
        return saved

    def action(self, context: StudioContext, version_id: UUID, expected_revision: int, action: str,
               payload: dict[str, Any]) -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "change template")
        version = self._version(context, version_id); definition = copy.deepcopy(version["definition"])
        objects = definition.setdefault("objects", [])
        allowed = {"create_field_mapping", "update_field_mapping", "delete_field_mapping", "create_table_rule",
                   "update_column_mapping", "create_anchor", "set_ignore_region"}
        if action not in allowed: raise TemplateInvalid("unsupported template action")
        object_id = str(payload.get("id") or uuid4())[:80]
        if action == "create_field_mapping":
            objects.append({"id": object_id, "type": "FIELD", "field": payload.get("field", "custom_field"),
                "field_kind": payload.get("field_kind", "CUSTOM"), "box": payload["box"],
                "page_policy": payload.get("page_policy", "PAGE_ANY"), "page": payload.get("page"),
                "transforms": payload.get("transforms", ["trim"])})
            event = "FIELD_MAPPED"
        elif action == "create_table_rule":
            objects.append({"id": object_id, "type": "TABLE", "table_type": payload.get("table_type", "GENERIC"),
                "box": payload["box"], "page_policy": payload.get("page_policy", "TABLE_REPEAT"),
                "columns": payload.get("columns", []), "row_classifiers": payload.get("row_classifiers", []),
                "repeating": payload.get("repeating", True), "multiline_strategy": payload.get("multiline_strategy", "same-cell")})
            event = "TABLE_RULE_CHANGED"
        elif action == "create_anchor":
            objects.append({"id": object_id, "type": "ANCHOR", "field": payload.get("field", "custom_field"),
                "anchor_text": payload.get("anchor_text", ""), "relationship": payload.get("relationship", "RIGHT_OF"),
                "match_policy": payload.get("match_policy", "CASE_INSENSITIVE"), "tolerance": payload.get("tolerance", 0.05),
                "page_policy": payload.get("page_policy", "PAGE_ANY"), "sample_value": payload.get("sample_value", "")})
            event = "ANCHOR_CHANGED"
        elif action == "set_ignore_region":
            objects.append({"id": object_id, "type": "IGNORE_REGION", "box": payload["box"],
                "page_policy": payload.get("page_policy", "PAGE_ANY"), "page": payload.get("page")})
            event = "IGNORE_REGION_CHANGED"
        elif action == "delete_field_mapping":
            before = len(objects); objects[:] = [item for item in objects if item.get("id") != payload.get("id")]
            if len(objects) == before: raise KeyError("mapping not found")
            event = "FIELD_REMOVED"
        elif action == "update_field_mapping":
            target = next((item for item in objects if item.get("id") == payload.get("id") and item.get("type") == "FIELD"), None)
            if not target: raise KeyError("field mapping not found")
            for key in ("field", "field_kind", "box", "page_policy", "page", "transforms"):
                if key in payload: target[key] = payload[key]
            event = "FIELD_MAPPED"
        else:
            target = next((item for item in objects if item.get("id") == payload.get("id") and item.get("type") == "TABLE"), None)
            if not target: raise KeyError("table rule not found")
            target["columns"] = payload.get("columns", [])
            event = "TABLE_RULE_CHANGED"
        return self.save(context, version_id, definition, expected_revision, event)

    def add_sample(self, context: StudioContext, version_id: UUID, document_id: UUID,
                   expected: dict[str, Any] | None = None, notes: str = "") -> None:
        self._require(context, CREATE_ROLES, "attach sample")
        version = self._version(context, version_id)
        self.repository.add_sample(context.organization_id, context.company_id, version_id, document_id,
                                   context.user_id, expected, notes[:2000])
        self.repository.record_activity(context.organization_id, context.company_id, version["family_id"], version_id,
                                        context.user_id, "SAMPLE_ADDED", {"document_id": str(document_id)})

    def preview(self, context: StudioContext, version_id: UUID, evidence: dict[str, Any]) -> dict[str, Any]:
        self._require(context, TEST_ROLES, "test template")
        version = self._version(context, version_id)
        extraction = self.engine.extract(version["definition"], evidence)
        validation = self.validate_preview(version["validation_profile"], extraction)
        return {"extraction": extraction, "validation": validation}

    @staticmethod
    def validate_preview(profile: str, extraction: dict[str, Any]) -> dict[str, Any]:
        fields = {item["field"]: item.get("value") for item in extraction.get("fields", [])}
        requirements = {
            "INVOICE": ("invoice_number", "invoice_date", "invoice_total"),
            "MARKETPLACE": ("invoice_number", "document_type", "invoice_total"),
            "BANK": ("opening_balance", "closing_balance"),
            "STOCK_TRANSFER": ("reference_number", "invoice_total"), "GENERIC": (),
        }.get(profile, ())
        items=[dict(row.get("values") or {}) for row in extraction.get("item_rows",[])]
        tax_buckets=[]
        for index,row in enumerate(extraction.get("tax_buckets",[])):
            values=dict(row.get("values") or {})
            tax_buckets.append({"tax_type":values.get("tax_type") or values.get("gst_type"),
                "rate":values.get("gst_rate") or values.get("rate"),"taxable":values.get("taxable"),
                "tax":values.get("tax_amount") or values.get("tax"),"hsn_sac":values.get("hsn_sac") or values.get("hsn"),
                "base_partition_id":values.get("base_partition_id") or f"template-row:{index}"})
        bank_rows=[dict(row.get("values") or {}) for table in extraction.get("tables",[]) if table.get("table_type")=="BANK" for row in table.get("rows",[])]
        payload={**fields,"items":items,"tax_buckets":tax_buckets,
            "displayed_total_quantity":fields.get("displayed_total_quantity"),"invoice_total":fields.get("invoice_total"),
            "taxable_total":fields.get("taxable_total"),"adjustments":fields.get("adjustments"),"round_off":fields.get("round_off"),
            "opening_balance":fields.get("opening_balance"),"closing_balance":fields.get("closing_balance"),
            "bank_transactions":[{"credit":row.get("credit") or row.get("deposit"),"debit":row.get("debit") or row.get("withdrawal"),
                "balance":row.get("balance"),"narration":row.get("narration") or row.get("description")} for row in bank_rows]}
        validators=[RequiredFieldValidator(requirements)]
        if profile in {"INVOICE","MARKETPLACE","STOCK_TRANSFER"}:validators.extend((QuantityValidator(),LineAmountValidator(),TaxBucketValidator(),InvoiceTotalValidator()))
        if profile=="BANK":validators.append(BankBalanceValidator())
        report=AccountingValidationEngine(tuple(validators)).validate(payload)
        findings=[{"code":item.error_code.value if item.error_code else item.validator,"severity":item.severity.value,
            "message":item.message,"field":item.message.rsplit(": ",1)[-1] if item.validator=="RequiredFieldValidator" else None,
            "expected":item.expected,"actual":item.actual,"difference":item.difference} for item in report.findings]
        return {"status":report.status,"profile":profile,"findings":findings,"calculations":report.calculations,
            "checks":{"required_fields":not any(item.validator=="RequiredFieldValidator" for item in report.findings),
                "canonical_accounting_engine":True}}

    def run_all_samples(self, context: StudioContext, version_id: UUID) -> dict[str, Any]:
        run_id = self.queue_test_run(context, version_id)
        self.execute_test_run(context, version_id, run_id)
        return self.repository.test_run(context.organization_id, context.company_id, run_id)

    def queue_test_run(self, context: StudioContext, version_id: UUID) -> UUID:
        self._require(context, TEST_ROLES, "test all samples")
        version = self._version(context, version_id); samples = self.repository.samples(context.organization_id, context.company_id, version_id)
        return self.repository.create_test_run(context.organization_id, context.company_id, version_id, context.user_id, len(samples))

    def execute_test_run(self, context: StudioContext, version_id: UUID, run_id: UUID) -> None:
        self._require(context, TEST_ROLES, "test all samples")
        version = self._version(context, version_id); samples = self.repository.samples(context.organization_id, context.company_id, version_id)
        self.repository.start_test_run(context.organization_id, context.company_id, run_id)
        for sample in samples:
            started = time.perf_counter()
            try:
                extraction = self.engine.extract(version["definition"], sample.get("normalized_result") or {})
                validation = self.validate_preview(version["validation_profile"], extraction)
                comparison = self.engine.compare_golden(extraction, sample.get("expected_result"))
                result = "BLOCKED" if "BLOCKED" in {validation["status"], comparison["status"]} else (
                         "REVIEW" if "REVIEW" in {validation["status"], comparison["status"]} else "VERIFIED")
                self.repository.add_test_result(context.organization_id, context.company_id, run_id, sample["document_id"], result,
                    extraction, validation, comparison, int((time.perf_counter() - started) * 1000))
            except Exception as exc:
                self.repository.add_test_result(context.organization_id, context.company_id, run_id, sample["document_id"], "FAILED",
                    {}, {}, {}, int((time.perf_counter() - started) * 1000), type(exc).__name__[:80])
        self.repository.finish_test_run(context.organization_id, context.company_id, run_id)
        if version["status"] == "DRAFT": self.repository.set_status(context.organization_id, context.company_id, version_id, "TESTING", context.user_id)
        result = self.repository.test_run(context.organization_id, context.company_id, run_id)
        self.repository.record_activity(context.organization_id, context.company_id, version["family_id"], version_id,
                                        context.user_id, "VERSION_TESTED", {key: result[key] for key in ("total", "verified", "review", "blocked", "failed")})

    def approve(self, context: StudioContext, version_id: UUID) -> dict[str, Any]:
        self._require(context, APPROVE_ROLES, "approve template")
        version = self._version(context, version_id)
        if version["status"] not in {"DRAFT", "TESTING"}: raise TemplateImmutable("only a draft/testing version can be approved")
        run = self.repository.latest_test_run(context.organization_id, context.company_id, version_id)
        if not run or run["total"] < 1 or run["verified"] != run["total"] or any(run[key] for key in ("review", "blocked", "failed")):
            raise TemplateInvalid("approval blocked: every attached sample must have a verified golden comparison and validation")
        evidence = {key: run[key] for key in ("total", "verified", "review", "blocked", "failed")}
        evidence.update({"test_run_id": str(run["id"]), "validation_profile": version["validation_profile"], "schema_version": version["schema_version"]})
        approved = self.repository.set_status(context.organization_id, context.company_id, version_id, "APPROVED", context.user_id, evidence)
        self.repository.record_activity(context.organization_id, context.company_id, version["family_id"], version_id,
                                        context.user_id, "TEMPLATE_APPROVED", evidence)
        return approved

    def deprecate(self, context: StudioContext, version_id: UUID) -> dict[str, Any]:
        self._require(context, APPROVE_ROLES, "deprecate template")
        version = self._version(context, version_id)
        if version["status"] != "APPROVED": raise TemplateInvalid("only an approved version can be deprecated")
        result = self.repository.set_status(context.organization_id, context.company_id, version_id, "DEPRECATED", context.user_id)
        self.repository.record_activity(context.organization_id, context.company_id, version["family_id"], version_id,
                                        context.user_id, "TEMPLATE_DEPRECATED")
        return result

    def export(self, context: StudioContext, version_id: UUID) -> dict[str, Any]:
        version = self._version(context, version_id)
        family = self.repository.get_family(context.organization_id, context.company_id, version["family_id"])
        return sanitized_export(family, version)

    def import_definition(self, context: StudioContext, payload: dict[str, Any], family_id: UUID | None = None) -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "import template")
        if payload.get("export_schema") != "business-automation-template-v1": raise TemplateInvalid("unsupported template export")
        version_payload = payload.get("version", {}); definition = validate_definition(version_payload.get("definition"))
        if version_payload.get("engine", "VISUAL_RULES") not in ENGINES: raise TemplateInvalid("unsupported extraction engine")
        if version_payload.get("validation_profile", "GENERIC") not in VALIDATION_PROFILES: raise TemplateInvalid("unsupported validation profile")
        if family_id is None:
            family_payload = payload.get("family", {})
            created = self.create_family(context, family_payload.get("name", "Imported Template"),
                family_payload.get("document_type", "Generic"), family_payload.get("supplier", ""),
                family_payload.get("description", ""), definition["document_mode"])
            return self.save(context, created["version"]["id"], definition, created["version"]["revision"], "TEMPLATE_IMPORTED")
        imported = self.repository.create_version(context.organization_id, context.company_id, family_id, context.user_id,
            definition, validation_profile=version_payload.get("validation_profile", "GENERIC"),
            engine=version_payload.get("engine", "VISUAL_RULES"), change_summary="Sanitized JSON import")
        self.repository.record_activity(context.organization_id, context.company_id, family_id, imported["id"], context.user_id, "TEMPLATE_IMPORTED")
        return imported

    def deterministic_draft(self, context: StudioContext, document: dict[str, Any], evidence: dict[str, Any],
                            candidate_family_id: UUID | None = None) -> dict[str, Any]:
        self._require(context, CREATE_ROLES, "create deterministic draft")
        mode = self._mode(document.get("document_type", "")); definition = empty_definition(mode)
        for index, field in enumerate(evidence.get("fields", [])):
            source = field.get("source") or {}; box = self._normalize_source_box(source.get("bounding_box"))
            if not box: continue
            definition["objects"].append({"id": f"candidate-field-{index+1}", "type": "FIELD",
                "field": field.get("name", f"unmapped_{index+1}"), "field_kind": "CUSTOM", "box": box,
                "page_policy": "PAGE_NUMBER", "page": source.get("page_number", 1), "transforms": ["trim"],
                "candidate": True, "confidence": field.get("confidence")})
        for page in evidence.get("pages", []):
            for index, table in enumerate(page.get("tables", [])):
                box = self._normalize_source_box(table.get("bounding_box"))
                if box: definition["objects"].append({"id": f"candidate-table-{page.get('page_number',1)}-{index+1}",
                    "type": "TABLE", "table_type": "GENERIC", "box": box, "page_policy": "TABLE_REPEAT",
                    "columns": [], "row_classifiers": [], "repeating": True, "multiline_strategy": "same-cell", "candidate": True})
        validate_definition({key: value for key, value in definition.items()})
        if candidate_family_id:
            version = self.repository.create_version(context.organization_id, context.company_id, candidate_family_id, context.user_id,
                definition, validation_profile=mode, change_summary="Possible deterministic format variation")
            flow = "POSSIBLE_FORMAT_VARIATION"
        else:
            created = self.create_family(context, f"Draft · {document.get('supplier') or document.get('original_filename','Unknown format')}",
                document.get("document_type") or "Generic Document", document.get("supplier") or "",
                "Automatically created deterministic draft; uncertain candidates require human mapping.", mode)
            version = self.save(context, created["version"]["id"], definition, created["version"]["revision"], "AUTOMATIC_DRAFT_CREATED")
            flow = "NEW_FORMAT"
        return {"flow": flow, "version": version, "candidate_count": len(definition["objects"]), "uncertain_fields_mapped": False}

    @staticmethod
    def _mode(document_type: str) -> str:
        lowered = document_type.casefold()
        if "bank" in lowered: return "BANK"
        if "marketplace" in lowered or "credit note" in lowered: return "MARKETPLACE"
        if "stock" in lowered or "transfer" in lowered: return "STOCK_TRANSFER"
        if "invoice" in lowered: return "INVOICE"
        return "GENERIC"

    @staticmethod
    def _normalize_source_box(box: dict[str, Any] | None) -> dict[str, float] | None:
        if not box: return None
        try:
            if box.get("page_width") and box.get("page_height"):
                return {"x0": float(box["x0"])/float(box["page_width"]), "y0": float(box["y0"])/float(box["page_height"]),
                        "x1": float(box["x1"])/float(box["page_width"]), "y1": float(box["y1"])/float(box["page_height"])}
            values = {key: float(box[key]) for key in ("x0", "y0", "x1", "y1")}
            return values if all(0 <= value <= 1 for value in values.values()) else None
        except (KeyError, TypeError, ValueError, ZeroDivisionError): return None

    def selection_context(self, context: StudioContext, version_id: UUID, selection: dict[str, Any]) -> dict[str, Any]:
        version = self._version(context, version_id)
        allowed = {"selected_type", "page", "coordinates", "current_mapping", "nearby_text", "validation_state", "sample_document"}
        result = {key: selection.get(key) for key in allowed}
        if isinstance(result.get("nearby_text"), str): result["nearby_text"] = result["nearby_text"][:1000]
        result.update({"template_version": version["version"], "template_version_id": str(version_id),
                       "external_transmission": False, "ai_enabled": False})
        return result

    @staticmethod
    def routing_diagnostic(fingerprint: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
        ranked = sorted(({"family_id": str(item["family_id"]), "name": item.get("name", ""),
                          "similarity": max(0.0, min(1.0, float(item.get("similarity", 0))))} for item in candidates),
                        key=lambda item: item["similarity"], reverse=True)
        selected = ranked[0] if ranked and ranked[0]["similarity"] >= 0.90 else None
        reason = "APPROVED_FAMILY_HIGH_CONFIDENCE" if selected else ("POSSIBLE_FORMAT_VARIATION" if ranked and ranked[0]["similarity"] >= 0.70 else "NEW_FORMAT_DETECTED")
        return {"fingerprint": fingerprint, "candidates": ranked, "selected": selected, "reason": reason,
                "fallback_route": "REVIEW_TEMPLATE_STUDIO" if not selected else "APPROVED_TEMPLATE"}
