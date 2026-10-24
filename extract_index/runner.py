"""Run an engine over suite rows, one request at a time, appending to `results.jsonl`.

A rerun into the same directory skips rows whose last result is `ok` or `unsupported` and retries
`error` rows. `environment.json` records the engine, redacted options, kit and git versions, and
the suite's manifest hash; a resume with a different suite or engine spec is refused.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from . import EDITION, __version__
from .engines import Engine, Unsupported, engine_spec, load_engine
from .scoring import last_by_id, read_results
from .suite.common import read_jsonl_gz, sha256_file

SECRET_WORDS = ("key", "token", "secret", "password")
REDACTED = "***"


class RunMismatch(RuntimeError):
    """The run directory belongs to a different suite or engine."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def _secret_name(name: Any) -> bool:
    return any(w in str(name).lower() for w in SECRET_WORDS)


def redact(options: Any) -> Any:
    """Options with any value whose name contains key/token/secret/password replaced by ***.

    Numbers, booleans and nulls under such names (`max_tokens`, `context_tokens`) are settings,
    not secrets, and are kept.
    """
    if isinstance(options, dict):
        return {k: (redact(v) if not _secret_name(k) or v is None or isinstance(v, (int, float, bool))
                    else REDACTED)
                for k, v in options.items()}
    if isinstance(options, (list, tuple)):
        return [redact(v) for v in options]
    if isinstance(options, (str, int, float, bool)) or options is None:
        return options
    return repr(options)


def git_info() -> dict:
    """Commit and dirty flag of the kit's checkout, or nulls outside a git checkout."""
    root = Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, timeout=10, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                                text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit or None, "dirty": bool(status.strip())}


def environment(engine: Any, spec: str, options: dict, suite_sha256: str) -> dict:
    info = engine.info() if hasattr(engine, "info") else {}
    env_names = tuple(getattr(engine, "env", ()) or ())
    return {
        "engine": {"name": getattr(engine, "name", spec), "spec": spec, "info": redact(info)},
        "options": redact(options),
        "env": {n: ("set" if os.environ.get(n) else "unset") for n in env_names},
        "kit_version": __version__,
        "edition": EDITION,
        "git": git_info(),
        "suite_sha256": suite_sha256,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "started_utc": utc_now(),
    }


def iter_rows(suite_dir: Path, manifest: dict, tests: list[str] | None,
              limit: int | None) -> Iterator[dict]:
    """Suite rows in manifest order; `limit` keeps the first N rows of each test."""
    names = list(manifest["tests"])
    if tests:
        unknown = [t for t in tests if t not in manifest["tests"]]
        if unknown:
            raise ValueError(f"tests not in the suite: {unknown}; the suite has {names}")
        names = [t for t in names if t in tests]
    for name in names:
        rows = read_jsonl_gz(suite_dir / manifest["tests"][name]["file"])
        yield from rows if limit is None else rows[:limit]


def call_engine(engine: Any, row: dict, spec: str, compact: bool) -> dict:
    """One timed engine call turned into a result row."""
    started = utc_now()
    response: Any = None
    error: str | None = None
    t0 = time.perf_counter()
    try:
        response = engine(row["request"])
        wall_ms = (time.perf_counter() - t0) * 1000.0
        if isinstance(response, dict) and isinstance(response.get("answers"), dict):
            status = "ok"
        else:
            status, error = "error", "malformed response: no answers object"
    except Unsupported as e:
        wall_ms = (time.perf_counter() - t0) * 1000.0
        status, error = "unsupported", _short_error(e, with_type=False)
    except Exception as e:  # noqa: BLE001 - any engine failure is recorded, not raised
        wall_ms = (time.perf_counter() - t0) * 1000.0
        status, error = "error", _short_error(e)

    out: dict[str, Any] = {"id": row["id"], "test": row["test"], "status": status,
                           "answers": response["answers"] if status == "ok" else None,
                           "wall_ms": round(wall_ms, 3), "engine": spec}
    if error is not None:
        out["error"] = error
    out["started_utc"] = started
    if isinstance(response, dict) and isinstance(response.get("usage"), dict):
        out["usage"] = response["usage"]
    if not compact and response is not None:
        out["response"] = response
    return out


def _short_error(e: BaseException, with_type: bool = True, limit: int = 300) -> str:
    text = " ".join(str(e).split()) or type(e).__name__
    if with_type:
        text = f"{type(e).__name__}: {text}"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _check_resume(env_path: Path, spec: str, suite_sha: str) -> dict | None:
    if not env_path.exists():
        return None
    old = json.loads(env_path.read_text())
    if old.get("suite_sha256") != suite_sha:
        raise RunMismatch(f"{env_path.parent} was run on a different suite "
                          f"({str(old.get('suite_sha256'))[:12]}… != {suite_sha[:12]}…); use a new --out")
    old_spec = (old.get("engine") or {}).get("spec")
    if old_spec != spec:
        raise RunMismatch(f"{env_path.parent} was run with engine {old_spec!r}, not {spec!r}; use a new --out")
    return old


def run(engine: Engine | str, suite_dir: str | Path, out_dir: str | Path, tests: list[str] | None = None,
        limit: int | None = None, compact: bool = False, options: dict | None = None,
        progress_every: int = 25) -> dict:
    """Run `engine` (an Engine, or a spec loaded with `options`) over the suite; returns counts."""
    suite = Path(suite_dir)
    out = Path(out_dir)
    manifest_path = suite / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    suite_sha = sha256_file(manifest_path)

    owned = isinstance(engine, str)
    spec = engine if isinstance(engine, str) else engine_spec(engine)
    out.mkdir(parents=True, exist_ok=True)
    env_path = out / "environment.json"
    old_env = _check_resume(env_path, spec, suite_sha)
    rows = list(iter_rows(suite, manifest, tests, limit))  # validates `tests` before any call

    if owned:
        engine = load_engine(spec, dict(options or {}))
    if options is None:
        options = dict(getattr(engine, "options", {}) or {})
    try:
        env = environment(engine, spec, options, suite_sha)
        if old_env:
            env["started_utc"] = old_env.get("started_utc", env["started_utc"])
            env["resumed_utc"] = list(old_env.get("resumed_utc", [])) + [utc_now()]
        env_path.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n")
        return _loop(engine, spec, rows, out / "results.jsonl", compact, progress_every)
    finally:
        if owned:
            engine.close()


def _loop(engine: Any, spec: str, rows: list[dict], results_path: Path, compact: bool,
          progress_every: int) -> dict:
    last = last_by_id(read_results(results_path))
    todo = [r for r in rows if (last.get(r["id"]) or {}).get("status") not in ("ok", "unsupported")]
    counts = {"rows": len(rows), "skipped": len(rows) - len(todo), "ok": 0, "unsupported": 0, "error": 0}
    _progress(f"{len(rows)} rows, {counts['skipped']} already done, {len(todo)} to run")
    every = max(1, progress_every)
    _end_partial_line(results_path)
    with open(results_path, "a", encoding="utf-8") as f:
        for i, row in enumerate(todo, 1):
            result = call_engine(engine, row, spec, compact)
            f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            f.flush()
            counts[result["status"]] += 1
            if i % every == 0 or i == len(todo):
                _progress(f"{i}/{len(todo)} {row['test']} ok={counts['ok']} "
                          f"unsupported={counts['unsupported']} error={counts['error']}")
    return counts


def _end_partial_line(path: Path) -> None:
    """After a crash mid-write, end the partial last line so new rows start on their own line."""
    if not path.exists() or path.stat().st_size == 0:
        return
    with open(path, "rb") as f:
        f.seek(-1, 2)
        last = f.read(1)
    if last != b"\n":
        with open(path, "ab") as f:
            f.write(b"\n")


def _progress(message: str) -> None:
    print(f"[run] {message}", file=sys.stderr, flush=True)
