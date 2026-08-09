from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from ..domain.enums import Role
from .passwords import hash_password, verify_password


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionIdentity:
    session_id: UUID
    organization_id: UUID
    company_id: UUID
    user_id: UUID
    email: str
    display_name: str
    roles: frozenset[Role]
    csrf_token_valid: bool = False


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    identity: SessionIdentity
    absolute_expires_at: datetime


class AuthenticationFailed(RuntimeError):
    pass


class SessionRepository:
    def __init__(self, connect, *, idle_minutes: int = 30, absolute_hours: int = 12) -> None:
        self.connect = connect
        self.idle = timedelta(minutes=idle_minutes)
        self.absolute = timedelta(hours=absolute_hours)

    @staticmethod
    def _record(cursor, row) -> dict[str, Any] | None:
        if row is None: return None
        return dict(zip([column.name if hasattr(column, "name") else column[0] for column in cursor.description], row))

    def authenticate(self, email: str, password: str, company_id: UUID | None,
                     user_agent: str = "", remote_address: str = "", *,
                     organization_name: str | None = None) -> IssuedSession:
        normalized = email.strip().casefold()
        realm = (organization_name or "").strip()
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                throttle_keys=(_digest(f"identity\0{realm.casefold()}\0{normalized}\0{remote_address}"),
                               _digest(f"network\0{remote_address or 'unknown'}"))
                throttles=[];now=datetime.now(timezone.utc)
                for throttle_key in throttle_keys:
                    cursor.execute("""INSERT INTO auth_login_throttles(key_sha256) VALUES(%s)
                        ON CONFLICT(key_sha256) DO UPDATE SET updated_at=now() RETURNING attempt_count,window_started_at,blocked_until""",(throttle_key,))
                    throttle=cursor.fetchone();throttles.append(throttle)
                    if throttle[1]<now-timedelta(minutes=15):
                        cursor.execute("UPDATE auth_login_throttles SET attempt_count=0,window_started_at=now(),blocked_until=NULL WHERE key_sha256=%s",(throttle_key,))
                if any(throttle[2] and throttle[2]>now for throttle in throttles):
                    connection.commit();raise AuthenticationFailed("invalid credentials")
                cursor.execute("""SELECT u.*,c.password_hash FROM users u
                    LEFT JOIN user_credentials c ON c.user_id=u.id
                    JOIN organizations o ON o.id=u.organization_id
                    WHERE lower(u.email)=lower(%s)
                      AND (%s='' OR lower(btrim(o.name))=lower(%s))
                    ORDER BY u.id LIMIT 2 FOR UPDATE OF u""", (normalized,realm,realm))
                user = self._record(cursor, cursor.fetchone())
                ambiguous = bool(user and not realm and cursor.fetchone())
                if not user or ambiguous or not user.get("password_hash"):
                    for throttle_key in throttle_keys:self._throttle_failure(cursor,throttle_key)
                    connection.commit()
                    try: from .passwords import dummy_verify; dummy_verify(password)
                    except Exception: pass
                    raise AuthenticationFailed("invalid credentials")
                if user["status"] != "ACTIVE" or (user.get("locked_until") and user["locked_until"] > now):
                    for throttle_key in throttle_keys:self._throttle_failure(cursor,throttle_key)
                    connection.commit();raise AuthenticationFailed("invalid credentials")
                valid, rehash = verify_password(user["password_hash"], password)
                if not valid:
                    failures = int(user["failed_login_count"] or 0) + 1
                    locked = now + timedelta(minutes=15) if failures >= 5 else None
                    cursor.execute("UPDATE users SET failed_login_count=%s,locked_until=%s WHERE id=%s",
                                   (failures, locked, user["id"]))
                    self._event(cursor, user["organization_id"], user["id"],
                                "ACCOUNT_LOCKED" if locked else "LOGIN_FAILED", remote_address)
                    for throttle_key in throttle_keys:self._throttle_failure(cursor,throttle_key)
                    connection.commit(); raise AuthenticationFailed("invalid credentials")
                cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(user["organization_id"]),))
                cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id or ""),))
                cursor.execute("""SELECT uca.company_id,array_agg(r.code ORDER BY r.code) roles
                    FROM user_company_access uca JOIN roles r ON r.id=uca.role_id
                    JOIN companies co ON co.id=uca.company_id
                    WHERE uca.user_id=%s AND co.organization_id=%s
                    GROUP BY uca.company_id ORDER BY uca.company_id""", (user["id"], user["organization_id"]))
                access = cursor.fetchall()
                selected = next((row for row in access if company_id and row[0] == company_id), None)
                if selected is None and company_id is None and access: selected = access[0]
                if selected is None:
                    connection.rollback(); raise AuthenticationFailed("company access denied")
                if rehash:
                    cursor.execute("UPDATE user_credentials SET password_hash=%s,updated_at=now() WHERE user_id=%s",
                                   (hash_password(password), user["id"]))
                absolute = now + self.absolute
                idle = min(now + self.idle, absolute)
                token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
                session_id = uuid4()
                cursor.execute("""INSERT INTO auth_sessions
                    (id,organization_id,user_id,token_sha256,csrf_sha256,idle_expires_at,absolute_expires_at,user_agent_hash)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (session_id,user["organization_id"],user["id"],_digest(token),_digest(csrf),idle,absolute,
                     _digest(user_agent) if user_agent else None))
                cursor.execute("UPDATE users SET failed_login_count=0,locked_until=NULL,last_login_at=%s WHERE id=%s",
                               (now,user["id"]))
                cursor.execute("DELETE FROM auth_login_throttles WHERE key_sha256=ANY(%s)",(list(throttle_keys),))
                self._event(cursor,user["organization_id"],user["id"],"LOGIN_SUCCEEDED",remote_address)
                connection.commit()
                identity=SessionIdentity(session_id,user["organization_id"],selected[0],user["id"],user["email"],
                                         user["display_name"],frozenset(Role(code) for code in selected[1]))
                return IssuedSession(token,csrf,identity,absolute)
        except Exception:
            if not connection.closed: connection.rollback()
            raise
        finally: connection.close()

    def authorized_companies(self, token: str) -> list[dict[str, Any]]:
        if not token: return []
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT s.organization_id,s.user_id FROM auth_sessions s JOIN users u ON u.id=s.user_id
                    WHERE s.token_sha256=%s AND s.revoked_at IS NULL AND s.idle_expires_at>now()
                      AND s.absolute_expires_at>now() AND u.status='ACTIVE'""",(_digest(token),))
                session=cursor.fetchone()
                if not session:return []
                cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(session[0]),))
                cursor.execute("SELECT set_config('app.company_id','',true)")
                cursor.execute("""SELECT c.id,c.name,array_agg(r.code ORDER BY r.code) roles
                    FROM user_company_access a JOIN companies c ON c.id=a.company_id
                    JOIN roles r ON r.id=a.role_id WHERE a.user_id=%s AND c.organization_id=%s
                    GROUP BY c.id,c.name ORDER BY c.name,c.id""",(session[1],session[0]))
                return [{"id":row[0],"name":row[1],"roles":row[2]} for row in cursor.fetchall()]
        finally:connection.close()

    def resolve(self, token: str, company_id: UUID | None, csrf_token: str = "") -> SessionIdentity | None:
        if not token: return None
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT s.id session_id,s.organization_id,s.user_id,s.csrf_sha256,
                    s.absolute_expires_at,u.email,u.display_name,u.status
                    FROM auth_sessions s JOIN users u ON u.id=s.user_id
                    WHERE s.token_sha256=%s AND s.revoked_at IS NULL
                      AND s.idle_expires_at>now() AND s.absolute_expires_at>now()""",(_digest(token),))
                session=self._record(cursor,cursor.fetchone())
                if not session or session["status"]!="ACTIVE": return None
                cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(session["organization_id"]),))
                cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id or ""),))
                cursor.execute("""SELECT uca.company_id,array_agg(r.code ORDER BY r.code) roles
                    FROM user_company_access uca JOIN roles r ON r.id=uca.role_id
                    JOIN companies c ON c.id=uca.company_id
                    WHERE uca.user_id=%s AND c.organization_id=%s
                    GROUP BY uca.company_id ORDER BY uca.company_id""",(session["user_id"],session["organization_id"]))
                access=cursor.fetchall()
                selected=next((row for row in access if company_id and row[0]==company_id),None)
                if selected is None and company_id is None and access: selected=access[0]
                if selected is None: return None
                now=datetime.now(timezone.utc); idle=min(now+self.idle,session["absolute_expires_at"])
                cursor.execute("UPDATE auth_sessions SET last_seen_at=%s,idle_expires_at=%s WHERE id=%s",
                               (now,idle,session["session_id"]))
                connection.commit()
                return SessionIdentity(session["session_id"],session["organization_id"],selected[0],session["user_id"],
                    session["email"],session["display_name"],frozenset(Role(code) for code in selected[1]),
                    bool(csrf_token and secrets.compare_digest(_digest(csrf_token),session["csrf_sha256"])))
        finally: connection.close()

    def revoke(self, token: str, actor_id: UUID | None = None) -> bool:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE auth_sessions SET revoked_at=now(),revoked_by=%s
                    WHERE token_sha256=%s AND revoked_at IS NULL RETURNING organization_id,user_id""",
                    (actor_id,_digest(token)))
                row=cursor.fetchone()
                if row: self._event(cursor,row[0],row[1],"LOGOUT","")
            connection.commit(); return bool(row)
        finally: connection.close()

    @staticmethod
    def _event(cursor,organization_id,user_id,event_type,remote_address) -> None:
        cursor.execute("""INSERT INTO auth_security_events
            (id,organization_id,user_id,event_type,remote_address_hash)
            VALUES(%s,%s,%s,%s,%s)""",(uuid4(),organization_id,user_id,event_type,
            _digest(remote_address) if remote_address else None))

    @staticmethod
    def _throttle_failure(cursor,key_sha256:str)->None:
        cursor.execute("""UPDATE auth_login_throttles SET attempt_count=attempt_count+1,updated_at=now(),
            blocked_until=CASE WHEN attempt_count+1>=10 THEN now()+interval '15 minutes' ELSE blocked_until END
            WHERE key_sha256=%s""",(key_sha256,))
