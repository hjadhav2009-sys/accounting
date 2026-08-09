from __future__ import annotations

import copy
import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from v2.backend.app.document_intelligence.models import DocumentRecord, DocumentStatus
from v2.backend.app.document_intelligence.repository import DocumentRepository
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
from v2.backend.app.template_studio.engine import TemplateRuleEngine, apply_transform, safe_formula
from v2.backend.app.template_studio.models import CommandHistory, StudioContext, TemplateInvalid, TemplatePermissionDenied
from v2.backend.app.template_studio.repository import TemplateRepository
from v2.backend.app.template_studio.schema import empty_definition, sanitized_export, validate_definition
from v2.backend.app.template_studio.service import TemplateStudioService
from tests.v2.rls_support import set_tenant, tenant_factory


ROOT = Path(__file__).resolve().parents[2]


def mapped_definition(mode: str = "INVOICE"):
    definition = empty_definition(mode)
    definition["objects"] = [
        {"id": "invoice", "type": "FIELD", "field": "invoice_number", "field_kind": "DOCUMENT",
         "box": {"x0": .05, "y0": .05, "x1": .45, "y1": .15}, "page_policy": "PAGE_FIRST", "transforms": ["trim"]},
        {"id": "amount", "type": "FIELD", "field": "invoice_total", "field_kind": "TOTAL",
         "box": {"x0": .55, "y0": .8, "x1": .95, "y1": .95}, "page_policy": "PAGE_LAST",
         "transforms": ["remove_currency_symbol", "remove_grouping_comma", "parse_decimal"]},
        {"id": "items", "type": "TABLE", "table_type": "ITEM",
         "box": {"x0": .05, "y0": .2, "x1": .95, "y1": .7}, "page_policy": "TABLE_REPEAT",
         "columns": [{"boundary": .3, "field": "item_name","source_index":0}, {"boundary": .6, "field": "quantity","source_index":1}, {"boundary": .9, "field": "line_total","source_index":2}],
         "row_classifiers": [{"text": "Total", "row_type": "TOTAL"}], "multiline_strategy": "same-cell", "repeating": True},
    ]
    return definition


def source(page, box):
    return {"page_number": page, "bounding_box": {**box, "page_width": 100, "page_height": 100}}


class TemplateSchemaSecurityTests(unittest.TestCase):
    def test_empty_template_has_versioned_safe_shape(self):
        definition = validate_definition(empty_definition("BANK"))
        self.assertEqual((definition["schema_version"], definition["document_mode"], definition["validation_profile"]), (1, "BANK", "BANK"))

    def test_normalized_coordinates_are_required(self):
        definition = mapped_definition(); definition["objects"][0]["box"]["x1"] = 4
        with self.assertRaises(TemplateInvalid): validate_definition(definition)

    def test_unknown_properties_are_rejected(self):
        definition = empty_definition(); definition["python"] = "print('unsafe')"
        with self.assertRaises(TemplateInvalid): validate_definition(definition)

    def test_malicious_template_tokens_are_rejected(self):
        definition = mapped_definition(); definition["objects"][0]["field"] = "__import__('os')"
        with self.assertRaises(TemplateInvalid): validate_definition(definition)

    def test_transform_whitelist_rejects_code(self):
        definition = mapped_definition(); definition["objects"][0]["transforms"] = ["eval"]
        with self.assertRaises(TemplateInvalid): validate_definition(definition)

    def test_anchor_fuzz_tolerance_is_bounded(self):
        definition = empty_definition(); definition["objects"] = [{"id":"a","type":"ANCHOR","anchor_text":"Invoice No.","relationship":"RIGHT_OF","match_policy":"CASE_INSENSITIVE","tolerance":.5}]
        with self.assertRaises(TemplateInvalid): validate_definition(definition)

    def test_safe_formula_allows_accounting_arithmetic(self):
        self.assertEqual(safe_formula("line_total - tax", {"line_total": "118.00", "tax": "18.00"}), Decimal("100.00"))
        self.assertEqual(safe_formula("cgst + sgst + igst", {"cgst": 9, "sgst": 9, "igst": 0}), Decimal("18.00"))

    def test_safe_formula_prohibits_calls_attributes_and_subscripts(self):
        for formula in ("open('x')", "os.system('x')", "values['tax']"):
            with self.subTest(formula=formula), self.assertRaises(TemplateInvalid): safe_formula(formula, {"values": 1})

    def test_whitelisted_transforms_are_deterministic(self):
        value = " ₹ 21,494.00 "
        for transform in ("trim", "remove_currency_symbol", "remove_grouping_comma", "parse_decimal"):
            value = apply_transform(value, transform)
        self.assertEqual(value, Decimal("21494.00"))

    def test_export_contains_no_document_or_credential_payload(self):
        result = sanitized_export({"name":"Synthetic","description":"","supplier":"","document_type":"Tax Invoice","private_pdf":b"x"},
                                  {"schema_version":1,"validation_profile":"INVOICE","engine":"VISUAL_RULES","definition":mapped_definition()})
        encoded = json.dumps(result)
        self.assertNotIn("private_pdf", encoded); self.assertNotIn("document_id", encoded); self.assertNotIn("credential", encoded)


class TemplateRuleEngineTests(unittest.TestCase):
    def test_region_fields_page_policies_transforms_and_source_trace(self):
        evidence = {"pages":[{"page_number":1},{"page_number":2}],"fields":[
            {"name":"candidate","value":" INV-1 ","confidence":"0.99","source":source(1,{"x0":10,"y0":7,"x1":30,"y1":12})},
            {"name":"total","value":"₹ 1,180.00","confidence":"0.99","source":source(2,{"x0":60,"y0":82,"x1":90,"y1":90})}]}
        result = TemplateRuleEngine().extract(mapped_definition(), evidence)
        self.assertEqual({item["field"]:item["value"] for item in result["fields"]}, {"invoice_number":"INV-1","invoice_total":"1180.00"})
        self.assertTrue(result["source_trace"]); self.assertTrue(all(item["source"] for item in result["fields"]))

    def test_ignore_region_excludes_polluting_source(self):
        definition = mapped_definition(); definition["objects"].append({"id":"ignore","type":"IGNORE_REGION","box":{"x0":.05,"y0":.05,"x1":.45,"y1":.15},"page_policy":"PAGE_FIRST"})
        evidence={"pages":[{"page_number":1}],"fields":[{"value":"INV-X","confidence":1,"source":source(1,{"x0":10,"y0":7,"x1":30,"y1":12})}]}
        result=TemplateRuleEngine().extract(definition,evidence)
        self.assertNotIn("invoice_number", {item["field"] for item in result["fields"]})

    def test_repeating_table_and_total_row_classification(self):
        evidence={"pages":[{"page_number":1,"tables":[{"bounding_box":{"x0":5,"y0":20,"x1":95,"y1":70,"page_width":100,"page_height":100},"rows":[
            {"cells":[{"text":"Bracelet (black)"},{"text":"2"},{"text":"236.00"}]},{"cells":[{"text":"Total"},{"text":"2"},{"text":"236.00"}]}]}]}]}
        result=TemplateRuleEngine().extract(mapped_definition(),evidence)
        self.assertEqual([row["row_type"] for row in result["tables"][0]["rows"]],["ITEM","TOTAL"])
        self.assertEqual(len(result["item_rows"]),1); self.assertEqual(result["item_rows"][0]["values"]["item_name"],"Bracelet (black)")

    def test_multiple_tax_rows_remain_independent(self):
        definition=empty_definition("INVOICE"); definition["objects"]=[{"id":"tax","type":"TABLE","table_type":"TAX_SUMMARY","box":{"x0":0,"y0":0,"x1":1,"y1":1},"page_policy":"TABLE_REPEAT","columns":[{"boundary":.3,"field":"tax_type","source_index":0},{"boundary":.6,"field":"gst_rate","source_index":1},{"boundary":.9,"field":"tax_amount","source_index":2}],"row_classifiers":[],"multiline_strategy":"same-cell","repeating":True}]
        evidence={"pages":[{"page_number":1,"tables":[{"bounding_box":{"x0":0,"y0":0,"x1":100,"y1":100,"page_width":100,"page_height":100},"rows":[{"cells":[{"text":"IGST"},{"text":"3"},{"text":"644.82"}]},{"cells":[{"text":"IGST"},{"text":"18"},{"text":"783.00"}]}]}]}]}
        rows=TemplateRuleEngine().extract(definition,evidence)["tax_buckets"]
        self.assertEqual([row["values"]["gst_rate"] for row in rows],["3","18"])

    def test_anchor_selection_is_explainable(self):
        definition=empty_definition("GENERIC"); definition["objects"]=[{"id":"anchor","type":"ANCHOR","field":"invoice_number","anchor_text":"Invoice No.","relationship":"RIGHT_OF","match_policy":"CASE_INSENSITIVE","tolerance":.05,"sample_value":"INV-7","page_policy":"PAGE_ANY"}]
        evidence={"pages":[{"page_number":1,"width":100,"height":100,"text_blocks":[{"text":"invoice no.","bounding_box":{"x0":1,"y0":1,"x1":10,"y1":3}},{"text":"INV-2026-88","bounding_box":{"x0":12,"y0":1,"x1":25,"y1":3}}]}]}
        field=TemplateRuleEngine().extract(definition,evidence)["fields"][0]
        self.assertEqual(field["value"],"INV-2026-88");self.assertNotEqual(field["value"],"INV-7"); self.assertIn("RIGHT_OF",field["why"])

    def test_anchor_never_reuses_sample_value_across_documents(self):
        definition=empty_definition("GENERIC");definition["objects"]=[{"id":"anchor","type":"ANCHOR","field":"invoice_number","anchor_text":"Invoice No.","relationship":"RIGHT_OF","match_policy":"EXACT","tolerance":.02,"sample_value":"STATIC-BAD","page_policy":"PAGE_ANY"}]
        def evidence(value):return {"pages":[{"page_number":1,"width":100,"height":100,"text_blocks":[{"text":"Invoice No.","bounding_box":{"x0":5,"y0":5,"x1":20,"y1":8}},{"text":value,"bounding_box":{"x0":22,"y0":5,"x1":40,"y1":8}}]}]}
        engine=TemplateRuleEngine();first=engine.extract(definition,evidence("INV-A"))["fields"][0]["value"];second=engine.extract(definition,evidence("INV-B"))["fields"][0]["value"]
        self.assertEqual((first,second),("INV-A","INV-B"));self.assertNotIn("STATIC-BAD",(first,second))

    def test_table_boundaries_control_cell_assignment(self):
        definition=empty_definition("GENERIC");definition["objects"]=[{"id":"table","type":"TABLE","table_type":"ITEM","box":{"x0":0,"y0":0,"x1":1,"y1":1},"page_policy":"PAGE_ANY","columns":[{"boundary":.5,"field":"left"},{"boundary":1,"field":"right"}],"row_classifiers":[],"multiline_strategy":"same-cell"}]
        evidence={"pages":[{"page_number":1,"tables":[{"bounding_box":{"x0":0,"y0":0,"x1":100,"y1":100,"page_width":100,"page_height":100},"rows":[{"cells":[{"text":"A","bounding_box":{"x0":10,"y0":10,"x1":20,"y1":20,"page_width":100,"page_height":100}},{"text":"B","bounding_box":{"x0":70,"y0":10,"x1":80,"y1":20,"page_width":100,"page_height":100}}]}]}]}]}
        values=TemplateRuleEngine().extract(definition,evidence)["item_rows"][0]["values"];self.assertEqual(values,{"left":"A","right":"B"})
        definition["objects"][0]["columns"]=[{"boundary":.8,"field":"left"},{"boundary":1,"field":"right"}]
        values=TemplateRuleEngine().extract(definition,evidence)["item_rows"][0]["values"];self.assertEqual(values,{"left":"A B","right":""})

    def test_derived_field_is_marked_and_has_no_fabricated_source(self):
        definition=empty_definition(); definition["derived_fields"]=[{"field":"taxable","formula":"line_total - tax","inputs":["line_total","tax"],"rounding":2}]
        definition["objects"]=[{"id":"line","type":"FIELD","field":"line_total","field_kind":"ITEM","box":{"x0":0,"y0":0,"x1":.4,"y1":.2},"page_policy":"PAGE_ANY","transforms":["parse_decimal"]},{"id":"tax","type":"FIELD","field":"tax","field_kind":"ITEM","box":{"x0":.5,"y0":0,"x1":1,"y1":.2},"page_policy":"PAGE_ANY","transforms":["parse_decimal"]}]
        evidence={"pages":[{"page_number":1}],"fields":[{"value":"118","confidence":1,"source":source(1,{"x0":1,"y0":1,"x1":30,"y1":10})},{"value":"18","confidence":1,"source":source(1,{"x0":60,"y0":1,"x1":80,"y1":10})}]}
        derived=[item for item in TemplateRuleEngine().extract(definition,evidence)["fields"] if item["derived"]][0]
        self.assertEqual(derived["value"],"100.00"); self.assertIsNone(derived["source"])

    def test_golden_output_comparison_blocks_difference(self):
        actual={"fields":[{"field":"invoice_number","value":"INV-1"}],"item_rows":[],"tax_buckets":[]}
        self.assertEqual(TemplateRuleEngine().compare_golden(actual,{"fields":{"invoice_number":"INV-1"}})["status"],"VERIFIED")
        self.assertEqual(TemplateRuleEngine().compare_golden(actual,{"fields":{"invoice_number":"INV-2"}})["status"],"BLOCKED")


class EditorAndWorkflowModelTests(unittest.TestCase):
    def test_undo_redo_command_model(self):
        history=CommandHistory({"objects":[]}); history.apply({"objects":[{"id":"one"}]},"map field")
        self.assertEqual(history.undo(),{"objects":[]}); self.assertEqual(history.redo(),{"objects":[{"id":"one"}]})

    def test_modes_have_specific_approval_validators(self):
        service=TemplateStudioService(None)  # static validator has no persistence dependency
        bank=service.validate_preview("BANK",{"fields":[]}); invoice=service.validate_preview("INVOICE",{"fields":[]})
        self.assertEqual(bank["status"],"BLOCKED"); self.assertEqual({item["field"] for item in bank["findings"]},{"opening_balance","closing_balance"})
        self.assertIn("invoice_total",{item["field"] for item in invoice["findings"]})

    def test_viewer_cannot_mutate_or_approve(self):
        context=StudioContext(uuid4(),uuid4(),uuid4(),frozenset({"VIEWER"}))
        service=TemplateStudioService(None)
        with self.assertRaises(TemplatePermissionDenied): service._require(context,{"ADMIN"},"approve")

    def test_ai_selection_context_is_local_structured_and_bounded(self):
        context=StudioContext(uuid4(),uuid4(),uuid4(),frozenset({"ADMIN"})); service=TemplateStudioService(None)
        with patch.object(service,"_version",return_value={"version":5}):
            result=service.selection_context(context,uuid4(),{"selected_type":"FIELD","page":1,"nearby_text":"x"*2000,"secret":"no"})
        self.assertFalse(result["external_transmission"]); self.assertFalse(result["ai_enabled"]); self.assertNotIn("secret",result); self.assertEqual(len(result["nearby_text"]),1000)

    def test_routing_distinguishes_approved_variation_and_new_format(self):
        service=TemplateStudioService
        self.assertEqual(service.routing_diagnostic({},[{"family_id":uuid4(),"similarity":.95}])["reason"],"APPROVED_FAMILY_HIGH_CONFIDENCE")
        self.assertEqual(service.routing_diagnostic({},[{"family_id":uuid4(),"similarity":.82}])["reason"],"POSSIBLE_FORMAT_VARIATION")
        self.assertEqual(service.routing_diagnostic({},[])["reason"],"NEW_FORMAT_DETECTED")

    def test_frontend_routes_and_real_editor_controls_exist(self):
        source=(ROOT/"v2/frontend/components/TemplateStudio.tsx").read_text(encoding="utf-8")
        for token in ("onPointerDown","resize-handle","Test all","Create label → value anchor","Ctrl K","Document Assistant","Approve"):
            self.assertIn(token,source)
        self.assertTrue((ROOT/"v2/frontend/app/template-studio/[studioId]/page.tsx").exists())

    def test_phase4_migration_has_immutability_audit_and_evidence(self):
        sql=(ROOT/"v2/backend/migrations/006_phase4_template_studio.sql").read_text(encoding="utf-8").upper()
        for token in ("PREVENT_APPROVED_TEMPLATE_MUTATION","TEMPLATE_ACTIVITY","APPROVAL_EVIDENCE","TEMPLATE_TEST_RESULTS"):
            self.assertIn(token,sql)


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "development PostgreSQL is not available")
class Phase4PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg; cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url); apply_migrations(connection); connection.close()

    def setUp(self):
        self.org,self.company,self.user,self.other_company=uuid4(),uuid4(),uuid4(),uuid4()
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(self.org,f"Phase4 {self.org}"))
            set_tenant(cursor,self.org,self.company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Phase4','Phase4'),(%s,%s,'Other','Other')",(self.company,self.org,self.other_company,self.org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Phase4','ACTIVE')",(self.user,self.org,f"{self.user}@example.invalid"))
        connection.commit();connection.close()
        self.repository=TemplateRepository(tenant_factory(self.url,self.org,self.company,self.user));self.service=TemplateStudioService(self.repository)
        self.context=StudioContext(self.org,self.company,self.user,frozenset({"ADMIN"}))

    def test_family_version_draft_save_optimistic_lock_clone_and_tenant_isolation(self):
        created=self.service.create_family(self.context,f"Synthetic {uuid4()}","Tax Invoice",mode="INVOICE"); version=created["version"]
        definition=copy.deepcopy(version["definition"]);definition["metadata"]["note"]="revision two"
        saved=self.service.save(self.context,version["id"],definition,1)
        self.assertEqual(saved["revision"],2)
        with self.assertRaises(Exception): self.service.save(self.context,version["id"],definition,1)
        clone=self.service.clone_version(self.context,version["id"]);self.assertEqual((clone["version"],clone["status"],clone["parent_version_id"]),(2,"DRAFT",version["id"]))
        self.assertIsNone(self.repository.get_version(self.org,self.other_company,version["id"]))

    def test_approval_evidence_immutability_deprecation_and_history(self):
        created=self.service.create_family(self.context,f"Approval {uuid4()}","Generic",mode="GENERIC"); version=created["version"]
        document_id=uuid4(); DocumentRepository(tenant_factory(self.url,self.org,self.company,self.user)).create(DocumentRecord(
            document_id,self.org,self.company,"synthetic.pdf","synthetic.pdf","application/pdf",1,"a"*64,
            f"synthetic/{document_id}",1,DocumentStatus.UPLOADED,self.user,datetime.now(timezone.utc)))
        run_id=self.repository.create_test_run(self.org,self.company,version["id"],self.user,1);self.repository.start_test_run(self.org,self.company,run_id)
        self.repository.add_test_result(self.org,self.company,run_id,document_id,"VERIFIED",{"fields":[]},{"status":"VERIFIED"},{"status":"VERIFIED"});self.repository.finish_test_run(self.org,self.company,run_id)
        approved=self.service.approve(self.context,version["id"]);self.assertEqual(approved["approval_evidence"]["verified"],1)
        changed=copy.deepcopy(version["definition"]);changed["metadata"]["mutation"]="forbidden"
        with self.assertRaises(Exception): self.repository.save_definition(self.org,self.company,version["id"],self.user,changed,version["revision"])
        deprecated=self.service.deprecate(self.context,version["id"]);self.assertEqual(deprecated["status"],"DEPRECATED")
        events=[item["event_type"] for item in self.repository.activity(self.org,self.company,created["family"]["id"])]
        self.assertIn("TEMPLATE_APPROVED",events);self.assertIn("TEMPLATE_DEPRECATED",events)

    def test_api_surface_contains_safe_actions_and_no_approval_backdoor(self):
        from v2.backend.app.main import app
        paths=app.openapi()["paths"]
        for path in ("/api/v2/templates","/api/v2/templates/versions/{version_id}/actions","/api/v2/templates/versions/{version_id}/selection-context","/api/v2/template-studio/from-document","/api/v2/template-test-runs/{run_id}"):
            self.assertIn(path,paths)
        viewer=StudioContext(self.org,self.company,self.user,frozenset({"VIEWER"}))
        with self.assertRaises(TemplatePermissionDenied): self.service.approve(viewer,uuid4())


if __name__ == "__main__": unittest.main()
