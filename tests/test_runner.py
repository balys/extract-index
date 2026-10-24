import json
import time

import pytest

from kit_fixture import make_suite, suite_rows
from extract_index.engines import Engine, Unsupported
from extract_index.engines.null import NullEngine
from extract_index.runner import RunMismatch, redact, run
from extract_index.scoring import read_results


class ScriptedEngine(Engine):
    """Errors on `fail` ids until `heal` is set, declines `decline` ids, else answers null."""

    name = "scripted"
    env = ("SCRIPTED_TOKEN", "SCRIPTED_UNSET_VAR")

    def __init__(self, fail=(), decline=(), delay=0.0, **options):
        super().__init__(**options)
        self.fail, self.decline, self.delay = set(fail), set(decline), delay
        self.heal = False
        self.calls: list[str] = []
        self.by_state = {}

    def __call__(self, request):
        rid = self.by_state[request["state"]]
        self.calls.append(rid)
        time.sleep(self.delay)
        if rid in self.decline:
            raise Unsupported("input too long")
        if rid in self.fail and not self.heal:
            raise RuntimeError("upstream exploded\nwith detail")
        return {"answers": {n: {"type": s["type"], "value": None} for n, s in request["fields"].items()},
                "usage": {"input_tokens": 7}, "debug": "full response"}


@pytest.fixture()
def suite(tmp_path):
    return make_suite(tmp_path / "suite")


def scripted(suite, **kw):
    e = ScriptedEngine(**kw)
    e.by_state = {r["request"]["state"]: r["id"] for r in suite_rows(suite)}
    return e


def test_run_writes_rows_in_manifest_order(suite, tmp_path):
    counts = run(NullEngine(), suite, tmp_path / "run")
    rows = read_results(tmp_path / "run" / "results.jsonl")
    assert [r["id"] for r in rows] == [r["id"] for r in suite_rows(suite)]
    assert counts == {"rows": 10, "skipped": 0, "ok": 10, "unsupported": 0, "error": 0}
    first = rows[0]
    assert list(first)[:6] == ["id", "test", "status", "answers", "wall_ms", "engine"]
    assert first["status"] == "ok" and first["engine"] == "null" and first["started_utc"].endswith("Z")
    assert "response" in first


def test_resume_skips_ok_and_unsupported_and_retries_errors(suite, tmp_path):
    out = tmp_path / "run"
    engine = scripted(suite, fail={"docs-00001", "cord-00000"}, decline={"cuad-00001"})
    first = run(engine, suite, out)
    assert first == {"rows": 10, "skipped": 0, "ok": 7, "unsupported": 1, "error": 2}
    rows = {r["id"]: r for r in read_results(out / "results.jsonl")}
    assert rows["docs-00001"]["status"] == "error"
    assert rows["docs-00001"]["error"] == "RuntimeError: upstream exploded with detail"
    assert rows["docs-00001"]["answers"] is None
    assert rows["cuad-00001"] == {**rows["cuad-00001"], "status": "unsupported", "error": "input too long"}

    engine.calls.clear()
    engine.heal = True
    second = run(engine, suite, out)
    assert sorted(engine.calls) == ["cord-00000", "docs-00001"]
    assert second == {"rows": 10, "skipped": 8, "ok": 2, "unsupported": 0, "error": 0}
    all_rows = read_results(out / "results.jsonl")
    assert len(all_rows) == 12
    last = {r["id"]: r for r in all_rows}
    assert all(r["status"] in ("ok", "unsupported") for r in last.values())

    engine.calls.clear()
    assert run(engine, suite, out)["skipped"] == 10 and engine.calls == []
    env = json.loads((out / "environment.json").read_text())
    assert len(env["resumed_utc"]) == 2


def test_latency_usage_and_compact(suite, tmp_path):
    engine = scripted(suite, delay=0.01)
    run(engine, suite, tmp_path / "full", tests=["drop"])
    run(engine, suite, tmp_path / "compact", tests=["drop"], compact=True)
    full = read_results(tmp_path / "full" / "results.jsonl")[0]
    compact = read_results(tmp_path / "compact" / "results.jsonl")[0]
    assert full["wall_ms"] >= 10.0 and compact["wall_ms"] >= 10.0
    assert full["usage"] == compact["usage"] == {"input_tokens": 7}
    assert full["response"]["debug"] == "full response"
    assert "response" not in compact


def test_tests_and_limit(suite, tmp_path):
    run(NullEngine(), suite, tmp_path / "run", tests=["docs", "squad2"], limit=1)
    ids = [r["id"] for r in read_results(tmp_path / "run" / "results.jsonl")]
    assert ids == ["squad2-00000", "docs-00000"]  # manifest order, first row of each
    with pytest.raises(ValueError, match="not in the suite"):
        run(NullEngine(), suite, tmp_path / "run2", tests=["nope"])


def test_malformed_response_is_an_error(suite, tmp_path):
    class Bad(Engine):
        def __call__(self, request):
            return {"answer": {}}

    run(Bad(), suite, tmp_path / "run", tests=["drop"])
    row = read_results(tmp_path / "run" / "results.jsonl")[0]
    assert row["status"] == "error" and "malformed" in row["error"]
    assert row["response"] == {"answer": {}}


def test_environment_redacts_secrets(suite, tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIPTED_TOKEN", "sekrit-env-value")
    monkeypatch.delenv("SCRIPTED_UNSET_VAR", raising=False)
    options = {"api_key": "sk-123", "Auth_Token": "t", "client_secret": "s", "db_password": "p",
               "model": "m1", "timeout": 30, "nested": {"apikey": "x", "keep": [1, 2]},
               "max_tokens": 512, "token": {"value": "deep"}}
    engine = scripted(suite, **options)
    run(engine, suite, tmp_path / "run", tests=["drop"], options=options)
    text = (tmp_path / "run" / "environment.json").read_text()
    env = json.loads(text)
    assert env["options"] == {"api_key": "***", "Auth_Token": "***", "client_secret": "***", "db_password": "***",
                              "model": "m1", "timeout": 30, "nested": {"apikey": "***", "keep": [1, 2]},
                              "max_tokens": 512, "token": "***"}
    assert env["env"] == {"SCRIPTED_TOKEN": "set", "SCRIPTED_UNSET_VAR": "unset"}
    for secret in ("sk-123", "sekrit-env-value", "deep"):
        assert secret not in text
    assert env["engine"]["spec"].endswith(":ScriptedEngine") and env["engine"]["name"] == "scripted"
    assert env["kit_version"] == "0.1.0" and len(env["suite_sha256"]) == 64
    assert set(env["git"]) == {"commit", "dirty"}
    assert env["python"] and env["platform"] and env["started_utc"].endswith("Z")
    assert redact({"x": object()})["x"].startswith("<object")


def test_engine_spec_string_with_options(suite, tmp_path):
    run("null", suite, tmp_path / "run", tests=["drop"], options={"token": "abc"})
    env = json.loads((tmp_path / "run" / "environment.json").read_text())
    assert env["engine"]["spec"] == "null" and env["options"] == {"token": "***"}


def test_refuses_resume_with_other_suite_or_engine(suite, tmp_path):
    out = tmp_path / "run"
    run(NullEngine(), suite, out, tests=["drop"])
    other = make_suite(tmp_path / "other", only=["drop", "docs"])
    with pytest.raises(RunMismatch, match="different suite"):
        run(NullEngine(), other, out, tests=["drop"])
    with pytest.raises(RunMismatch, match="engine"):
        run(scripted(suite), suite, out, tests=["drop"])
    assert len(read_results(out / "results.jsonl")) == 1


def test_resume_after_a_partial_last_line(suite, tmp_path):
    out = tmp_path / "run"
    run(NullEngine(), suite, out, tests=["drop", "tatqa"])
    path = out / "results.jsonl"
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n" + lines[1][:25])  # crash while writing the second row
    counts = run(NullEngine(), suite, out, tests=["drop", "tatqa"])
    assert counts["skipped"] == 1 and counts["ok"] == 1
    rows = read_results(path)
    assert [r["id"] for r in rows] == ["drop-00000", "tatqa-00000"]
