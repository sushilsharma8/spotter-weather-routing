import logging

from django.http import JsonResponse

log = logging.getLogger(__name__)


class ApiErrorMiddleware:
    """Turn unexpected /api errors into JSON. Do not leak tracebacks to clients."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            if request.path.startswith("/api/"):
                log.exception("Unhandled API error on %s", request.path)
                return JsonResponse({"error": "Unexpected server error."}, status=500)
            raise
