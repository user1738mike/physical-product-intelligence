from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class BoundedUploadHandler(FileUploadHandler):
    """Abort oversized files while streaming, before downstream handlers persist them."""

    def receive_data_chunk(self, raw_data, start):
        if start + len(raw_data) > settings.INGESTION_LIMITS["upload_bytes"]:
            self.request.ingestion_oversized = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None
