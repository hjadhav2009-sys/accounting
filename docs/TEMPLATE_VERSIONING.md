# Template versioning

Template versions belong to a company-scoped format family, have immutable positive version numbers, schema versions and JSON definitions, and support `DRAFT`, `TESTING`, `APPROVED`, `DEPRECATED`, `REJECTED`, and legacy `RETIRED` states. Draft saves increment an optimistic `revision`; stale saves return HTTP 409.

Editing or cloning any historical version creates the next numbered DRAFT with a `parent_version_id`. APPROVED definition/schema/profile/engine content is protected by both the application service and a PostgreSQL trigger. Deprecation changes routing status without deleting historical definitions or extraction provenance. Version diff reports added, changed and removed objects plus validation-profile changes.
