"""Request id propagation and a one-line-per-request access log."""

import logging
import time

from django.utils.deprecation import MiddlewareMixin

from .logging import clean_request_id, new_request_id, request_id_var

logger = logging.getLogger("apps.requests")

HEADER = "X-Request-ID"
QUIET_PATHS = {"/health/"}  # polled by the compose healthcheck; keep it out of the log


class RequestIDMiddleware(MiddlewareMixin):
    """
    Reuse the id nginx assigns (`X-Request-ID`), or mint one, expose it on
    `request.request_id`, bind it for logging, and echo it in the response so a
    client can quote it when reporting a problem.
    """

    def process_request(self, request):
        rid = clean_request_id(request.headers.get(HEADER)) or new_request_id()
        request.request_id = rid
        request._request_id_token = request_id_var.set(rid)
        request._started = time.monotonic()

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response[HEADER] = rid
        started = getattr(request, "_started", None)
        if started is not None and request.path not in QUIET_PATHS:
            user = getattr(request, "user", None)
            logger.info(
                "%s %s -> %s in %dms",
                request.method,
                request.get_full_path(),
                response.status_code,
                int((time.monotonic() - started) * 1000),
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "user_id": str(user.pk) if user is not None and user.is_authenticated else None,
                    "client_ip": request.META.get("REMOTE_ADDR"),
                },
            )
        token = getattr(request, "_request_id_token", None)
        if token is not None:
            request_id_var.reset(token)
        return response
