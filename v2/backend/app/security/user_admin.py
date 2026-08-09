from __future__ import annotations

from typing import Any
from uuid import UUID,uuid4

from ..domain.enums import Role
from .passwords import hash_password


class UserAdminRepository:
    def __init__(self,connect):self.connect=connect

    @staticmethod
    def _records(cursor):
        names=[column.name if hasattr(column,"name") else column[0] for column in cursor.description]
        return [dict(zip(names,row)) for row in cursor.fetchall()]

    def list_users(self,organization_id:UUID)->list[dict[str,Any]]:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT u.id,u.email,u.display_name,u.status,u.last_login_at,u.created_at,u.must_change_password,
                    coalesce(jsonb_agg(DISTINCT jsonb_build_object('company_id',c.id,'company_name',c.name,'role',r.code))
                      FILTER(WHERE c.id IS NOT NULL),'[]'::jsonb) companies
                    FROM users u LEFT JOIN user_company_access a ON a.user_id=u.id
                    LEFT JOIN companies c ON c.id=a.company_id LEFT JOIN roles r ON r.id=a.role_id
                    WHERE u.organization_id=%s GROUP BY u.id ORDER BY u.display_name,u.email""",(organization_id,))
                return self._records(cursor)
        finally:connection.close()

    def create_user(self,organization_id:UUID,actor_id:UUID,email:str,display_name:str,password:str,
                    assignments:list[tuple[UUID,Role]])->dict[str,Any]:
        user_id=uuid4();connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO users(id,organization_id,email,display_name,status,must_change_password,password_changed_at)
                    VALUES(%s,%s,%s,%s,'ACTIVE',true,now())""",(user_id,organization_id,email.strip().casefold(),display_name.strip()))
                cursor.execute("INSERT INTO user_credentials(user_id,password_hash,updated_by) VALUES(%s,%s,%s)",
                               (user_id,hash_password(password),actor_id))
                for company_id,role in assignments:
                    cursor.execute("SELECT 1 FROM companies WHERE id=%s AND organization_id=%s",(company_id,organization_id))
                    if not cursor.fetchone():raise ValueError("company access denied")
                    cursor.execute("""INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,%s)
                        ON CONFLICT(organization_id,code) DO UPDATE SET code=excluded.code RETURNING id""",
                        (uuid4(),organization_id,role.value));role_id=cursor.fetchone()[0]
                    cursor.execute("INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)",
                                   (user_id,company_id,role_id))
                cursor.execute("""INSERT INTO auth_security_events(id,organization_id,user_id,event_type,detail)
                    VALUES(%s,%s,%s,'USER_CREATED',jsonb_build_object('actor_id',%s::text))""",
                    (uuid4(),organization_id,user_id,actor_id))
            connection.commit();return {"id":user_id,"email":email.strip().casefold(),"display_name":display_name.strip(),"status":"ACTIVE"}
        except Exception as exc:
            connection.rollback()
            if getattr(exc,"sqlstate",None)=="23505":raise ValueError("email or assignment already exists") from exc
            raise
        finally:connection.close()

    def set_status(self,organization_id:UUID,actor_id:UUID,user_id:UUID,status:str)->bool:
        event="USER_DISABLED" if status=="DISABLED" else "USER_REACTIVATED";connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE users SET status=%s WHERE id=%s AND organization_id=%s RETURNING id",(status,user_id,organization_id));row=cursor.fetchone()
                if row and status=="DISABLED":cursor.execute("UPDATE auth_sessions SET revoked_at=now(),revoked_by=%s WHERE user_id=%s AND revoked_at IS NULL",(actor_id,user_id))
                if row:cursor.execute("INSERT INTO auth_security_events(id,organization_id,user_id,event_type) VALUES(%s,%s,%s,%s)",(uuid4(),organization_id,user_id,event))
            connection.commit();return bool(row)
        finally:connection.close()

    def replace_company_role(self,organization_id:UUID,actor_id:UUID,user_id:UUID,company_id:UUID,role:Role)->bool:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE id=%s AND organization_id=%s",(user_id,organization_id));user=cursor.fetchone()
                cursor.execute("SELECT 1 FROM companies WHERE id=%s AND organization_id=%s",(company_id,organization_id));company=cursor.fetchone()
                if not user or not company:return False
                cursor.execute("""INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,%s)
                    ON CONFLICT(organization_id,code) DO UPDATE SET code=excluded.code RETURNING id""",(uuid4(),organization_id,role.value));role_id=cursor.fetchone()[0]
                cursor.execute("DELETE FROM user_company_access WHERE user_id=%s AND company_id=%s",(user_id,company_id))
                cursor.execute("INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)",(user_id,company_id,role_id))
                cursor.execute("INSERT INTO auth_security_events(id,organization_id,user_id,event_type,detail) VALUES(%s,%s,%s,'ROLE_CHANGED',jsonb_build_object('actor_id',%s::text,'company_id',%s::text,'role',%s))",
                               (uuid4(),organization_id,user_id,actor_id,company_id,role.value))
            connection.commit();return True
        except Exception:connection.rollback();raise
        finally:connection.close()

    def reset_password(self,organization_id:UUID,actor_id:UUID,user_id:UUID,password:str)->bool:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE user_credentials c SET password_hash=%s,password_version=password_version+1,
                    updated_by=%s,updated_at=now() FROM users u WHERE c.user_id=u.id AND u.id=%s AND u.organization_id=%s RETURNING c.user_id""",
                    (hash_password(password),actor_id,user_id,organization_id));row=cursor.fetchone()
                if row:
                    cursor.execute("UPDATE users SET must_change_password=true,password_changed_at=now() WHERE id=%s",(user_id,))
                    cursor.execute("UPDATE auth_sessions SET revoked_at=now(),revoked_by=%s WHERE user_id=%s AND revoked_at IS NULL",(actor_id,user_id))
                    cursor.execute("INSERT INTO auth_security_events(id,organization_id,user_id,event_type) VALUES(%s,%s,%s,'PASSWORD_RESET')",(uuid4(),organization_id,user_id))
            connection.commit();return bool(row)
        finally:connection.close()

    def revoke_sessions(self,organization_id:UUID,actor_id:UUID,user_id:UUID)->int:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE auth_sessions s SET revoked_at=now(),revoked_by=%s FROM users u
                    WHERE s.user_id=u.id AND u.id=%s AND u.organization_id=%s AND s.revoked_at IS NULL""",
                    (actor_id,user_id,organization_id));count=cursor.rowcount
            connection.commit();return count
        finally:connection.close()
