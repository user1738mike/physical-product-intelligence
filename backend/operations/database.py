from django.db import connection


def runtime_role_privileged():
    """Runtime must neither administer PostgreSQL nor assume database/table ownership."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication "
            "OR r.rolbypassrls OR EXISTS (SELECT 1 FROM pg_database d "
            "WHERE d.datname=current_database() AND pg_has_role(current_user,d.datdba,'MEMBER')) "
            "OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND pg_has_role(current_user,c.relowner,'MEMBER')) "
            "FROM pg_roles r WHERE r.rolname=current_user"
        )
        return cursor.fetchone()[0]
