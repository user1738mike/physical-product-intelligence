import hashlib
import re
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, storages
from django.utils.module_loading import import_string
from rest_framework.exceptions import PermissionDenied, ValidationError


class PrivateStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError("Private uploads have no public URLs")


def store_upload(upload, organization):
    name = str(upload.name).replace("\\", "/").split("/")[-1]
    extension = PurePosixPath(name).suffix.lower().lstrip(".")
    content_types = {
        "csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
        "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        "pdf": {"application/pdf"},
        "txt": {"text/plain"},
    }
    if extension not in content_types or upload.content_type not in content_types[extension]:
        raise ValidationError("Supported uploads: CSV, XLSX, text-based PDF and UTF text.")
    data = bytearray()
    for chunk in upload.chunks():
        data.extend(chunk)
        if len(data) > settings.INGESTION_LIMITS["upload_bytes"]:
            raise ValidationError("Upload exceeds the configured byte limit.")
    data = bytes(data)
    if (
        not data
        or (extension == "xlsx" and not data.startswith(b"PK\x03\x04"))
        or (extension == "pdf" and not data.startswith(b"%PDF-"))
    ):
        raise ValidationError("File content does not match the declared format.")
    if extension in {"csv", "txt"}:
        if data.startswith((b"PK", b"%PDF", b"\xd0\xcf\x11\xe0")):
            raise ValidationError("File content does not match the declared format.")
        try:
            text = data.decode(
                "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            )
            if "\x00" in text or any(ord(c) < 32 and c not in "\r\n\t" for c in text):
                raise ValueError()
        except (UnicodeError, ValueError) as error:
            raise ValidationError(
                "Text files must contain valid UTF-8 or BOM-marked UTF-16 text."
            ) from error
    scanner = settings.INGESTION_SCANNER
    if scanner:
        try:
            clean = import_string(scanner)(data)
        except Exception as error:
            raise ValidationError("Malware inspection is unavailable; upload rejected.") from error
        if clean is not True:
            raise ValidationError("Upload did not pass malware inspection.")
        scan_status = "clean"
    elif settings.INGESTION_ALLOW_UNSCANNED:
        scan_status = "unscanned"
    else:
        raise PermissionDenied("Uploads require a configured malware scanner in this environment.")
    key = f"{organization.pk}/{uuid.uuid4().hex}.{extension}"
    storage = storages["ingestion"]
    try:
        key = storage.save(key, ContentFile(data))
    except OSError as error:
        raise ValidationError("Private upload storage is unavailable.") from error
    display = re.sub(r"[^\w .()-]", "_", name)[:120] or f"upload.{extension}"
    return dict(
        storage_key=key,
        display_name=display,
        format=extension,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        scan_status=scan_status,
    )


def read_upload(job):
    from .retention import check_readable

    check_readable(job)
    return read_stored_bytes(job)


def read_stored_bytes(job):
    """Integrity primitive; only trusted quiesced backup/restore bypasses lifecycle checks."""
    if job.scan_status != "clean" and not settings.INGESTION_ALLOW_UNSCANNED:
        raise PermissionDenied("This source has not passed malware inspection.")
    try:
        with storages["ingestion"].open(job.storage_key, "rb") as stream:
            data = stream.read(settings.INGESTION_LIMITS["upload_bytes"] + 1)
    except OSError as error:
        raise ValidationError("Private source is unavailable.") from error
    if len(data) != job.size or hashlib.sha256(data).hexdigest() != job.sha256:
        raise ValidationError("Stored upload failed integrity validation.")
    return data
