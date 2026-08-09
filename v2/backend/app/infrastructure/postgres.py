from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from typing import Any
from uuid import UUID
from functools import lru_cache
import os
import atexit

from ..domain.mapping import mapping_matches,normalize_platform as norm_platform,normalize_text as norm_text

from ..domain.enums import JobStatus
from ..domain.models import AuditEvent, DocumentIdentity, Job


ConnectionFactory = Callable[[], Any]


class _PooledConnection:
    def __init__(self,pool,connection):self._pool=pool;self._connection=connection;self._returned=False
    def __getattr__(self,name):return getattr(self._connection,name)
    @property
    def closed(self):return self._returned or self._connection.closed
    def close(self):
        if self._returned:return
        try:
            if not self._connection.closed:self._connection.rollback()
        finally:self._pool.putconn(self._connection);self._returned=True


@lru_cache(maxsize=8)
def _connection_pool(database_url:str):
    from psycopg_pool import ConnectionPool
    minimum=max(0,int(os.getenv("POSTGRES_POOL_MIN_SIZE","1")));maximum=max(minimum or 1,int(os.getenv("POSTGRES_POOL_MAX_SIZE","10")))
    return ConnectionPool(database_url,min_size=minimum,max_size=maximum,timeout=max(1,int(os.getenv("POSTGRES_POOL_TIMEOUT_SECONDS","10"))),open=True)


def close_connection_pools()->None:
    # lru_cache intentionally exposes no value iterator; configured URLs used by
    # this process are tracked separately by the pool factory wrapper below.
    for pool in tuple(_OPEN_POOLS):pool.close()
    _OPEN_POOLS.clear();_connection_pool.cache_clear()


_OPEN_POOLS:set[Any]=set()
atexit.register(close_connection_pools)


def psycopg_connection_factory(database_url: str) -> ConnectionFactory:
    if not database_url:
        raise ValueError("DATABASE_URL is required for PostgreSQL modes")

    def connect():
        pool=_connection_pool(database_url);_OPEN_POOLS.add(pool)
        return _PooledConnection(pool,pool.getconn())

    return connect


def psycopg_tenant_connection_factory(database_url: str, organization_id: UUID, company_id: UUID,
                                      user_id: UUID | None = None) -> ConnectionFactory:
    """Create an RLS-enforced application connection for one selected company.

    The configured application login must be NOSUPERUSER and NOBYPASSRLS. Database
    role provisioning is intentionally external to application migrations. The
    transaction-local tenant settings are reset automatically on commit/rollback.
    """
    if not database_url: raise ValueError("DATABASE_URL is required for PostgreSQL modes")

    def connect():
        pool=_connection_pool(database_url);_OPEN_POOLS.add(pool);connection=_PooledConnection(pool,pool.getconn())
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
                cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id),))
                cursor.execute("SELECT set_config('app.user_id',%s,true)",(str(user_id or ""),))
            return connection
        except Exception:
            connection.close();raise
    return connect


class PostgresRepositories:
    """Tenant-scoped Phase 2 implementation of the Phase 1 repository contracts."""

    def __init__(self, connect: ConnectionFactory, organization_id: UUID) -> None:
        self._connect = connect
        self.organization_id = organization_id

    @contextmanager
    def _cursor(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _record(cursor, row) -> dict[str, Any] | None:
        if row is None:
            return None
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return dict(zip(names, row))

    def list_companies(self) -> Sequence[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE organization_id=%s ORDER BY name", (self.organization_id,))
            return [self._record(cursor, row) for row in cursor.fetchall()]

    def get_company(self, name: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM companies WHERE organization_id=%s AND name=%s",
                (self.organization_id, norm_text(name)),
            )
            return self._record(cursor, cursor.fetchone())

    def _company_id(self, cursor, company_name: str) -> UUID | None:
        cursor.execute(
            "SELECT id FROM companies WHERE organization_id=%s AND name=%s",
            (self.organization_id, norm_text(company_name)),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _company_ids_with_default(self, cursor, company_name: str) -> list[UUID]:
        """V2 forced-RLS lookups are company-local; defaults must be copied explicitly."""
        company_id=self._company_id(cursor,company_name)
        return [company_id] if company_id is not None else []

    def list_bank_accounts(self, company_name: str) -> Sequence[dict[str, Any]]:
        with self._cursor() as cursor:
            company_id = self._company_id(cursor, company_name)
            if company_id is None:
                return []
            cursor.execute(
                "SELECT * FROM bank_accounts WHERE organization_id=%s AND company_id=%s ORDER BY id",
                (self.organization_id, company_id),
            )
            return [self._record(cursor, row) for row in cursor.fetchall()]

    def party_ledger(self, company_name: str, platform: str) -> str:
        company = self.get_company(company_name)
        fallback = (company or {}).get("suspense_ledger") or "Suspense"
        with self._cursor() as cursor:
            company_ids = self._company_ids_with_default(cursor, company_name)
            for wanted_platform in (norm_platform(platform), "unknown"):
                for company_id in company_ids:
                    cursor.execute(
                        "SELECT party_ledger FROM party_ledgers WHERE organization_id=%s AND company_id=%s AND platform=%s",
                        (self.organization_id, company_id, wanted_platform),
                    )
                    row = cursor.fetchone()
                    if row and norm_text(row[0]):
                        return norm_text(row[0])
        return fallback

    def map_ledger(self, company_name: str, tool: str, platform: str, description: str, voucher_type: str = "") -> tuple[str, str]:
        company = self.get_company(company_name)
        fallback = (company or {}).get("suspense_ledger") or "Suspense"
        with self._cursor() as cursor:
            company_ids = self._company_ids_with_default(cursor, company_name)
            if not company_ids:
                return fallback, "UNMATCHED_TO_SUSPENSE"
            wanted_platform = norm_platform(platform)
            wanted_voucher = norm_text(voucher_type).lower()
            for company_id in company_ids:
                cursor.execute(
                    """SELECT pattern, ledger, platform, voucher_type,match_type FROM ledger_mappings
                       WHERE organization_id=%s AND company_id=%s AND tool=%s AND enabled=true
                       ORDER BY length(pattern) DESC""",
                    (self.organization_id, company_id, norm_platform(tool)),
                )
                for pattern, ledger, row_platform, row_voucher,match_type in cursor.fetchall():
                    normalized_platform = norm_platform(row_platform)
                    if normalized_platform and wanted_platform and normalized_platform not in {wanted_platform, "all"}:
                        continue
                    normalized_voucher = norm_text(row_voucher).lower()
                    if normalized_voucher and wanted_voucher and normalized_voucher != wanted_voucher:
                        continue
                    if mapping_matches(description,pattern,match_type):
                        return norm_text(ledger) or fallback, pattern
        return fallback, "UNMATCHED_TO_SUSPENSE"

    def get_rule(self, company_name: str, platform: str, document_type: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            for company_id in self._company_ids_with_default(cursor, company_name):
                cursor.execute(
                    """SELECT tally_voucher_type, sign_mode FROM voucher_rules
                       WHERE organization_id=%s AND company_id=%s AND platform=%s AND document_type=%s""",
                    (self.organization_id, company_id, norm_platform(platform), norm_text(document_type)),
                )
                record = self._record(cursor, cursor.fetchone())
                if record:
                    return record
        if str(document_type).lower() == "credit note":
            return {"tally_voucher_type": "Debit Note", "sign_mode": "reverse"}
        return {"tally_voucher_type": "Purchase", "sign_mode": "charge"}

    def save_document(self, document: DocumentIdentity, storage_key: str, status: str = "UPLOADED") -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT document_id FROM document_hashes WHERE organization_id=%s AND company_id=%s AND sha256=%s",
                (document.organization_id, document.company_id, document.sha256),
            )
            if cursor.fetchone():
                return False
            cursor.execute(
                """INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by,created_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (document.document_id, document.organization_id, document.company_id, document.filename,
                 document.mime_type, document.size, storage_key, status, document.created_by, document.created_at),
            )
            cursor.execute(
                "INSERT INTO document_hashes(document_id,organization_id,company_id,sha256) VALUES(%s,%s,%s,%s)",
                (document.document_id, document.organization_id, document.company_id, document.sha256),
            )
        return True

    def get(self, document_id: UUID) -> DocumentIdentity | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT d.id,d.organization_id,d.company_id,h.sha256,d.filename,d.mime_type,d.byte_size,d.created_at,d.created_by
                   FROM documents d JOIN document_hashes h ON h.document_id=d.id
                   WHERE d.organization_id=%s AND d.id=%s""",
                (self.organization_id, document_id),
            )
            row = cursor.fetchone()
            return DocumentIdentity(*row) if row else None

    def save(self, job: Job) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO extraction_jobs(id,organization_id,company_id,document_id,job_type,status,progress,created_by,created_at,started_at,completed_at,error_code)
                   VALUES(%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,progress=excluded.progress,
                     started_at=excluded.started_at,completed_at=excluded.completed_at,error_code=excluded.error_code""",
                (job.job_id, job.organization_id, job.company_id, job.job_type, job.status.value, job.progress,
                 job.created_by, job.created_at, job.started_at, job.completed_at, job.error_code[:80]),
            )

    def append(self, event: AuditEvent) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO audit_logs(id,organization_id,company_id,actor_id,action,entity_type,entity_id,
                   previous_reference,new_reference,document_id,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (event.event_id, event.organization_id, event.company_id, event.actor_id, event.action,
                 event.entity_type, str(event.entity_id), event.previous_reference, event.new_reference,
                 event.document_id, event.reason),
            )


    def get_version(self, template_version_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT tv.* FROM template_versions tv
                   JOIN document_format_families f ON f.id=tv.family_id
                   WHERE f.organization_id=%s AND tv.id=%s""",
                (self.organization_id, template_version_id),
            )
            return self._record(cursor, cursor.fetchone())


class PostgresCompanyRepository(PostgresRepositories):
    pass


class PostgresLedgerRepository(PostgresRepositories):
    pass


class PostgresMappingRepository(PostgresRepositories):
    pass


class PostgresBankRepository(PostgresRepositories):
    pass


class PostgresVoucherRuleRepository(PostgresRepositories):
    pass


class PostgresDocumentRepository(PostgresRepositories):
    pass


class PostgresTemplateRepository(PostgresRepositories):
    pass


class PostgresJobRepository(PostgresRepositories):
    def get(self, job_id: UUID) -> Job | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT job_type,organization_id,company_id,created_by,id,status,progress,created_at,
                          started_at,completed_at,coalesce(error_code,'')
                   FROM extraction_jobs WHERE organization_id=%s AND id=%s""",
                (self.organization_id, job_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Job(
                job_type=row[0], organization_id=row[1], company_id=row[2], created_by=row[3], job_id=row[4],
                status=JobStatus(row[5]), progress=row[6], created_at=row[7], started_at=row[8],
                completed_at=row[9], error_code=row[10],
            )


class PostgresAuditRepository(PostgresRepositories):
    def list_events(self) -> tuple[AuditEvent, ...]:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT action,organization_id,company_id,actor_id,entity_type,entity_id,reason,
                          coalesce(previous_reference,''),coalesce(new_reference,''),document_id,id,occurred_at
                   FROM audit_logs WHERE organization_id=%s ORDER BY occurred_at,id""",
                (self.organization_id,),
            )
            return tuple(AuditEvent(*row) for row in cursor.fetchall())
