import json

import httpx
import pytest

from extract_index.engines import (Engine, EngineError, Unsupported, backoff_delay, load_engine, parse_option,
                                   parse_options, send_with_retries)
from extract_index.engines.clairic import ClairicEngine
from extract_index.engines.http import HttpEngine
from extract_index.engines.null import NullEngine
from extract_index.engines.openai_json import OpenAIJsonEngine, parse_output, user_prompt
from extract_index.schema import validate_response

REQUEST = {"state": "Invoice INV-2291, total $1,080.50.",
           "fields": {"invoice_number": {"type": "text"}, "total": {"type": "number", "decimals": 2},
                      "contacts": {"type": "list", "items": "text"}},
           "reference_date": "2026-09-02"}
ANSWERS = {"invoice_number": {"type": "text", "value": "INV-2291", "p_null": 0.0},
           "total": {"type": "number", "value": 1080.5},
           "contacts": {"type": "list", "value": []}}
ACCOUNT = "acct0123456789abcdef0123456789ab"


class Recorder:
    """A MockTransport handler that replays `responses` in order and records the requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def transport(self):
        return httpx.MockTransport(self)

    def body(self, i=-1):
        return json.loads(self.requests[i].content)


def no_sleep(_):
    pass


# ---------------------------------------------------------------- base, loading, options

def test_null_engine():
    out = NullEngine()(REQUEST)
    assert out == {"answers": {n: {"type": s["type"], "value": None, "p_null": 1.0}
                               for n, s in REQUEST["fields"].items()}}
    assert validate_response(REQUEST["fields"], out) == []


def test_load_engine_builtins_and_module_class():
    e = load_engine("null", {})
    assert isinstance(e, NullEngine) and e.spec == "null"
    e = load_engine("extract_index.engines.null:NullEngine", {"x": 1})
    assert isinstance(e, NullEngine) and e.options == {"x": 1}
    assert isinstance(load_engine("http", {"base_url": "http://h"}), HttpEngine)
    with pytest.raises(ValueError, match="unknown engine"):
        load_engine("nope", {})
    with pytest.raises(ModuleNotFoundError):
        load_engine("no_such_module:Engine", {})


def test_base_engine():
    e = Engine(a=1)
    assert e.options == {"a": 1} and e.info() == {"name": "engine"} and e.env == ()
    with pytest.raises(NotImplementedError):
        e({})
    with Engine() as ctx:
        assert isinstance(ctx, Engine)


@pytest.mark.parametrize("item, want", [
    ("timeout=30", ("timeout", 30)), ("json_mode=false", ("json_mode", False)),
    ("model=gpt-4o-mini", ("model", "gpt-4o-mini")), ("t=0.5", ("t", 0.5)),
    ("x=null", ("x", None)), ('o={"a": [1]}', ("o", {"a": [1]})), ("u=http://h:8000/x", ("u", "http://h:8000/x")),
    ("s=", ("s", "")), ("eq=a=b", ("eq", "a=b")),
])
def test_parse_option(item, want):
    assert parse_option(item) == want


def test_parse_options_rejects_bad_items():
    assert parse_options(["a=1", "b=two"]) == {"a": 1, "b": "two"}
    with pytest.raises(ValueError):
        parse_option("novalue")
    with pytest.raises(ValueError):
        parse_option("=1")


def test_backoff_grows_and_caps():
    assert 1 <= backoff_delay(0) <= 2 and 8 <= backoff_delay(3) <= 9 and backoff_delay(20) <= 31


def test_send_with_retries_honours_retry_after_and_gives_up():
    waits = []
    rec = Recorder(httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(503), httpx.Response(503))
    with httpx.Client(transport=rec.transport()) as c:
        r = send_with_retries(c, "GET", "http://x/", attempts=3, sleep=waits.append)
    assert r.status_code == 503 and len(rec.requests) == 3
    assert waits[0] == 3.0 and len(waits) == 2

    rec = Recorder(httpx.ConnectError("down"), httpx.ConnectError("down"))
    with httpx.Client(transport=rec.transport()) as c:
        with pytest.raises(EngineError, match="network error after 2 attempts"):
            send_with_retries(c, "GET", "http://x/", attempts=2, sleep=no_sleep)


# ---------------------------------------------------------------- http

def test_http_success_and_bearer(monkeypatch):
    monkeypatch.setenv("EXTRACT_INDEX_API_KEY", "k-1")
    rec = Recorder(httpx.Response(200, json={"answers": ANSWERS, "usage": {"input_tokens": 3}}))
    e = HttpEngine(base_url="http://model:8000/", transport=rec.transport(), sleep=no_sleep)
    assert e(REQUEST)["answers"] == ANSWERS
    req = rec.requests[0]
    assert req.method == "POST" and str(req.url) == "http://model:8000/v1/extract"
    assert req.headers["authorization"] == "Bearer k-1" and rec.body() == REQUEST
    assert e.env == ("EXTRACT_INDEX_API_KEY",) and "transport" not in e.options


def test_http_without_key_sends_no_auth(monkeypatch):
    monkeypatch.delenv("EXTRACT_INDEX_API_KEY", raising=False)
    rec = Recorder(httpx.Response(200, json={"answers": ANSWERS}))
    HttpEngine(transport=rec.transport())(REQUEST)
    assert "authorization" not in rec.requests[0].headers


def test_http_retries_429_and_network_errors():
    rec = Recorder(httpx.Response(429), httpx.ConnectError("refused"), httpx.Response(502),
                   httpx.Response(200, json={"answers": ANSWERS}))
    e = HttpEngine(transport=rec.transport(), sleep=no_sleep)
    assert e(REQUEST)["answers"] == ANSWERS and len(rec.requests) == 4


@pytest.mark.parametrize("response", [
    httpx.Response(413, text="too big"),
    httpx.Response(400, json={"error": {"code": "unsupported", "message": "state over 32k tokens"}}),
    httpx.Response(422, json={"error": "Unsupported: field type forecast"}),
])
def test_http_unsupported(response):
    with pytest.raises(Unsupported):
        HttpEngine(transport=Recorder(response).transport(), sleep=no_sleep)(REQUEST)


@pytest.mark.parametrize("response, match", [
    (httpx.Response(400, json={"error": "bad field"}), "HTTP 400: bad field"),
    (httpx.Response(500, text="oops"), "HTTP 500"),
    (httpx.Response(200, json={"result": {}}), "malformed"),
    (httpx.Response(200, text="not json"), "malformed"),
])
def test_http_errors(response, match):
    e = HttpEngine(transport=Recorder(*[response] * 6).transport(), sleep=no_sleep)
    with pytest.raises(EngineError, match=match):
        e(REQUEST)


# ---------------------------------------------------------------- clairic

def cf_ok(result):
    return httpx.Response(200, json={"result": result, "success": True, "errors": [], "messages": []})


def cf_err(status, message, code=3030):
    return httpx.Response(status, json={"errors": [{"message": message, "code": code}], "success": False,
                                        "result": {}, "messages": []})


RESULT = {"model": "clairic", "answers": ANSWERS, "truncated": False,
          "usage": {"state_tokens": 10, "schema_tokens": 40, "input_tokens": 60, "output_tokens": 0, "passes": 1}}


@pytest.fixture()
def cf_env(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)


def test_clairic_success_unwraps_result(cf_env):
    rec = Recorder(cf_ok(RESULT))
    e = ClairicEngine(transport=rec.transport(), sleep=no_sleep)
    out = e(REQUEST)
    assert out == RESULT and out["usage"]["input_tokens"] == 60
    req = rec.requests[0]
    assert str(req.url) == f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/@cf/cloudflare/clairic"
    assert req.headers["authorization"] == "Bearer cf-token"
    assert rec.body() == {"model": "clairic", "state": REQUEST["state"], "fields": REQUEST["fields"],
                          "reference_date": "2026-09-02"}


def test_clairic_body_without_reference_date(cf_env):
    rec = Recorder(cf_ok(RESULT))
    ClairicEngine(transport=rec.transport())({"state": "x", "fields": {"a": {"type": "text"}}})
    assert "reference_date" not in rec.body()


def test_clairic_retries_429_then_succeeds(cf_env):
    waits = []
    rec = Recorder(cf_err(429, "rate limited", 3040), httpx.Response(503, text="busy"),
                   httpx.ReadTimeout("slow"), cf_ok(RESULT))
    out = ClairicEngine(transport=rec.transport(), sleep=waits.append)(REQUEST)
    assert out["answers"] == ANSWERS and len(rec.requests) == 4 and len(waits) == 3


def test_clairic_gives_up_after_attempts(cf_env):
    rec = Recorder(*[cf_err(500, "internal")] * 6)
    with pytest.raises(EngineError, match="HTTP 500"):
        ClairicEngine(transport=rec.transport(), sleep=no_sleep)(REQUEST)
    assert len(rec.requests) == 6


@pytest.mark.parametrize("status, message", [
    (400, "AiError: AiError: input is too long: 70123 tokens exceed the 65536-token context"),
    (422, "AiError: AiError: context length exceeded"),
    (400, "Maximum context of 65536 tokens"),
    (400, "AiError: state of 70123 tokens exceeds the maximum context"),
    (422, "AiError: 70123 tokens exceed 65536"),
])
def test_clairic_too_long_is_unsupported(cf_env, status, message):
    with pytest.raises(Unsupported):
        ClairicEngine(transport=Recorder(cf_err(status, message)).transport(), sleep=no_sleep)(REQUEST)


def test_clairic_413_is_unsupported(cf_env):
    with pytest.raises(Unsupported):
        ClairicEngine(transport=Recorder(httpx.Response(413, text="body too large")).transport())(REQUEST)


@pytest.mark.parametrize("response, match", [
    (cf_err(422, "AiError: AiError: invalid field name 'xxx' (abc)"), "HTTP 422: 3030: AiError: AiError: invalid"),
    (cf_err(400, "bad request"), "HTTP 400: 3030: bad request"),
    (cf_err(400, "daily free allocation exceeded", 4006), "HTTP 400: 4006: daily"),
    (cf_err(401, "Authentication error", 10000), "HTTP 401"),
    (httpx.Response(200, json={"success": False, "errors": [{"code": 1, "message": "nope"}]}), "API error: 1: nope"),
    (cf_ok({"model": "clairic"}), "malformed result"),
    (cf_ok({**RESULT, "truncated": True}), "truncated"),
])
def test_clairic_errors(cf_env, response, match):
    with pytest.raises(EngineError, match=match):
        ClairicEngine(transport=Recorder(response).transport(), sleep=no_sleep)(REQUEST)


def test_clairic_discovers_single_account(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    accounts = httpx.Response(200, json={"result": [{"id": ACCOUNT, "name": "Owner"}], "success": True,
                                         "errors": [], "messages": []})
    rec = Recorder(accounts, cf_ok(RESULT), cf_ok(RESULT))
    e = ClairicEngine(transport=rec.transport(), sleep=no_sleep)
    e(REQUEST)
    e(REQUEST)
    assert [r.method for r in rec.requests] == ["GET", "POST", "POST"]  # looked up once
    assert str(rec.requests[0].url) == "https://api.cloudflare.com/client/v4/accounts"
    assert ACCOUNT in str(rec.requests[1].url)
    err = capsys.readouterr().err
    assert "discovered" in err and ACCOUNT not in err
    assert ACCOUNT not in json.dumps(e.info())


@pytest.mark.parametrize("result", [[], [{"id": "a"}, {"id": "b"}]])
def test_clairic_discovery_needs_exactly_one_account(monkeypatch, result):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    rec = Recorder(httpx.Response(200, json={"result": result, "success": True}))
    with pytest.raises(EngineError, match="set CLOUDFLARE_ACCOUNT_ID"):
        ClairicEngine(transport=rec.transport())(REQUEST)


def test_clairic_needs_token(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    with pytest.raises(EngineError, match="CLOUDFLARE_API_TOKEN is not set"):
        ClairicEngine(transport=Recorder().transport())(REQUEST)


def test_clairic_info_and_options(cf_env):
    e = ClairicEngine(timeout=30, model="@cf/cloudflare/clairic-next", transport=Recorder().transport())
    info = e.info()
    assert info["model"] == "@cf/cloudflare/clairic-next" and "{account_id}" in info["endpoint"]
    assert info["limits"] == {"context_tokens": 65536, "pass_tokens": 8192}
    assert e.env == ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    assert e.options == {"timeout": 30, "model": "@cf/cloudflare/clairic-next", "attempts": 6}
    with load_engine("clairic", {}) as default:
        assert default.timeout == 120.0


# ---------------------------------------------------------------- openai_json

def completion(content, finish="stop", usage=None):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content},
                                                  "finish_reason": finish}],
                                     "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20,
                                                        "prompt_tokens_details": {"cached_tokens": 0}}})


FIELDS = REQUEST["fields"]


@pytest.mark.parametrize("content", [
    '{"invoice_number": "INV-2291", "total": 1080.5, "contacts": []}',
    '```json\n{"invoice_number": "INV-2291", "total": 1080.5, "contacts": []}\n```',
    'Here you go: {"invoice_number": "INV-2291", "total": 1080.5, "contacts": []} Done.',
    '{"answers": {"invoice_number": "INV-2291", "total": 1080.5, "contacts": []}}',
    '{"invoice_number": {"value": "INV-2291"}, "total": 1080.5, "contacts": []}',
])
def test_parse_output_forms(content):
    assert parse_output(FIELDS, content) == {"invoice_number": {"type": "text", "value": "INV-2291"},
                                             "total": {"type": "number", "value": 1080.5},
                                             "contacts": {"type": "list", "value": []}}


def test_parse_output_missing_and_extra_fields():
    assert parse_output(FIELDS, '{"total": null, "other": 1}') == {"total": {"type": "number", "value": None}}


@pytest.mark.parametrize("content", ["", "no json here", "[1, 2]", "{broken"])
def test_parse_output_unparseable(content):
    with pytest.raises(EngineError):
        parse_output(FIELDS, content)


def test_openai_json_call(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-test")
    rec = Recorder(completion('{"invoice_number": "INV-2291", "total": "1,080.50", "contacts": null}'))
    e = OpenAIJsonEngine(model="m1", base_url="http://llm/v1/", api_key_env="MY_KEY", max_tokens=500,
                         transport=rec.transport(), sleep=no_sleep)
    out = e(REQUEST)
    assert out["answers"]["total"] == {"type": "number", "value": "1,080.50"}
    assert out["usage"] == {"prompt_tokens": 100, "completion_tokens": 20}
    assert validate_response(FIELDS, out) == []
    req = rec.requests[0]
    assert str(req.url) == "http://llm/v1/chat/completions" and req.headers["authorization"] == "Bearer sk-test"
    body = rec.body()
    assert body["model"] == "m1" and body["temperature"] == 0 and body["max_tokens"] == 500
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and body["messages"][1]["content"] == user_prompt(REQUEST)
    assert "Reference date: 2026-09-02" in body["messages"][1]["content"]
    assert e.env == ("MY_KEY",) and e.info()["system"] == "two"


def test_openai_json_mode_off_and_retry():
    rec = Recorder(httpx.Response(429), completion('{"invoice_number": null}'))
    e = OpenAIJsonEngine(model="m1", json_mode=False, transport=rec.transport(), sleep=no_sleep)
    assert e(REQUEST)["answers"] == {"invoice_number": {"type": "text", "value": None}}
    assert "response_format" not in rec.body() and "max_tokens" not in rec.body()


@pytest.mark.parametrize("response, exc", [
    (completion("I cannot help"), EngineError),
    (completion('{"total": 1', finish="length"), EngineError),
    (httpx.Response(200, json={"choices": []}), EngineError),
    (httpx.Response(401, json={"error": {"message": "bad key"}}), EngineError),
    (httpx.Response(400, json={"error": {"code": "context_length_exceeded", "message": "too many"}}), Unsupported),
])
def test_openai_json_failures(response, exc):
    e = OpenAIJsonEngine(model="m1", transport=Recorder(response).transport(), sleep=no_sleep)
    with pytest.raises(exc):
        e(REQUEST)


def test_openai_json_needs_model():
    with pytest.raises(ValueError, match="model"):
        OpenAIJsonEngine()
