-- Complete the durable-queue boundary with company RLS on both scheduling metadata
-- and protected payload. Workers discover organizations, enumerate their authorized
-- company contexts, and query this index only after setting each tenant context.
BEGIN;

DROP POLICY IF EXISTS v2_tenant_isolation ON durable_job_schedule;
ALTER TABLE durable_job_schedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE durable_job_schedule FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON durable_job_schedule
    USING (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
       AND company_id=nullif(current_setting('app.company_id',true),'')::uuid)
    WITH CHECK (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
       AND company_id=nullif(current_setting('app.company_id',true),'')::uuid);

DO $verify$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE oid='durable_document_jobs'::regclass AND relrowsecurity AND relforcerowsecurity
    ) THEN
        RAISE EXCEPTION 'durable_document_jobs must retain forced RLS';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE oid='durable_job_schedule'::regclass AND relrowsecurity AND relforcerowsecurity
    ) THEN
        RAISE EXCEPTION 'durable_job_schedule must retain forced RLS';
    END IF;
END $verify$;

COMMIT;
