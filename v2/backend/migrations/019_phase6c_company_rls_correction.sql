-- Correct Phase 6 policy discovery so every table carrying company_id enforces it in RLS.
BEGIN;

DO $rls$
DECLARE
    item record;
    predicate text;
BEGIN
    FOR item IN
        SELECT c.table_schema,c.table_name,
               bool_or(c.column_name='organization_id') AS has_organization,
               bool_or(c.column_name='company_id') AS has_company,
               bool_or(c.column_name='company_id' AND c.is_nullable='YES') AS nullable_company
        FROM information_schema.columns c
        JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name
        WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
          AND c.column_name IN ('organization_id','company_id')
          AND c.table_name NOT IN ('schema_migrations','users','auth_sessions','auth_security_events')
        GROUP BY c.table_schema,c.table_name
        HAVING bool_or(c.column_name='organization_id')
    LOOP
        predicate := 'organization_id = nullif(current_setting(''app.organization_id'', true), '''')::uuid';
        IF item.has_company THEN
            IF item.nullable_company THEN
                predicate := predicate || ' AND (company_id IS NULL OR company_id = nullif(current_setting(''app.company_id'', true), '''')::uuid)';
            ELSE
                predicate := predicate || ' AND company_id = nullif(current_setting(''app.company_id'', true), '''')::uuid';
            END IF;
        END IF;
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',item.table_schema,item.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',item.table_schema,item.table_name);
        EXECUTE format('DROP POLICY IF EXISTS v2_tenant_isolation ON %I.%I',item.table_schema,item.table_name);
        EXECUTE format('CREATE POLICY v2_tenant_isolation ON %I.%I USING (%s) WITH CHECK (%s)',
                       item.table_schema,item.table_name,predicate,predicate);
    END LOOP;
END $rls$;

COMMIT;
