import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .storage import read_upload


def parse(job, options):
    payload = json.dumps(
        {
            "data": base64.b64encode(read_upload(job)).decode("ascii"),
            "format": job.format,
            "options": options,
            "limits": settings.INGESTION_LIMITS,
        }
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("worker.py"))],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=settings.INGESTION_LIMITS["seconds"],
            env={
                key: os.environ[key]
                for key in ("SYSTEMROOT", "WINDIR", "PATH")
                if key in os.environ
            },
            check=True,
        )
        if len(result.stdout) > settings.INGESTION_LIMITS["text_chars"] * 8:
            raise ValidationError("Parser output limit exceeded.")
        output = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError, OSError) as error:
        raise ValidationError(
            "Processing stopped safely: parser failed or exceeded its resource limit."
        ) from error
    if not output["ok"]:
        raise ValidationError(output["error"])
    return output
