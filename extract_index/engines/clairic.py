"""Cloudflare Workers AI `@cf/cloudflare/clairic` over the REST API.

`POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/clairic`
with `Authorization: Bearer $CLOUDFLARE_API_TOKEN` and body
`{"model": "clairic", "state", "fields", "reference_date"?}`. The account id comes from
`CLOUDFLARE_ACCOUNT_ID`, or, if unset, from `GET /client/v4/accounts` when the token sees exactly
one account (cached; never logged).

What the live API returned (4 probe calls, 2026-10-24):
- 200: `{"result": {"model": "clairic", "answers": {...}, "truncated": false, "usage":
  {"state_tokens", "image_tokens", "schema_tokens", "input_tokens", "output_tokens": 0, "passes"}},
  "success": true, "errors": [], "messages": []}`. Scalar answers carry `type`, `value`, `guess`,
  `p_null`, `confidence` (+ `span` for text, `unit` for durations); list answers carry `value`,
  `spans` or `confidences`, `confidence`, and no `p_null`. Times and datetimes come with seconds
  ("14:30:00"). A 9-field request on a 100-token state took ~0.3 s (3 passes).
- Request validation errors are HTTP 422 (not 400): `{"errors": [{"message": "AiError: AiError:
  invalid field name '...' (<request id>)", "code": 3030}], "success": false, "result": {},
  "messages": []}`, in ~0.1 s. The too-long message was not observed (it needs a >64k-token
  input), so `TOO_LONG_RE` is deliberately broad and applies to 400, 413 and 422.
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

from . import Engine, EngineError, Unsupported, json_or_none, make_client, send_with_retries, short

API = "https://api.cloudflare.com/client/v4"
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
DEFAULT_MODEL = "@cf/cloudflare/clairic"
CONTEXT_TOKENS = 65_536
PASS_TOKENS = 8_192

# A 400/422 whose message matches this is a declared limit (input too long), not a failure.
# "exceed" alone is not enough: a 400 "daily allocation exceeded" must stay an error (retried later).
TOO_LONG_RE = re.compile(
    r"too long|too large|too many tokens|context (?:length|window|size|limit)|token limit|input length|"
    r"maximum (?:context|input|length|tokens?)|tokens? exceed|"
    r"exceed\w* (?:the )?(?:max\w* )?(?:context|tokens?|input|length)", re.I)


def _cf_errors(body: Any) -> str:
    """The `errors[].message` texts of a Cloudflare API envelope, joined."""
    if not isinstance(body, dict):
        return ""
    errors = body.get("errors") or []
    if isinstance(errors, list):
        parts = [f"{e.get('code')}: {e.get('message')}" if isinstance(e, dict) else str(e) for e in errors]
        return "; ".join(parts)
    return short(errors)


class ClairicEngine(Engine):
    name = "clairic"
    env = (TOKEN_ENV, ACCOUNT_ENV)

    def __init__(self, timeout: float = 120.0, model: str = DEFAULT_MODEL, attempts: int = 6,
                 **options: Any) -> None:
        opts = dict(options)
        self.sleep = opts.pop("sleep", time.sleep)
        self.api = opts.pop("api", API)
        self.client, self._owned = make_client(opts, float(timeout))
        super().__init__(timeout=timeout, model=model, attempts=attempts, **opts)
        self.timeout = float(timeout)
        self.model = model
        self.attempts = int(attempts)
        self._account_id: str | None = None

    # ------------------------------------------------------------ auth and account

    def _token(self) -> str:
        token = os.environ.get(TOKEN_ENV)
        if not token:
            raise EngineError(f"{TOKEN_ENV} is not set")
        return token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    def account_id(self) -> str:
        """`CLOUDFLARE_ACCOUNT_ID`, or the token's single account (looked up once)."""
        if self._account_id:
            return self._account_id
        env = os.environ.get(ACCOUNT_ENV)
        if env:
            self._account_id = env
            return env
        r = send_with_retries(self.client, "GET", f"{self.api}/accounts", headers=self._headers(),
                              timeout=self.timeout, attempts=self.attempts, sleep=self.sleep)
        body = json_or_none(r)
        if r.status_code != 200 or not isinstance(body, dict) or not body.get("success"):
            raise EngineError(f"account lookup failed (HTTP {r.status_code}): {_cf_errors(body) or short(r.text)}")
        accounts = body.get("result") or []
        if len(accounts) != 1 or not isinstance(accounts[0], dict) or not accounts[0].get("id"):
            raise EngineError(f"the token sees {len(accounts)} accounts; set {ACCOUNT_ENV}")
        self._account_id = str(accounts[0]["id"])
        print(f"[clairic] account id discovered from the token ({ACCOUNT_ENV} unset)", file=sys.stderr)
        return self._account_id

    # ------------------------------------------------------------ calls

    def url(self) -> str:
        return f"{self.api}/accounts/{self.account_id()}/ai/run/{self.model}"

    def body(self, request: dict) -> dict:
        out: dict[str, Any] = {"model": "clairic", "state": request["state"], "fields": request["fields"]}
        if request.get("reference_date"):
            out["reference_date"] = request["reference_date"]
        return out

    def __call__(self, request: dict) -> dict:
        r = send_with_retries(self.client, "POST", self.url(), json=self.body(request),
                              headers=self._headers(), timeout=self.timeout,
                              attempts=self.attempts, sleep=self.sleep)
        body = json_or_none(r)
        if r.status_code == 413:
            raise Unsupported(f"request too large (413): {_cf_errors(body) or short(r.text)}")
        if r.status_code >= 400:
            message = _cf_errors(body) or short(r.text)
            if r.status_code in (400, 422) and TOO_LONG_RE.search(message):
                raise Unsupported(short(message))
            raise EngineError(f"HTTP {r.status_code}: {short(message)}")
        if not isinstance(body, dict) or not body.get("success", True):
            raise EngineError(f"API error: {_cf_errors(body) or short(r.text)}")
        result = body.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
            raise EngineError(f"malformed result: {short(result)}")
        if result.get("truncated"):
            raise EngineError("response is truncated (the kit forbids truncation)")
        return result

    def info(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "endpoint": f"{self.api}/accounts/{{account_id}}/ai/run/{self.model}",
            "limits": {"context_tokens": CONTEXT_TOKENS, "pass_tokens": PASS_TOKENS},
            "timeout": self.timeout,
        }

    def close(self) -> None:
        if self._owned:
            self.client.close()
