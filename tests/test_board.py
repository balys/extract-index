import json

import pytest

from kit_fixture import make_suite
from extract_index.board import BoardError, build_board, write_board
from extract_index.engines.null import NullEngine
from extract_index.runner import run
from extract_index.scoring import score_run


@pytest.fixture()
def setup(tmp_path):
    suite = make_suite(tmp_path / "suite")
    run(NullEngine(), suite, tmp_path / "runs" / "null")
    scores = score_run(suite, tmp_path / "runs" / "null")
    (tmp_path / "runs" / "null" / "scores.json").write_text(json.dumps(scores))
    subs = tmp_path / "submissions"
    subs.mkdir()
    return suite, subs, scores


def entry(**over):
    e = {"name": "Null", "org": "Turion AI", "kind": "open", "system": "one",
         "scores": "../runs/null/scores.json", "hardware": "CPU",
         "links": {"model": "https://example.org/null", "results": "https://example.org/r", "submission": ""},
         "date": "2026-10-24", "notes": "floor"}
    e.update(over)
    return e


def write_entries(subs, entries):
    path = subs / "entries.json"
    path.write_text(json.dumps(entries))
    return path


def test_board_from_manifest_and_scores(setup, tmp_path):
    suite, subs, scores = setup
    board = build_board(write_entries(subs, [entry()]), suite / "manifest.json")
    assert list(board) == ["edition", "generated_utc", "areas", "tests", "entries"]
    assert board["edition"] == "0.1" and board["areas"] == ["Spans", "Documents", "Numbers", "Entities"]
    assert [t["name"] for t in board["tests"]] == ["squad2", "cuad", "cord", "docs", "drop", "tatqa", "fewnerd"]
    docs = next(t for t in board["tests"] if t["name"] == "docs")
    assert docs == {"name": "docs", "title": "DOCS (fixture)", "area": "Documents",
                    "description": "Fixture rows for docs.", "requests": 2, "fields": 10,
                    "types": ["text", "number", "date", "time", "datetime", "duration", "list"],
                    "null_share": 0.2, "metric": "token F1", "license": "CC BY 4.0",
                    "source_url": "https://example.org/docs"}
    e = board["entries"][0]
    assert list(e) == ["id", "name", "org", "kind", "system", "index", "areas", "tests", "types", "null",
                       "latency_ms", "rows", "hardware", "links", "date", "notes"]
    assert e["id"] == "turion-ai-null"
    assert e["rows"] == {k: v for k, v in scores["rows"].items() if k != "ignored"}
    assert e["index"] == scores["index"] and e["tests"]["docs"] == scores["tests"]["docs"]["score"]
    assert e["areas"] == scores["areas"] and e["types"] == scores["types"]
    assert e["null"] == {"precision": scores["null"]["precision"], "recall": scores["null"]["recall"]}
    assert e["latency_ms"] == scores["latency_ms"]

    out = tmp_path / "space" / "data" / "board.json"
    write_board(board, out)
    text = out.read_text()
    assert json.loads(text) == board and text.startswith('{\n "edition"')


def test_board_sorts_ranked_entries_first(setup):
    suite, subs, scores = setup
    better = dict(scores, index=99.0)
    (subs / "better.json").write_text(json.dumps(better))
    entries = [entry(name="Ref", system="two", kind="api"), entry(name="Null"),
               entry(name="Better", scores="better.json")]
    board = build_board(write_entries(subs, entries), suite / "manifest.json")
    assert [e["name"] for e in board["entries"]] == ["Better", "Null", "Ref"]


def test_board_refuses_other_suite(setup, tmp_path):
    suite, subs, _ = setup
    other = make_suite(tmp_path / "other", only=["docs"])
    with pytest.raises(BoardError, match="not this manifest"):
        build_board(write_entries(subs, [entry()]), other / "manifest.json")


def test_board_refuses_incomplete_runs(setup):
    suite, subs, scores = setup
    (subs / "partial.json").write_text(json.dumps(dict(scores, complete=False)))
    with pytest.raises(BoardError, match="not complete"):
        build_board(write_entries(subs, [entry(scores="partial.json")]), suite / "manifest.json")


@pytest.mark.parametrize("bad, match", [
    ({"kind": "closed"}, "kind"), ({"system": "three"}, "system"), ({"org": ""}, "missing"),
    ({"scores": "ftp://x/scores.json"}, "https URL"),
])
def test_board_validates_entries(setup, bad, match):
    suite, subs, _ = setup
    with pytest.raises(BoardError, match=match):
        build_board(write_entries(subs, [entry(**bad)]), suite / "manifest.json")


def test_board_fetches_https_scores(setup, monkeypatch):
    import httpx

    suite, subs, scores = setup
    seen = []

    def fake_get(url, **kw):
        seen.append(url)
        return httpx.Response(200, json=scores, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    url = "https://huggingface.co/datasets/u/r/resolve/main/scores.json"
    board = build_board(write_entries(subs, [entry(scores=url)]), suite / "manifest.json")
    assert seen == [url] and board["entries"][0]["index"] == scores["index"]


def test_empty_entries(setup):
    suite, subs, _ = setup
    board = build_board(write_entries(subs, []), suite / "manifest.json")
    assert board["entries"] == [] and len(board["tests"]) == 7


def test_board_refuses_duplicate_ids_and_partial_suites(setup):
    suite, subs, _ = setup
    with pytest.raises(BoardError, match="duplicate entry ids"):
        build_board(write_entries(subs, [entry(), entry(notes="again")]), suite / "manifest.json")
    entries = write_entries(subs, [entry(), entry(name="Null", id="null-2")])
    assert [e["id"] for e in build_board(entries, suite / "manifest.json")["entries"]] == ["turion-ai-null", "null-2"]
    manifest = json.loads((suite / "manifest.json").read_text())
    (suite / "manifest.json").write_text(json.dumps(dict(manifest, partial=True)))
    with pytest.raises(BoardError, match="partial"):
        build_board(write_entries(subs, []), suite / "manifest.json")


def test_board_keeps_avatars_and_puts_baselines_last(setup):
    suite, subs, _ = setup
    entries = [entry(name="Floor", system="baseline"), entry(name="Ref", system="two", kind="api"),
               entry(name="Null", avatar="assets/orgs/turion-ai.webp")]
    board = build_board(write_entries(subs, entries), suite / "manifest.json")
    assert [(e["name"], e["system"]) for e in board["entries"]] == [("Null", "one"), ("Ref", "two"), ("Floor", "baseline")]
    assert board["entries"][0]["avatar"] == "assets/orgs/turion-ai.webp" and "avatar" not in board["entries"][1]
