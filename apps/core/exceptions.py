"""Uniform error envelope on top of DRF's default handler, plus an audit line
for authentication, authorization and throttling failures."""

import logging

from rest_framework.views import exception_handler as drf_exception_handler

audit = logging.getLogger("apps.audit")
AUDITED = {401: "auth_failed", 403: "forbidden", 429: "throttled"}


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if response.status_code in AUDITED:
        request = context.get("request")
        user = getattr(request, "user", None)
        audit.warning(
            "%s %s %s",
            AUDITED[response.status_code],
            getattr(request, "method", "-"),
            getattr(request, "path", "-"),
            extra={
                "event": AUDITED[response.status_code],
                "status": response.status_code,
                "path": getattr(request, "path", None),
                "user_id": str(user.pk) if user is not None and user.is_authenticated else None,
                "client_ip": request.META.get("REMOTE_ADDR") if request is not None else None,
            },
        )

    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        # Already the {"detail": "..."} shape.
        return response
    if isinstance(data, (list, dict)):
        response.data = {"detail": "Validation failed.", "errors": data}
    return response
