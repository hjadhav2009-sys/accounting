-- Phase 4 compatibility/scope follow-up. Keeps legacy engines explicit and family names company-scoped.
BEGIN;

ALTER TABLE document_format_families DROP CONSTRAINT document_format_families_organization_id_name_key;
ALTER TABLE document_format_families ADD CONSTRAINT document_format_families_tenant_name_key
    UNIQUE (organization_id, company_id, name);

DROP TRIGGER template_approved_immutable ON template_versions;

UPDATE template_versions
SET engine='LEGACY_PARSER', validation_profile='GENERIC'
WHERE definition ? 'adapter' AND definition->>'adapter'='certified-legacy';

CREATE TRIGGER template_approved_immutable BEFORE UPDATE ON template_versions
FOR EACH ROW EXECUTE FUNCTION prevent_approved_template_mutation();

COMMIT;
