"""Only new disposable rehearsal databases; never a production role-management shortcut."""

import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql


class Command(BaseCommand):
    help = "Provision isolated rehearsal runtime DML grants after controlled migrations."

    def handle(self, *args, **options):
        database = connection.settings_dict["NAME"]
        role = os.environ.get("PPI_RUNTIME_ROLE", "")
        password = os.environ.get("PPI_RUNTIME_PASSWORD", "")
        if (
            not re.fullmatch(r"ppi_(rehearsal|restore)_[a-f0-9]{10}", database)
            or not re.fullmatch(r"ppi_runtime_[a-f0-9]{10}", role)
            or len(password) < 32
        ):
            raise CommandError("Only explicit isolated rehearsal identity/configuration accepted")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", [role])
            if not cursor.fetchone():
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            for template in (
                "GRANT CONNECT ON DATABASE {} TO {}",
                "GRANT USAGE ON SCHEMA public TO {}",
                "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}",
                "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO {}",
            ):
                ids = (
                    (sql.Identifier(database), sql.Identifier(role))
                    if "DATABASE" in template
                    else (sql.Identifier(role),)
                )
                cursor.execute(sql.SQL(template).format(*ids))
            for table in (
                "plan",
                "account",
                "usage",
                "assignmentevent",
                "reservationevent",
                "operatorevent",
                "assignment",
            ):
                cursor.execute(
                    sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}").format(
                        sql.Identifier("commercial_" + table), sql.Identifier(role)
                    )
                )
            cursor.execute(
                sql.SQL("REVOKE INSERT ON commercial_operatorevent FROM {}").format(
                    sql.Identifier(role)
                )
            )
            for table in (
                "billingaccount",
                "price",
                "statement",
                "paymentoperation",
                "inbox",
                "moneyevent",
                "allocation",
                "accessgrant",
                "statementadjustment",
                "billingaudit",
                "gatewayobject",
                "gatewaycall",
            ):
                cursor.execute(
                    sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}").format(
                        sql.Identifier("billing_" + table), sql.Identifier(role)
                    )
                )
            for table in (
                "price",
                "statement",
                "moneyevent",
                "allocation",
                "accessgrant",
                "statementadjustment",
                "gatewayobject",
                "gatewaycall",
            ):
                cursor.execute(
                    sql.SQL("REVOKE INSERT ON {} FROM {}").format(
                        sql.Identifier("billing_" + table), sql.Identifier(role)
                    )
                )
        self.stdout.write("rehearsal_runtime_grants_current")
