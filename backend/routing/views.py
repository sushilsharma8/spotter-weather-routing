import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from routing.services.geocode import search_places
from routing.services.planner import PlanError, assess_trip, corridor_weather, plan_trip


def _json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode())
    except json.JSONDecodeError as exc:
        raise PlanError("Request body must be JSON.") from exc
    if not isinstance(payload, dict):
        raise PlanError("Request body must be a JSON object.")
    return payload


def _error(exc: PlanError) -> JsonResponse:
    return JsonResponse({"error": exc.message, **exc.details}, status=exc.status)


@require_GET
def health(_request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "headwind",
            "backend": "django",
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )


@require_GET
def suggest(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    try:
        places = search_places(query, limit=5)
    except PlanError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "results": [
                {"label": place.label, "lat": place.lat, "lon": place.lon, "query": place.query}
                for place in places
            ]
        }
    )


@require_POST
def plan(request):
    try:
        return JsonResponse(plan_trip(_json_body(request)))
    except PlanError as exc:
        return _error(exc)


@require_POST
def assess(request):
    try:
        return JsonResponse(assess_trip(_json_body(request)))
    except PlanError as exc:
        return _error(exc)


@require_POST
def corridor(request):
    try:
        return JsonResponse(corridor_weather(_json_body(request)))
    except PlanError as exc:
        return _error(exc)


def frontend(request, resource: str = ""):
    if not settings.SERVE_FRONTEND:
        return HttpResponse("Frontend serving is disabled.", status=404, content_type="text/plain")
    dist = Path(settings.FRONTEND_DIST).resolve()
    if not dist.is_dir():
        return HttpResponse(
            "Frontend is not built. From frontend/, run npm install and npm run build.",
            status=503,
            content_type="text/plain",
        )
    relative = resource or "index.html"
    candidate = (dist / relative).resolve()
    if not str(candidate).startswith(str(dist)) or not candidate.is_file():
        candidate = dist / "index.html"
    content_type = _content_type(candidate)
    response = FileResponse(candidate.open("rb"), content_type=content_type)
    if candidate.name == "index.html":
        response["Cache-Control"] = "no-cache"
    else:
        response["Cache-Control"] = "public, max-age=86400"
    return response


def _content_type(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".json": "application/json",
        ".png": "image/png",
        ".woff2": "font/woff2",
        ".ico": "image/x-icon",
    }.get(path.suffix.lower(), "application/octet-stream")
