# AI Privacy Model

All document text is untrusted. Before cloud eligibility, `PrivacyService`
deterministically masks PAN, bank account, Indian phone, email, UPI, and known
tenant entities such as names/addresses. `BALANCED` retains only accounting-useful
structure such as a bank account's last four digits; `STRICT` does not.

The reversible token map exists only in backend memory. Payload preview shows the
sanitized text, counts, and digest but never the map. Whole PDFs are not sent by
default. Image use, when later enabled, must raster-redact known regions locally,
remove hidden OCR text, and use transient storage.

AI Gateway payload retention must be disabled. Per-request cloud calls must set
`cf-aig-collect-log-payload: false` when using an AI Gateway REST route; safe
metadata such as model, status, token/Neuron usage, duration, tenant-scoped job ID,
and prompt version may remain. Raw cloud retention defaults off.

OFF mode is named `OFF_ADMIN_ONLY` deliberately: non-admin requests fail closed.
Tenant IDs are taken from authenticated request context, never model output.

## Phase 5B image runtime

Known sensitive bounding boxes are burned into a fresh RGB raster with opaque
pixels. The result is encoded as a new PNG with no source metadata or hidden text
layer. The cloud payload preview exposes the exact sanitized text, exact redacted
image data URL, digests, model, task, and estimated usage; it never includes
credentials or the reversible token map.
