-- Structured Phase 3B processing telemetry; no extracted document text.
BEGIN;
ALTER TABLE document_processing_metrics ADD COLUMN ocr_pages integer NOT NULL DEFAULT 0 CHECK (ocr_pages >= 0);
ALTER TABLE document_processing_metrics ADD COLUMN format_route text NOT NULL DEFAULT '';
ALTER TABLE document_processing_metrics ADD COLUMN validation_status text NOT NULL DEFAULT '';
ALTER TABLE document_processing_metrics ADD COLUMN batch_id uuid REFERENCES document_batches(id);
ALTER TABLE document_processing_metrics ADD COLUMN job_id uuid;
CREATE INDEX ix_metrics_batch_stage ON document_processing_metrics(batch_id,stage,created_at);
COMMIT;
