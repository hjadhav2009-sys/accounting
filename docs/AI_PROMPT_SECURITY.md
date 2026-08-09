# AI Prompt Security

PDF text, OCR text, filenames, annotations, and retrieved corrections are data,
never instructions. System prompts state this boundary and only permit domain
tasks. Synthetic fixtures include attempts to override the system, approve a
template, post a voucher, execute code, and fetch an external URL.

Controls:

- version and hash prompts;
- minimize and mask input;
- restrict tasks/models/actions at FastAPI and Worker boundaries;
- reject unknown JSON fields and invalid structured output;
- bound messages, bodies, outputs, retries, and action counts;
- escape display text and never render provider HTML;
- never expose chain-of-thought; provide short rationale/source/validation impact;
- deterministic validation and human confirmation remain mandatory;
- cache only by model, prompt version, sanitized input hash, template revision,
  task, organization, and company.

Provider errors, quota uncertainty, and schema failure result in explicit
review/failure states. They never silently fall back to a paid or less-private
provider.
