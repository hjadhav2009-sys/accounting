# Identity and Authorization

Phase 1 defines `User`/organization/company-access concepts in the PostgreSQL schema and centralizes authorization through `Role`, `Permission`, and `AuthorizationService`. No production login or session cutover exists.

Roles are Owner, Admin, Accountant, Operator, Reviewer, and Viewer. Permissions cover document upload/view/review, template create/approve, bank and marketplace processing, XML/Excel export, mapping edit, and company/user administration. Business services should call the centralized evaluator rather than scatter role-name checks.

Future authenticated requests must establish actor, organization, permitted companies, session, and correlation ID before repositories run. Background jobs carry the same explicit scope. RLS will enforce organization/company claims only after this session contract is reliable and negative cross-tenant tests exist.
