"""Our own wire format: `POST {base_url}/v1/extract` with the request as JSON.

The server answers `{"answers": {...}}` (plus optional `usage`). It declares a limit with a 413,
or with a JSON error whose code, type or message contains "unsupported"; both become
`Unsupported`. A bearer token is sent when `EXTRACT_INDEX_API_KEY` is set.
"""

from __future__ import annotations

import os
import time
from typing import Any

from . import Engine, EngineError, Unsupported, json_or_none, make_client, send_with_retries, short

TOKEN_ENV = "EXTRACT_INDEX_API_KEY"


def _error_text(body: Any) -> str:
    """The error part of a JSON body, flattened to text ('' if there is none)."""
    if not isinstance(body, dict):
        return ""
    err = body.get("error", body.get("errors", body.get("detail")))
    if err is None:
        return ""
    return short(err, 1000)


class HttpEngine(Engine):
    name = "http"
    env = (TOKEN_ENV,)

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 120.0,
                 attempts: int = 6, **options: Any) -> None:
        opts = dict(options)
        self.sleep = opts.pop("sleep", time.sleep)
        self.client, self._owned = make_client(opts, float(timeout))
        super().__init__(base_url=base_url, timeout=timeout, attempts=attempts, **opts)
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.attempts = int(attempts)

    def _headers(self) -> dict:
        token = os.environ.get(TOKEN_ENV)
        return {"Authorization": f"Bearer {token}"} if token else {}

    def __call__(self, request: dict) -> dict:
        r = send_with_retries(self.client, "POST", f"{self.base_url}/v1/extract", json=request,
                              headers=self._headers(), timeout=self.timeout,
                              attempts=self.attempts, sleep=self.sleep)
        body = json_or_none(r)
        err = _error_text(body)
        if r.status_code == 413:
            raise Unsupported(err or "request too large (413)")
        if "unsupported" in err.lower():
            raise Unsupported(err)
        if r.status_code >= 400:
            raise EngineError(f"HTTP {r.status_code}: {err or short(r.text)}")
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise EngineError(f"malformed response: {short(r.text)}")
        return body

    def info(self) -> dict:
        return {"name": self.name, "endpoint": f"{self.base_url}/v1/extract", "timeout": self.timeout}

    def close(self) -> None:
        if self._owned:
            self.client.close()
