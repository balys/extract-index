"""End to end through the CLI on the fixture suite: verify, sample, pipeline, score, board."""

import gzip
import json

from kit_fixture import make_suite
from extract_index.cli import main


def test_cli_end_to_end(tmp_path, capsys):
    suite = make_suite(tmp_path / "suite")
    capsys.readouterr()

    assert main(["suite", "verify", "--dir", str(suite)]) == 0
    assert capsys.readouterr().out.strip().endswith("ok")

    assert main(["suite", "sample", "--test", "docs", "--n", "1", "--dir", str(suite)]) == 0
    sample = json.loads(capsys.readouterr().out)
    assert sample["id"] == "docs-00000" and "gold" in sample

    run_dir = tmp_path / "runs" / "null"
    assert main(["pipeline", "--engine", "null", "--suite", str(suite), "--out", str(run_dir), "--compact"]) == 0
    out = capsys.readouterr().out
    assert "index" in out and "squad2" in out
    scores = json.loads((run_dir / "scores.json").read_text())
    assert scores["complete"] is True and scores["engine"] == "null" and scores["index"] is not None
    first = json.loads((run_dir / "results.jsonl").read_text().splitlines()[0])
    assert "response" not in first

    # A rerun skips everything; `score` rewrites scores.json with the same numbers.
    assert main(["run", "--engine", "null", "--suite", str(suite), "--out", str(run_dir)]) == 0
    assert "10 skipped" in capsys.readouterr().out
    assert main(["score", "--run", str(run_dir), "--suite", str(suite)]) == 0
    again = json.loads((run_dir / "scores.json").read_text())
    assert {k: v for k, v in again.items() if k != "generated_utc"} == \
           {k: v for k, v in scores.items() if k != "generated_utc"}

    # The gold engine scores 100 everywhere (a module:Class engine with an option).
    gold_dir = tmp_path / "runs" / "gold"
    assert main(["pipeline", "--engine", "kit_fixture:GoldEngine", "--option", f"suite={suite}",
                 "--suite", str(suite), "--out", str(gold_dir)]) == 0
    gold = json.loads((gold_dir / "scores.json").read_text())
    assert gold["index"] == 100.0 and gold["usage"] == {"input_tokens": 100}

    subs = tmp_path / "submissions"
    subs.mkdir()
    (subs / "entries.json").write_text(json.dumps([
        {"name": "Null", "org": "Turion AI", "kind": "open", "system": "one", "scores": "../runs/null/scores.json"},
        {"name": "Gold", "org": "Turion AI", "kind": "open", "system": "one", "scores": "../runs/gold/scores.json"},
    ]))
    board_path = tmp_path / "space" / "data" / "board.json"
    capsys.readouterr()
    assert main(["board", "--entries", str(subs / "entries.json"), "--manifest", str(suite / "manifest.json"),
                 "--out", str(board_path)]) == 0
    board = json.loads(board_path.read_text())
    assert [e["name"] for e in board["entries"]] == ["Gold", "Null"]
    assert board["entries"][0]["index"] == 100.0


def test_cli_verify_finds_problems(tmp_path, capsys):
    suite = make_suite(tmp_path / "suite")
    path = suite / "drop.jsonl.gz"
    rows = [json.loads(line) for line in gzip.open(path, "rt")]
    rows[0]["gold"]["cities"]["value"] = "three"
    with gzip.open(path, "wt") as f:
        f.write(json.dumps(rows[0]) + "\n")
    capsys.readouterr()
    assert main(["suite", "verify", "--dir", str(suite)]) == 1
    out = capsys.readouterr().out
    assert "sha256 of drop.jsonl.gz" in out and "not a canonical number" in out


def test_cli_run_refuses_other_engine(tmp_path, capsys):
    suite = make_suite(tmp_path / "suite", only=["drop"])
    run_dir = tmp_path / "run"
    assert main(["run", "--engine", "null", "--suite", str(suite), "--out", str(run_dir)]) == 0
    assert main(["run", "--engine", "http", "--suite", str(suite), "--out", str(run_dir)]) == 1
    assert "use a new --out" in capsys.readouterr().err


def test_cli_score_without_results(tmp_path, capsys):
    suite = make_suite(tmp_path / "suite", only=["drop"])
    assert main(["score", "--run", str(tmp_path / "nope"), "--suite", str(suite)]) == 1


def test_cli_upload_with_fake_hub(tmp_path, monkeypatch, capsys):
    import huggingface_hub

    calls = {}

    class FakeApi:
        def create_repo(self, repo_id, repo_type, private, exist_ok):
            calls["repo"] = (repo_id, repo_type, private, exist_ok)

        def create_commit(self, repo_id, repo_type, operations, commit_message):
            calls["files"] = sorted(op.path_in_repo for op in operations)
            readme = next(op for op in operations if op.path_in_repo == "README.md")
            calls["readme"] = readme.path_or_fileobj.read().decode() if hasattr(readme.path_or_fileobj, "read") \
                else bytes(readme.path_or_fileobj).decode()

    monkeypatch.setattr(huggingface_hub, "HfApi", FakeApi)
    suite = make_suite(tmp_path / "suite")
    run_dir = tmp_path / "runs" / "null"
    assert main(["run", "--engine", "null", "--suite", str(suite), "--out", str(run_dir)]) == 0
    assert main(["upload", "--run", str(run_dir), "--repo", "me/null-run"]) == 1  # no scores.json yet
    assert main(["score", "--run", str(run_dir), "--suite", str(suite)]) == 0
    assert main(["upload", "--run", str(run_dir), "--repo", "me/null-run"]) == 0
    assert calls["repo"] == ("me/null-run", "dataset", True, True)
    assert calls["files"] == ["README.md", "environment.json", "results.jsonl", "scores.json"]
    assert "Complete: True" in calls["readme"] and "| docs |" in calls["readme"]
    assert main(["upload", "--run", str(run_dir), "--repo", "me/null-run", "--public"]) == 0
    assert calls["repo"][2] is False


def test_cli_download_with_fake_hub(tmp_path, monkeypatch, capsys):
    import shutil

    import huggingface_hub

    built = make_suite(tmp_path / "built")
    seen = {}

    def fake_snapshot_download(repo_id, repo_type, revision, local_dir):
        seen.update(repo_id=repo_id, repo_type=repo_type, revision=revision)
        shutil.copytree(built, local_dir)
        return str(local_dir)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)
    out = tmp_path / "suite-0.1"
    assert main(["suite", "download", "--out", str(out), "--revision", "v0.1"]) == 0
    assert seen == {"repo_id": "balys/extract-index-suite", "repo_type": "dataset", "revision": "v0.1"}
    assert capsys.readouterr().out.strip().endswith("ok")
