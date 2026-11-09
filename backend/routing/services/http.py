"""Small JSON HTTP helper with one retry on transient failures."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "HeadwindDispatch/1.0 (educational weather-aware routing demo)"


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def http_json(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 25) -> dict | list:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(2):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"error": True, "reason": body[:400]}
            if not isinstance(parsed, dict):
                parsed = {"error": True, "reason": body[:400]}
            parsed["_http_status"] = exc.code
            if exc.code in {429, 502, 503, 504} and attempt == 0:
                time.sleep(0.5)
                continue
            return parsed
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
                continue
    raise HttpError(f"Network error: {last_error}")
