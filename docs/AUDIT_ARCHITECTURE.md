# Audit Architecture

`AuditEvent` is append-oriented and records actor, organization, optional company, action, entity type/ID, references to previous/new state, optional document, reason, event ID, and UTC time. Phase 1 provides an in-memory append-only development repository; it is not durable production audit storage.

Events will include mapping changes, template approval, duplicate override, reprocessing, XML export, reconciliation override, and role changes. Sensitive payloads are referenced or minimized rather than copied into logs. Production audit persistence later requires immutable append semantics, access controls, retention, correlation/session context, and tamper evidence.
