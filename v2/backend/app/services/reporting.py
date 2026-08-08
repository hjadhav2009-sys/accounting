from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID


class PostgresReportingService:
    """Tenant-scoped aggregate queries; no raw document contents are returned."""

    def __init__(self, connect, organization_id: UUID) -> None:
        self.connect = connect
        self.organization_id = organization_id

    def document_summary(self, company_id: UUID) -> dict[str, int]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*),count(*) FILTER (WHERE status='VERIFIED'),
                              count(*) FILTER (WHERE status='REVIEW'),count(*) FILTER (WHERE status='BLOCKED')
                       FROM documents WHERE organization_id=%s AND company_id=%s""",
                    (self.organization_id, company_id),
                )
                total, verified, review, blocked = cursor.fetchone()
                cursor.execute(
                    "SELECT count(*) FROM document_hashes WHERE organization_id=%s AND company_id=%s",
                    (self.organization_id, company_id),
                )
                unique_hashes = cursor.fetchone()[0]
            return {"documents_processed": total, "verified": verified, "review": review,
                    "blocked": blocked, "duplicate_count": max(0, total - unique_hashes)}
        finally:
            connection.close()

    def invoice_summary(self, company_id: UUID) -> dict[str, Decimal]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT coalesce(sum(b.taxable),0),
                              coalesce(sum(b.tax) FILTER (WHERE b.tax_type='CGST'),0),
                              coalesce(sum(b.tax) FILTER (WHERE b.tax_type='SGST'),0),
                              coalesce(sum(b.tax) FILTER (WHERE b.tax_type='IGST'),0)
                       FROM invoices i LEFT JOIN invoice_tax_buckets b ON b.invoice_id=i.id
                       WHERE i.organization_id=%s AND i.company_id=%s""",
                    (self.organization_id, company_id),
                )
                taxable, cgst, sgst, igst = cursor.fetchone()
                cursor.execute(
                    "SELECT coalesce(sum(total),0) FROM invoices WHERE organization_id=%s AND company_id=%s",
                    (self.organization_id, company_id),
                )
                total = cursor.fetchone()[0]
            return {"taxable": taxable, "cgst": cgst, "sgst": sgst, "igst": igst, "invoice_total": total}
        finally:
            connection.close()

    def bank_summary(self, company_id: UUID) -> dict[str, Decimal]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT coalesce(sum(credit),0),coalesce(sum(debit),0)
                       FROM bank_transactions WHERE organization_id=%s AND company_id=%s""",
                    (self.organization_id, company_id),
                )
                credits, debits = cursor.fetchone()
            return {"credits": credits, "debits": debits}
        finally:
            connection.close()

    def marketplace_summary(self, company_id: UUID) -> dict[str, Any]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT platform,count(*),coalesce(sum(total_amount),0)
                       FROM marketplace_documents WHERE organization_id=%s AND company_id=%s
                       GROUP BY platform ORDER BY platform""",
                    (self.organization_id, company_id),
                )
                rows = cursor.fetchall()
            return {"platforms": [{"platform": platform, "documents": count, "total": total}
                                  for platform, count, total in rows]}
        finally:
            connection.close()
