import logging
import re
import time
import uuid

logger = logging.getLogger("operations.requests")
VALID_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied_id = request.headers.get("X-Request-ID", "")
        request.request_id = supplied_id if VALID_ID.fullmatch(supplied_id) else uuid.uuid4().hex
        started = time.perf_counter()
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        if request.path.startswith("/api/v1/health/"):
            response["Cache-Control"] = "no-store"
        logger.info(
            "http_request",
            extra={
                "request_id": request.request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response
