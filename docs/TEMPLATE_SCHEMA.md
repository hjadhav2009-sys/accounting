# Template schema

Schema version 1 is structured JSON with `document_mode`, `page_rules`, `objects`, `derived_fields`, `validation_profile` and bounded metadata. Objects are FIELD, TABLE, ANCHOR or IGNORE_REGION. Page policies include any, first, last, explicit number and repeating table. Coordinates are ordered values from 0 to 1.

Unknown top-level properties, oversized definitions, unsafe transforms, excessive anchor tolerance and executable/resource tokens are rejected. JSON exports contain definitions and sanitized family metadata only—never PDFs, document IDs, credentials or customer values.
