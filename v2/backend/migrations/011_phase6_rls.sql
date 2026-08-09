-- Phase 6 development/staging RLS enforcement. No legacy SQLite changes.
BEGIN;

DROP POLICY IF EXISTS companies_tenant_candidate ON companies;
DROP POLICY IF EXISTS ledger_mappings_tenant_candidate ON ledger_mappings;
DROP POLICY IF EXISTS documents_tenant_candidate ON documents;
DROP POLICY IF EXISTS extraction_jobs_tenant_candidate ON extraction_jobs;
DROP POLICY IF EXISTS audit_logs_tenant_candidate ON audit_logs;

DO $rls$
DECLARE
    item record;
    predicate text;
BEGIN
    FOR item IN
        SELECT c.table_schema,c.table_name,
               bool_or(c.column_name='company_id') AS has_company
        FROM information_schema.columns c
        JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name
        WHERE c.table_schema='public' AND t.table_type='BASE TABLE' AND c.column_name='organization_id'
          AND c.table_name NOT IN ('schema_migrations','users','auth_sessions','auth_security_events')
        GROUP BY c.table_schema,c.table_name
    LOOP
        predicate := 'organization_id = nullif(current_setting(''app.organization_id'', true), '''')::uuid';
        IF item.has_company THEN
            predicate := predicate || ' AND company_id = nullif(current_setting(''app.company_id'', true), '''')::uuid';
        END IF;
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',item.table_schema,item.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',item.table_schema,item.table_name);
        EXECUTE format('DROP POLICY IF EXISTS v2_tenant_isolation ON %I.%I',item.table_schema,item.table_name);
        EXECUTE format('CREATE POLICY v2_tenant_isolation ON %I.%I USING (%s) WITH CHECK (%s)',
                       item.table_schema,item.table_name,predicate,predicate);
    END LOOP;
END $rls$;

COMMIT;
