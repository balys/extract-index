"""Engines: the base class, `Unsupported`, `load_engine`, CLI option parsing, and HTTP retries.

An engine takes one request (`{"state", "fields", "reference_date"?}`) and returns
`{"answers": {...}}`, optionally with `usage` and other keys the runner stores as `response`.
It raises `Unsupported(reason)` for a declared limit (the kit forbids truncation).
"""

from __future__ import annotations

import importlib
import json
import random
import time
from typing import Any, Callable, Iterable

import httpx

BUILTIN = {
    "null": "extract_index.engines.null:NullEngine",
    "http": "extract_index.engines.http:HttpEngine",
    "clairic": "extract_index.engines.clairic:ClairicEngine",
    "openai_json": "extract_index.engines.openai_json:OpenAIJsonEngine",
}

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529})


class Unsupported(Exception):
    """The engine declines this request because of a declared limit (e.g. input too long)."""


class EngineError(RuntimeError):
    """A failed call (HTTP error, malformed output). The runner records it as status `error`."""


class Engine:
    """Base class. Subclasses set `name` and `env` and implement `__call__`."""

    name: str = "engine"
    env: tuple[str, ...] = ()  # names of the environment variables the engine reads

    def __init__(self, **options: Any) -> None:
        self.options = options

    def __call__(self, request: dict) -> dict:
        raise NotImplementedError

    def info(self) -> dict:
        """Static facts about the engine for `environment.json` (model id, limits...)."""
        return {"name": self.name}

    def close(self) -> None:
        """Release resources (HTTP clients)."""

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def load_engine(spec: str, options: dict | None = None) -> Engine:
    """A built-in engine by name (`null`, `http`, `clairic`, `openai_json`) or `"module:Class"`."""
    target = BUILTIN.get(spec, spec)
    if ":" not in target:
        raise ValueError(f"unknown engine {spec!r}; use one of {sorted(BUILTIN)} or 'module:Class'")
    module_name, _, attr = target.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    engine = obj(**(options or {}))
    if not callable(engine):
        raise TypeError(f"{spec!r} did not produce a callable engine")
    engine.spec = spec
    return engine


def engine_spec(engine: Any) -> str:
    """The spec an engine was loaded from, or `module:Class` for one built directly."""
    spec = getattr(engine, "spec", None)
    if spec:
        return spec
    cls = type(engine)
    for name, target in BUILTIN.items():
        if target == f"{cls.__module__}:{cls.__qualname__}":
            return name
    return f"{cls.__module__}:{cls.__qualname__}"


def parse_option(item: str) -> tuple[str, Any]:
    """`k=v` from the CLI; `v` is parsed as JSON when it parses, else kept as a string."""
    key, sep, raw = item.partition("=")
    key = key.strip()
    if not sep or not key:
        raise ValueError(f"option {item!r} is not k=v")
    try:
        value: Any = json.loads(raw)
    except ValueError:
        value = raw
    return key, value


def parse_options(items: Iterable[str] | None) -> dict:
    return dict(parse_option(i) for i in items or ())


# ---------------------------------------------------------------- HTTP helpers

def make_client(options: dict, timeout: float) -> tuple[httpx.Client, bool]:
    """An httpx client from the `client` or `transport` option (tests), else a new one.

    Returns `(client, owned)`; close the client only if `owned`.
    """
    client = options.pop("client", None)
    transport = options.pop("transport", None)
    if client is not None:
        return client, False
    return httpx.Client(timeout=timeout, transport=transport), True


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter on top: base * 2^attempt, capped, plus up to 1 s."""
    return min(cap, base * (2 ** attempt)) + random.uniform(0, 1.0)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return min(60.0, max(0.0, float(value))) if value else None
    except ValueError:
        return None


def send_with_retries(client: httpx.Client, method: str, url: str, *, attempts: int = 6,
                      sleep: Callable[[float], None] = time.sleep, **kwargs: Any) -> httpx.Response:
    """Send a request, retrying network errors, 429 and 5xx with backoff.

    Returns the final response (which may still be an error status); raises `EngineError`
    when the last attempt failed at the network level.
    """
    last_exc: Exception | None = None
    response: httpx.Response | None = None
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as e:
            last_exc, response = e, None
        else:
            if response.status_code not in RETRY_STATUSES:
                return response
        if attempt + 1 < attempts:
            delay = _retry_after(response) if response is not None else None
            sleep(delay if delay is not None else backoff_delay(attempt))
    if response is not None:
        return response
    raise EngineError(f"network error after {attempts} attempts: {type(last_exc).__name__}: {last_exc}")


def json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def short(text: Any, limit: int = 300) -> str:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"
