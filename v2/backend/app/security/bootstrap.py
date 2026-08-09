from __future__ import annotations

import argparse
import getpass
import os
from uuid import uuid4

from ..infrastructure.postgres_migrations import apply_migrations
from .passwords import hash_password


def bootstrap_admin(connection, organization: str, company: str, email: str,
                    display_name: str, password: str) -> dict[str, str]:
    organization=organization.strip();company=company.strip();email=email.strip().casefold();display_name=display_name.strip()
    if not all((organization,company,email,display_name)):raise ValueError("organization, company, email, and display name are required")
    password_hash=hash_password(password)
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM organizations WHERE lower(btrim(name))=lower(%s)",(organization,))
        row=cursor.fetchone();organization_id=row[0] if row else uuid4()
        if not row:cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(organization_id,organization))
        cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
        cursor.execute("SELECT id FROM companies WHERE organization_id=%s AND lower(name)=lower(%s)",(organization_id,company))
        row=cursor.fetchone();company_id=row[0] if row else uuid4()
        if not row:cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,%s,%s)",(company_id,organization_id,company,company))
        cursor.execute("SELECT id FROM users WHERE organization_id=%s AND lower(email)=lower(%s)",(organization_id,email))
        if cursor.fetchone():raise ValueError("that administrator already exists in this organization")
        user_id,role_id=uuid4(),uuid4()
        cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status,must_change_password,password_changed_at) VALUES(%s,%s,%s,%s,'ACTIVE',false,now())",(user_id,organization_id,email,display_name))
        cursor.execute("INSERT INTO user_credentials(user_id,password_hash,updated_by) VALUES(%s,%s,%s)",(user_id,password_hash,user_id))
        cursor.execute("""INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,'OWNER')
            ON CONFLICT(organization_id,code) DO UPDATE SET code=excluded.code RETURNING id""",(role_id,organization_id))
        role_id=cursor.fetchone()[0]
        cursor.execute("INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)",(user_id,company_id,role_id))
        cursor.execute("INSERT INTO auth_security_events(id,organization_id,user_id,event_type,detail) VALUES(%s,%s,%s,'USER_CREATED',jsonb_build_object('company_id',%s::text,'bootstrap',true))",(uuid4(),organization_id,user_id,company_id))
    connection.commit()
    return {"organization_id":str(organization_id),"company_id":str(company_id),"user_id":str(user_id)}


def main() -> int:
    parser=argparse.ArgumentParser(description="Create the first V2 organization, company, and owner account.")
    parser.add_argument("--organization",required=True);parser.add_argument("--company",required=True)
    parser.add_argument("--email",required=True);parser.add_argument("--display-name",required=True)
    args=parser.parse_args();password=getpass.getpass("New owner password: ");confirmation=getpass.getpass("Confirm password: ")
    if password!=confirmation:parser.error("passwords do not match")
    url=os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:parser.error("POSTGRES_URL or DATABASE_URL must be configured")
    import psycopg
    connection=psycopg.connect(url)
    try:
        apply_migrations(connection);result=bootstrap_admin(connection,args.organization,args.company,args.email,args.display_name,password)
    except Exception:
        connection.rollback();raise
    finally:connection.close()
    print(f"Owner created for organization {args.organization!r}. IDs: {result}")
    return 0


if __name__=="__main__":raise SystemExit(main())
