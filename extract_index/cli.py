"""Command line: `python -m extract_index <command>`.

suite build|download|verify|sample, run, score, pipeline, upload, board.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import EDITION, __version__

DEFAULT_SUITE = f"suite-{EDITION}"
SUITE_REPO = "balys/extract-index-suite"


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


# ---------------------------------------------------------------- suite

def cmd_suite_build(args: argparse.Namespace) -> int:
    from .suite import build_suite

    manifest = build_suite(args.out, only=_csv(args.tests), limit=args.limit)
    print(f"{manifest['totals']['requests']} requests, {manifest['totals']['fields']} fields -> {args.out}")
    return 0


def cmd_suite_download(args: argparse.Namespace) -> int:
    from huggingface_hub import snapshot_download

    path = snapshot_download(repo_id=args.repo, repo_type="dataset", revision=args.revision,
                             local_dir=args.out)
    print(f"downloaded {args.repo}@{args.revision} -> {path}")
    return cmd_suite_verify(argparse.Namespace(dir=args.out))


def verify_suite(suite_dir: str | Path) -> list[str]:
    """Problems with a built suite: file hashes, row validity, counts against the manifest."""
    from .schema import validate_row
    from .suite import summarise
    from .suite.common import read_jsonl_gz, sha256_file

    suite = Path(suite_dir)
    manifest_path = suite / "manifest.json"
    if not manifest_path.exists():
        return [f"{manifest_path} not found"]
    manifest = json.loads(manifest_path.read_text())
    problems: list[str] = []
    totals = {"requests": 0, "fields": 0}
    for name, entry in manifest.get("tests", {}).items():
        path = suite / entry["file"]
        if not path.exists():
            problems.append(f"{name}: {path} not found")
            continue
        if sha256_file(path) != entry.get("sha256"):
            problems.append(f"{name}: sha256 of {path.name} does not match the manifest")
        rows = read_jsonl_gz(path)
        bad = [p for row in rows for p in validate_row(row, test=name)]
        problems += [f"{name}: {p}" for p in bad[:20]]
        if len(bad) > 20:
            problems.append(f"{name}: ... {len(bad) - 20} more row problems")
        ids = [r.get("id") for r in rows]
        if len(set(ids)) != len(ids):
            problems.append(f"{name}: duplicate row ids")
        if not bad:
            got = summarise(rows)
            for key in ("requests", "fields", "types", "null_share"):
                if got[key] != entry.get(key):
                    problems.append(f"{name}: {key} is {got[key]!r}, manifest says {entry.get(key)!r}")
            totals["requests"] += got["requests"]
            totals["fields"] += got["fields"]
    if not problems and manifest.get("totals") != totals:
        problems.append(f"totals are {totals}, manifest says {manifest.get('totals')}")
    return problems


def cmd_suite_verify(args: argparse.Namespace) -> int:
    problems = verify_suite(args.dir)
    manifest_path = Path(args.dir) / "manifest.json"
    if manifest_path.exists():
        from .suite.common import sha256_file

        manifest = json.loads(manifest_path.read_text())
        print(f"suite {args.dir}: edition {manifest.get('edition')}, tests {list(manifest.get('tests', {}))}, "
              f"manifest sha256 {sha256_file(manifest_path)}")
        if manifest.get("partial"):
            print("note: this is a partial build (--limit); it must not be published or submitted")
    for p in problems:
        print(f"problem: {p}")
    print("ok" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


def cmd_suite_sample(args: argparse.Namespace) -> int:
    from .suite.common import read_jsonl_gz

    manifest = json.loads((Path(args.dir) / "manifest.json").read_text())
    if args.test not in manifest["tests"]:
        print(f"test {args.test!r} is not in the suite; it has {list(manifest['tests'])}", file=sys.stderr)
        return 2
    rows = read_jsonl_gz(Path(args.dir) / manifest["tests"][args.test]["file"])
    for row in rows[: args.n]:
        print(json.dumps(row, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- run and score

def cmd_run(args: argparse.Namespace) -> int:
    from .engines import parse_options
    from .runner import RunMismatch, run

    try:
        options = parse_options(args.option)
        counts = run(args.engine, args.suite, args.out, tests=_csv(args.tests), limit=args.limit,
                     compact=args.compact, options=options)
    except (RunMismatch, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"run {args.out}: {counts['ok']} ok, {counts['unsupported']} unsupported, {counts['error']} error, "
          f"{counts['skipped']} skipped (already done)")
    return 0


def format_scores(s: dict) -> str:
    """A plain-text table of a `scores.json`."""
    def num(v: object, digits: int = 2) -> str:
        return "-" if v is None else f"{v:.{digits}f}" if isinstance(v, float) else str(v)

    lines = [f"engine {s.get('engine')}  edition {s.get('edition')}  complete {s.get('complete')}",
             "", f"{'test':<10} {'score':>7} {'requests':>8} {'fields':>7} {'ok':>6} {'unsup':>6} "
                 f"{'error':>6} {'missing':>7}"]
    for name, t in s["tests"].items():
        lines.append(f"{name:<10} {num(t['score']):>7} {t['requests']:>8} {t['fields']:>7} {t['ok']:>6} "
                     f"{t['unsupported']:>6} {t['error']:>6} {t['missing']:>7}")
    lines += ["", f"{'index':<10} {num(s['index']):>7}"]
    lines += [f"{'area':<10} " + "  ".join(f"{a} {num(v)}" for a, v in s["areas"].items())]
    lines += [f"{'types':<10} " + "  ".join(f"{t} {num(v)}" for t, v in s["types"].items())]
    n = s["null"]
    lines.append(f"{'null':<10} precision {num(n['precision'])}  recall {num(n['recall'])}  f1 {num(n['f1'])}  "
                 f"brier {num(n['brier'], 4)}  p_null coverage {num(n['p_null_coverage'], 4)}")
    lat = s["latency_ms"]
    lines.append(f"{'latency':<10} median {num(lat['median'])} ms  mean {num(lat['mean'])} ms  "
                 f"p80 {num(lat['p80'])} ms")
    r = s["rows"]
    lines.append(f"{'rows':<10} " + "  ".join(f"{k} {v}" for k, v in r.items()))
    if s.get("usage"):
        lines.append(f"{'usage':<10} " + "  ".join(f"{k} {v:,}" for k, v in s["usage"].items()))
    return "\n".join(lines)


def cmd_score(args: argparse.Namespace) -> int:
    from .scoring import score_run

    run_dir = Path(args.run)
    results = run_dir / "results.jsonl"
    if not results.exists():
        print(f"error: {results} not found", file=sys.stderr)
        return 1
    scores = score_run(args.suite, results)
    (run_dir / "scores.json").write_text(json.dumps(scores, indent=2, ensure_ascii=False) + "\n")
    print(format_scores(scores))
    if scores["rows"].get("ignored"):
        print(f"note: {scores['rows']['ignored']} result ids are not in the suite and were ignored")
    print(f"-> {run_dir / 'scores.json'}")
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    code = cmd_run(args)
    if code:
        return code
    return cmd_score(argparse.Namespace(run=args.out, suite=args.suite))


# ---------------------------------------------------------------- publish

def run_readme(repo: str, scores: dict, environment: dict) -> str:
    engine = (environment.get("engine") or {}).get("spec", scores.get("engine"))
    tests = "\n".join(f"| {t} | {v['score']:.2f} | {v['ok']} | {v['unsupported']} | {v['error']} | {v['missing']} |"
                      for t, v in scores["tests"].items())
    index = "-" if scores.get("index") is None else f"{scores['index']:.2f}"
    git = environment.get("git") or {}
    return f"""---
pretty_name: Extract Index run {repo.split('/')[-1]}
tags: [extract-index, benchmark-results]
---

# Extract Index {scores.get('edition')} run: `{engine}`

Results of one run of the [SystemOne Extract Index](https://huggingface.co/spaces/balys/extract-index)
kit ({scores.get('kit_version')}, commit `{git.get('commit')}`{' (dirty)' if git.get('dirty') else ''}).

- Suite manifest sha256: `{scores.get('suite_sha256')}`
- Complete: {scores.get('complete')}
- Index: {index}

| test | score | ok | unsupported | error | missing |
|---|---|---|---|---|---|
{tests}

Files: `results.jsonl` (one row per request), `scores.json` (from `python -m extract_index score`),
`environment.json` (engine, redacted options, versions).
"""


def cmd_upload(args: argparse.Namespace) -> int:
    from huggingface_hub import CommitOperationAdd, HfApi

    run_dir = Path(args.run)
    names = ("results.jsonl", "scores.json", "environment.json")
    missing = [n for n in names if not (run_dir / n).exists()]
    if missing:
        print(f"error: {run_dir} lacks {missing}; run `score` first", file=sys.stderr)
        return 1
    scores = json.loads((run_dir / "scores.json").read_text())
    env = json.loads((run_dir / "environment.json").read_text())
    if not scores.get("complete"):
        print("warning: this run is not complete; it cannot be submitted as is", file=sys.stderr)
    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=not args.public, exist_ok=True)
    ops = [CommitOperationAdd(path_in_repo=n, path_or_fileobj=str(run_dir / n)) for n in names]
    ops.append(CommitOperationAdd(path_in_repo="README.md",
                                  path_or_fileobj=run_readme(args.repo, scores, env).encode("utf-8")))
    api.create_commit(repo_id=args.repo, repo_type="dataset", operations=ops,
                      commit_message=f"Extract Index {scores.get('edition')} run")
    print(f"uploaded to https://huggingface.co/datasets/{args.repo} ({'public' if args.public else 'private'})")
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    from .board import BoardError, build_board, write_board

    try:
        board = build_board(args.entries, args.manifest)
    except BoardError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    write_board(board, args.out)
    print(f"{len(board['entries'])} entries, {len(board['tests'])} tests -> {args.out}")
    return 0


# ---------------------------------------------------------------- parser

def _run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", required=True, help="null | http | clairic | openai_json | module:Class")
    p.add_argument("--option", action="append", default=[], metavar="K=V",
                   help="engine option (value parsed as JSON when possible); repeatable")
    p.add_argument("--out", required=True, help="run directory, e.g. runs/<name>")
    p.add_argument("--tests", help="comma-separated tests (default: all in the suite)")
    p.add_argument("--limit", type=int, help="first N rows of each test")
    p.add_argument("--compact", action="store_true", help="do not store full engine responses")
    p.add_argument("--suite", default=DEFAULT_SUITE)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="extract_index", description="SystemOne Extract Index kit")
    ap.add_argument("--version", action="version", version=f"extract-index {__version__} (edition {EDITION})")
    sub = ap.add_subparsers(dest="command", required=True)

    suite = sub.add_parser("suite", help="build, download, verify or sample the suite")
    ss = suite.add_subparsers(dest="suite_command", required=True)
    p = ss.add_parser("build", help="build the suite from its sources")
    p.add_argument("--out", default=DEFAULT_SUITE)
    p.add_argument("--tests", help="comma-separated tests (default: all)")
    p.add_argument("--limit", type=int, help="at most N rows per test (marks the build partial)")
    p.set_defaults(func=cmd_suite_build)
    p = ss.add_parser("download", help="download the frozen suite from the Hub")
    p.add_argument("--repo", default=SUITE_REPO)
    p.add_argument("--revision", default="main")
    p.add_argument("--out", default=DEFAULT_SUITE)
    p.set_defaults(func=cmd_suite_download)
    p = ss.add_parser("verify", help="check hashes, rows and counts against the manifest")
    p.add_argument("--dir", default=DEFAULT_SUITE)
    p.set_defaults(func=cmd_suite_verify)
    p = ss.add_parser("sample", help="print a few rows of one test")
    p.add_argument("--test", required=True)
    p.add_argument("--n", type=int, default=2)
    p.add_argument("--dir", default=DEFAULT_SUITE)
    p.set_defaults(func=cmd_suite_sample)

    p = sub.add_parser("run", help="run an engine over the suite (resumable)")
    _run_args(p)
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("score", help="score a run directory -> scores.json")
    p.add_argument("--run", required=True)
    p.add_argument("--suite", default=DEFAULT_SUITE)
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("pipeline", help="run, then score")
    _run_args(p)
    p.set_defaults(func=cmd_pipeline)
    p = sub.add_parser("upload", help="upload a run's results to a Hub dataset repo")
    p.add_argument("--run", required=True)
    p.add_argument("--repo", required=True, help="<user>/<name>")
    p.add_argument("--public", action="store_true", help="make the repo public (default private)")
    p.set_defaults(func=cmd_upload)
    p = sub.add_parser("board", help="build space/data/board.json from the submissions")
    p.add_argument("--entries", default="submissions/entries.json")
    p.add_argument("--manifest", default=f"{DEFAULT_SUITE}/manifest.json")
    p.add_argument("--out", default="space/data/board.json")
    p.set_defaults(func=cmd_board)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
