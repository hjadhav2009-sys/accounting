# Template Studio architecture

The browser editor calls tenant-scoped FastAPI endpoints. All writes pass through `TemplateStudioService`, role checks, schema validation, optimistic revision checks and `TemplateRepository`; the UI and future AI use the same action boundary. PostgreSQL stores families, immutable versions, samples, test evidence, comments and activity. Protected PDFs remain in document storage and are rendered page-at-a-time through the authenticated Phase 3 page endpoint.

The editor is full viewport: toolbar and tools; resizable page/sample panel; lazy protected PDF canvas and overlays; resizable inspector; extraction/test/explanation/activity/disabled-assistant dock. Coordinates are normalized and never fabricated. Approved definitions cannot be changed at either the service or database-trigger layer.
