-- Preserve distinct taxable-base partitions while avoiding CGST/SGST double counting.
BEGIN;

ALTER TABLE invoice_tax_buckets ADD COLUMN IF NOT EXISTS base_partition_id text NOT NULL DEFAULT '';
ALTER TABLE invoice_tax_buckets DROP CONSTRAINT IF EXISTS invoice_tax_buckets_invoice_id_tax_type_rate_hsn_sac_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_tax_bucket_partition
    ON invoice_tax_buckets(invoice_id,base_partition_id,tax_type,rate,hsn_sac);

COMMIT;
