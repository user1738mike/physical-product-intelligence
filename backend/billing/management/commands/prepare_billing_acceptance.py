"""Create only synthetic financial fixtures in the guarded isolated rehearsal."""

import json
import re
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from billing import adapter, services
from billing.models import GatewayObject
from commercial import services as access
from organizations.services import add_member, create_organization


class Command(BaseCommand):
    help = "Prepare isolated synthetic billing acceptance; never a live payment setup command."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True)
        parser.add_argument("--member", required=True)

    def handle(self, *args, **o):
        if not getattr(settings, "ALLOW_REHEARSAL_PROVIDER", False) or not re.fullmatch(
            r"ppi_rehearsal_[a-f0-9]{10}", connection.settings_dict["NAME"]
        ):
            raise CommandError("Isolated rehearsal required")
        adapter.require()
        users = get_user_model()
        owner = users.objects.get(username=o["owner"])
        member = users.objects.get(username=o["member"])
        suffix = uuid.uuid4().hex[:10]
        operator = users.objects.create_user("billing-acceptance-" + suffix, is_staff=True)
        policy = {key: value for key, value in access.PILOT.items() if key != "name"}
        plan = access.publish(
            operator,
            code="billing-acceptance-" + suffix,
            version=1,
            name="Synthetic billing access",
            policy=policy,
        )
        price = services.publish_price(
            operator,
            code="billing-acceptance-" + suffix,
            version=1,
            plan=plan,
            currency_code="XTS",
            exponent=0,
            unit_minor=1000,
            mode="test",
            reason="Synthetic acceptance only",
        )
        result = {"operator": operator.username}
        for state in ("pending", "partial", "unknown", "action_required"):
            org = create_organization(
                owner, name="Synthetic billing " + state, slug="billing-" + state + "-" + suffix
            )
            add_member(owner, org.pk, username=operator.username, role="admin")
            if state == "partial":
                add_member(owner, org.pk, username=member.username, role="admin")
            account = services.configure_simulator(operator, org, reason="Synthetic acceptance")
            start, end = access.month()
            statement = services.generate(
                operator,
                account,
                price,
                start=start,
                end=end,
                access_transition=True,
                reason="Explicit synthetic fulfillment",
            )
            statement = services.finalize(operator, statement, reason="Synthetic acceptance")
            operation = services.request_operation(
                operator,
                org.pk,
                statement.pk,
                uuid.uuid4(),
                partial_minor=400 if state == "partial" else None,
            )
            if state == "unknown":
                original = adapter.create

                def fail_after_create(item, create=original):
                    create(item)
                    raise adapter.UnknownOutcome()

                with patch("billing.adapter.create", side_effect=fail_after_create):
                    services.process_outbound(operator, operation.pk)
            else:
                operation = services.process_outbound(operator, operation.pk)
                obj = GatewayObject.objects.get(operation=operation)
                obj.version += 1
                obj.state = "paid"
                if state == "action_required":
                    obj.amount_minor = 1100
                obj.save()
                body = json.dumps(adapter.payload(operation, obj), sort_keys=True).encode()
                timestamp, proof = adapter.sign(body)
                event = services.receive(body, timestamp, proof)
                if state != "pending":
                    services.process_event(operator, event.pk)
            result[state] = {
                "org": str(org.pk),
                "statement": str(statement.pk),
                "operation": str(operation.pk),
            }
        self.stdout.write(json.dumps(result))
