"""Create a non-superuser, non-BYPASSRLS database owner for public CI tests."""

from __future__ import annotations

import os

import psycopg
from psycopg import sql


def main() -> None:
    admin_url = os.environ["POSTGRES_CI_ADMIN_URL"]
    role = "phase2_ci"
    database = "business_automation_test"

    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                ).format(
                    sql.Identifier(role),
                    sql.Literal(os.environ["POSTGRES_CI_APP_PASSWORD"]),
                )
            )
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(role)
                )
            )


if __name__ == "__main__":
    main()
