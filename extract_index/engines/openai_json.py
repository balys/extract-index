"""Reference System Two baseline: an OpenAI-compatible chat model writing one JSON object.

Never ranked. The prompt is fixed (no per-test tuning): a system message with the value forms and
a user message with the field specs as JSON, the reference date, and the document. The model
answers `{field: value}`, which maps to `{"answers": {field: {"type", "value"}}}`.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import Engine, EngineError, Unsupported, json_or_none, make_client, send_with_retries, short

SYSTEM_PROMPT = """You extract typed values from a document.
You get a map of fields (name -> spec with "type" and optional "instructions", "unit",
"decimals", "integer", "items") and a document. Reply with exactly one JSON object that has every
field name as a key and nothing else. Each value must be in the form for its type:
- text: a string, copied from the document where possible
- number: a JSON number (no units or thousands separators); duration: a number in the field's unit
- date: "YYYY-MM-DD"; time: "HH:MM" or "HH:MM:SS"; datetime: "YYYY-MM-DDTHH:MM" (no time zone)
- list: a JSON array of item values in the item type's form
Use null when the document does not determine the value (for lists, null or []).
Resolve dates written without a year against the reference date, if one is given."""

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
_TOO_LONG_RE = re.compile(r"context_length_exceeded|maximum context length|too many tokens|too long", re.I)


def user_prompt(request: dict) -> str:
    parts = ["Fields:", json.dumps(request["fields"], ensure_ascii=False, indent=1)]
    if request.get("reference_date"):
        parts += ["", f"Reference date: {request['reference_date']}"]
    parts += ["", "Document:", request["state"]]
    return "\n".join(parts)


def parse_output(fields: dict, content: str) -> dict:
    """The answers for `fields` from the model's text, or raise `EngineError` if unparseable."""
    if not isinstance(content, str) or not content.strip():
        raise EngineError("empty model output")
    m = _FENCE_RE.match(content)
    text = m[1] if m else content.strip()
    try:
        obj = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise EngineError(f"unparseable model output: {short(content, 200)}") from None
        try:
            obj = json.loads(text[start:end + 1])
        except ValueError:
            raise EngineError(f"unparseable model output: {short(content, 200)}") from None
    if not isinstance(obj, dict):
        raise EngineError(f"model output is not a JSON object: {short(content, 200)}")
    if "answers" in obj and "answers" not in fields and isinstance(obj["answers"], dict):
        obj = obj["answers"]
    answers = {}
    for name, spec in fields.items():
        if name not in obj:
            continue  # missing fields score 0, as for any engine
        value = obj[name]
        if isinstance(value, dict) and "value" in value:
            value = value["value"]
        answers[name] = {"type": spec["type"], "value": value}
    return answers


class OpenAIJsonEngine(Engine):
    name = "openai_json"

    def __init__(self, model: str | None = None, base_url: str = "https://api.openai.com/v1",
                 api_key_env: str = "OPENAI_API_KEY", temperature: float = 0,
                 max_tokens: int | None = None, timeout: float = 120.0, json_mode: bool = True,
                 attempts: int = 6, **options: Any) -> None:
        if not model:
            raise ValueError("openai_json needs --option model=<model id>")
        opts = dict(options)
        self.sleep = opts.pop("sleep", time.sleep)
        self.client, self._owned = make_client(opts, float(timeout))
        super().__init__(model=model, base_url=base_url, api_key_env=api_key_env,
                         temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                         json_mode=json_mode, attempts=attempts, **opts)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.env = (api_key_env,)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = float(timeout)
        self.json_mode = bool(json_mode)
        self.attempts = int(attempts)

    def payload(self, request: dict) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user_prompt(request)}],
            "temperature": self.temperature,
        }
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def __call__(self, request: dict) -> dict:
        key = os.environ.get(self.api_key_env)
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        r = send_with_retries(self.client, "POST", f"{self.base_url}/chat/completions",
                              json=self.payload(request), headers=headers, timeout=self.timeout,
                              attempts=self.attempts, sleep=self.sleep)
        body = json_or_none(r)
        if r.status_code >= 400:
            message = short((body or {}).get("error", r.text) if isinstance(body, dict) else r.text)
            if r.status_code in (400, 413) and _TOO_LONG_RE.search(message):
                raise Unsupported(message)
            raise EngineError(f"HTTP {r.status_code}: {message}")
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (TypeError, KeyError, IndexError):
            raise EngineError(f"malformed completion: {short(r.text)}") from None
        if choice.get("finish_reason") == "length":
            raise EngineError("completion hit max_tokens (truncated output)")
        out: dict[str, Any] = {"answers": parse_output(request["fields"], content), "raw": content}
        if isinstance(body.get("usage"), dict):
            out["usage"] = {k: v for k, v in body["usage"].items() if isinstance(v, (int, float))}
        return out

    def info(self) -> dict:
        return {"name": self.name, "system": "two", "model": self.model,
                "endpoint": f"{self.base_url}/chat/completions", "json_mode": self.json_mode,
                "temperature": self.temperature, "max_tokens": self.max_tokens,
                "system_prompt": SYSTEM_PROMPT}

    def close(self) -> None:
        if self._owned:
            self.client.close()
