from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4
from typing import Any, Callable

from .models import BillingMode


@dataclass(frozen=True)
class QuotaThresholds:
    warning: int = 85
    critical: int = 93
    hard_stop: int = 95

    def __post_init__(self) -> None:
        if not 0 < self.warning < self.critical < self.hard_stop <= 100:
            raise ValueError("quota thresholds must be ordered percentages")


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    state: str
    used: int
    reserved: int
    limit: int
    remaining: int
    reset_at: datetime
    reservation_id: UUID | None = None


class AiQuotaService:
    """Atomic in-process gate; PostgreSQL repository supplies cross-process locking."""

    def __init__(self, limit: int = 10_000, used: int = 0, reserved: int = 0,
                 thresholds: QuotaThresholds | None = None,
                 billing_mode: BillingMode = BillingMode.FREE_ONLY) -> None:
        self.limit, self.used, self.reserved = limit, used, reserved
        self.thresholds = thresholds or QuotaThresholds()
        self.billing_mode = billing_mode
        self._reservations: dict[UUID, int] = {}
        self._lock = Lock()

    @staticmethod
    def reset_at(now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        tomorrow = now.date().toordinal() + 1
        return datetime.fromordinal(tomorrow).replace(tzinfo=timezone.utc)

    def status(self) -> QuotaDecision:
        committed = self.used + self.reserved
        percentage = committed * 100 / self.limit if self.limit else 100
        state = "NORMAL"
        if percentage >= self.thresholds.hard_stop: state = "HARD_STOP"
        elif percentage >= self.thresholds.critical: state = "CRITICAL"
        elif percentage >= self.thresholds.warning: state = "WARNING"
        return QuotaDecision(percentage < self.thresholds.hard_stop, state, self.used, self.reserved,
                             self.limit, max(0, self.limit - committed), self.reset_at())

    def reserve(self, estimated_units: int) -> QuotaDecision:
        if estimated_units <= 0: raise ValueError("estimated units must be positive")
        with self._lock:
            projected = self.used + self.reserved + estimated_units
            hard_limit = self.limit * self.thresholds.hard_stop / 100
            if self.billing_mode == BillingMode.FREE_ONLY and projected >= hard_limit:
                value = self.status()
                return QuotaDecision(False, "HARD_STOP", value.used, value.reserved, value.limit,
                                     value.remaining, value.reset_at)
            reservation_id = uuid4(); self._reservations[reservation_id] = estimated_units
            self.reserved += estimated_units
            value = self.status()
            return QuotaDecision(True, value.state, value.used, value.reserved, value.limit,
                                 value.remaining, value.reset_at, reservation_id)

    def reconcile(self, reservation_id: UUID, actual_units: int) -> QuotaDecision:
        if actual_units < 0: raise ValueError("actual units cannot be negative")
        with self._lock:
            estimated = self._reservations.pop(reservation_id)
            self.reserved -= estimated
            self.used += actual_units
            return self.status()

    def release(self, reservation_id: UUID) -> QuotaDecision:
        with self._lock:
            self.reserved -= self._reservations.pop(reservation_id)
            return self.status()


class PostgresAiQuotaService:
    """Tenant quota ledger with row locks for multi-process cloud reservations."""

    def __init__(self, connect: Callable[[], Any], organization_id: UUID, company_id: UUID,
                 provider_account_key: str, limit: int = 10_000,
                 thresholds: QuotaThresholds | None = None,
                 billing_mode: BillingMode = BillingMode.FREE_ONLY) -> None:
        self._connect=connect;self.organization_id=organization_id;self.company_id=company_id
        self.provider_account_key=provider_account_key;self.limit=limit
        self.thresholds=thresholds or QuotaThresholds();self.billing_mode=billing_mode

    def _account(self,cursor) -> UUID:
        cursor.execute("""SELECT id FROM ai_provider_accounts WHERE organization_id=%s AND provider='CLOUDFLARE_WORKERS_AI'
            AND provider_account_id=%s FOR UPDATE""",(self.organization_id,self.provider_account_key))
        row=cursor.fetchone()
        if row:return row[0]
        account_id=uuid4();cursor.execute("""INSERT INTO ai_provider_accounts
            (id,organization_id,provider,provider_account_id,deployment_mode,billing_mode,daily_limit,warning_percent,critical_percent,hard_stop_percent,enabled,health)
            VALUES(%s,%s,'CLOUDFLARE_WORKERS_AI',%s,'BYOC',%s,%s,%s,%s,%s,true,'UNVERIFIED')""",
            (account_id,self.organization_id,self.provider_account_key,self.billing_mode.value,self.limit,
             self.thresholds.warning,self.thresholds.critical,self.thresholds.hard_stop))
        return account_id

    def _usage(self,cursor,account_id:UUID,lock:bool=True):
        today=datetime.now(timezone.utc).date();reset=AiQuotaService.reset_at()
        cursor.execute("""INSERT INTO ai_daily_usage(id,organization_id,company_id,provider_account_id,usage_date,reset_at)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(organization_id,company_id,provider_account_id,usage_date) DO NOTHING""",
            (uuid4(),self.organization_id,self.company_id,account_id,today,reset))
        cursor.execute("""SELECT used_units,reserved_units,reset_at FROM ai_daily_usage
            WHERE organization_id=%s AND company_id=%s AND provider_account_id=%s AND usage_date=%s"""+(" FOR UPDATE" if lock else ""),
            (self.organization_id,self.company_id,account_id,today))
        return cursor.fetchone()

    def _decision(self,used:int,reserved:int,reset:datetime,reservation_id:UUID|None=None)->QuotaDecision:
        committed=used+reserved;percentage=committed*100/self.limit if self.limit else 100;state="NORMAL"
        if percentage>=self.thresholds.hard_stop:state="HARD_STOP"
        elif percentage>=self.thresholds.critical:state="CRITICAL"
        elif percentage>=self.thresholds.warning:state="WARNING"
        return QuotaDecision(percentage<self.thresholds.hard_stop,state,used,reserved,self.limit,max(0,self.limit-committed),reset,reservation_id)

    def status(self)->QuotaDecision:
        connection=self._connect()
        try:
            with connection.cursor() as cursor:
                account=self._account(cursor);used,reserved,reset=self._usage(cursor,account,False)
            connection.commit();return self._decision(used,reserved,reset)
        except Exception:connection.rollback();raise
        finally:connection.close()

    def reserve(self,estimated_units:int)->QuotaDecision:
        if estimated_units<=0:raise ValueError("estimated units must be positive")
        connection=self._connect()
        try:
            with connection.cursor() as cursor:
                account=self._account(cursor);used,reserved,reset=self._usage(cursor,account)
                if self.billing_mode==BillingMode.FREE_ONLY and used+reserved+estimated_units>=self.limit*self.thresholds.hard_stop/100:
                    connection.commit();return QuotaDecision(False,"HARD_STOP",used,reserved,self.limit,max(0,self.limit-used-reserved),reset)
                reservation_id=uuid4();cursor.execute("""INSERT INTO ai_quota_reservations
                    (id,organization_id,company_id,provider_account_id,estimated_units,status,expires_at)
                    VALUES(%s,%s,%s,%s,%s,'RESERVED',now()+interval '15 minutes')""",
                    (reservation_id,self.organization_id,self.company_id,account,estimated_units))
                cursor.execute("""UPDATE ai_daily_usage SET reserved_units=reserved_units+%s,updated_at=now()
                    WHERE organization_id=%s AND company_id=%s AND provider_account_id=%s AND usage_date=%s""",
                    (estimated_units,self.organization_id,self.company_id,account,datetime.now(timezone.utc).date()))
            connection.commit();return self._decision(used,reserved+estimated_units,reset,reservation_id)
        except Exception:connection.rollback();raise
        finally:connection.close()

    def _settle(self,reservation_id:UUID,actual_units:int|None,status:str)->QuotaDecision:
        connection=self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT provider_account_id,estimated_units,status FROM ai_quota_reservations
                    WHERE id=%s AND organization_id=%s AND company_id=%s FOR UPDATE""",
                    (reservation_id,self.organization_id,self.company_id));row=cursor.fetchone()
                if not row or row[2]!="RESERVED":raise KeyError("active reservation not found")
                account,estimated,_=row;used,reserved,reset=self._usage(cursor,account)
                actual=actual_units or 0
                cursor.execute("""UPDATE ai_quota_reservations SET actual_units=%s,status=%s,reconciled_at=now() WHERE id=%s""",
                               (actual,status,reservation_id))
                cursor.execute("""UPDATE ai_daily_usage SET reserved_units=greatest(0,reserved_units-%s),used_units=used_units+%s,updated_at=now()
                    WHERE organization_id=%s AND company_id=%s AND provider_account_id=%s AND usage_date=%s""",
                    (estimated,actual,self.organization_id,self.company_id,account,datetime.now(timezone.utc).date()))
            connection.commit();return self._decision(used+actual,max(0,reserved-estimated),reset)
        except Exception:connection.rollback();raise
        finally:connection.close()

    def reconcile(self,reservation_id:UUID,actual_units:int)->QuotaDecision:
        if actual_units<0:raise ValueError("actual units cannot be negative")
        return self._settle(reservation_id,actual_units,"RECONCILED")

    def release(self,reservation_id:UUID)->QuotaDecision:return self._settle(reservation_id,None,"RELEASED")
