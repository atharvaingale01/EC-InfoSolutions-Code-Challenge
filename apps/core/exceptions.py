"""Uniform error envelope on top of DRF's default handler."""

from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        # Already the {"detail": "..."} shape.
        return response
    if isinstance(data, (list, dict)):
        response.data = {"detail": "Validation failed.", "errors": data}
    return response
