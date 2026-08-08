# Legacy Identity Mapping

Every imported row is keyed by `legacy_source=sqlite`, `legacy_table`, the
original text form of `legacy_id`, and `organization_id`. Its V2 UUID is UUIDv5
over those same stable values. Companies use their legacy name because the
SQLite company key is textual; child tables use the SQLite integer ID.

`legacy_identity_map` stores the V2 UUID and a SHA-256 fingerprint of the source
row. Re-import updates the same entity and identity record. Normalized fields are
recorded separately with source value, normalized value, and the exact legacy
normalization rule. No new matching semantics are introduced.
