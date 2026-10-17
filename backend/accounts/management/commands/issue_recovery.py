"""Issue only after out-of-band identity verification; never print the link."""

import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.recovery import issue


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--user", required=True)
        parser.add_argument("--case-reference", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        # POSIX container permission semantics are required; no false Windows ACL claim.
        if os.name != "posix":
            raise CommandError("Run inside the protected Linux operator container.")
        path = Path(options["output"])
        descriptor = None
        try:
            parent = path.parent
            if (
                not parent.is_dir()
                or parent.stat().st_uid != os.geteuid()
                or parent.stat().st_mode & 0o077
            ):
                raise ValueError()
            with transaction.atomic():
                actor = get_user_model().objects.get(username=options["actor"])
                token = issue(actor, options["user"], options["case_reference"])
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as output:
                    descriptor = None
                    output.write("/account/recover#token=" + token + "\n")
                    output.flush()
                    os.fsync(output.fileno())
            self.stdout.write("Recovery issued to protected file; link valid for fifteen minutes.")
        except Exception:
            raise CommandError(
                "Recovery issuance failed; private diagnostics suppressed."
            ) from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
