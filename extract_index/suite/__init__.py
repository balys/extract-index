"""The suite: test registry and the build that writes `<test>.jsonl.gz` files plus `manifest.json`."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from .. import EDITION, __version__
from ..schema import validate_row
from .common import SEED, sha256_file, write_jsonl_gz

TESTS = ["squad2", "cuad", "cord", "docs", "drop", "tatqa", "fewnerd"]
AREAS = ["Spans", "Documents", "Numbers", "Entities"]
MODULE_KEYS = ("TITLE", "AREA", "DESCRIPTION", "METRIC", "LICENSE", "SOURCE", "REVISION", "SPLIT", "URL")
TYPE_ORDER = ["text", "number", "date", "time", "datetime", "duration", "list"]


def module(name: str) -> ModuleType:
    if name not in TESTS:
        raise KeyError(f"unknown test {name!r}; tests are {TESTS}")
    return importlib.import_module(f"{__name__}.{name}")


def summarise(rows: list[dict]) -> dict:
    """Counts the manifest (and the board) report for one test's rows."""
    types: dict[str, int] = {}
    fields = nulls = 0
    for row in rows:
        for name, spec in row["request"]["fields"].items():
            fields += 1
            types[spec["type"]] = types.get(spec["type"], 0) + 1
            nulls += row["gold"][name]["value"] is None
    ordered = {t: types[t] for t in TYPE_ORDER if t in types}
    return {"requests": len(rows), "fields": fields, "types": ordered,
            "null_share": round(nulls / fields, 4) if fields else 0.0}


def build_suite(out_dir: str | Path, only: list[str] | None = None, limit: int | None = None) -> dict:
    """Build the tests (all, or `only`) into `out_dir` and write `manifest.json`.

    With `only`, entries for other tests already in an existing manifest are kept. A build with
    `limit` is marked `partial` and must not be published.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    old = json.loads(manifest_path.read_text()) if (only and manifest_path.exists()) else {}
    tests: dict[str, dict] = {k: v for k, v in old.get("tests", {}).items() if k in TESTS}
    partial = bool(old.get("partial")) or limit is not None

    for name in only or TESTS:
        mod = module(name)
        rows = mod.build(limit=limit)
        problems = [p for row in rows for p in validate_row(row, test=name)]
        if problems:
            raise ValueError(f"{name}: {len(problems)} invalid rows, e.g. {problems[:5]}")
        ids = [r["id"] for r in rows]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{name}: duplicate row ids")
        path = out / f"{name}.jsonl.gz"
        write_jsonl_gz(path, rows)
        entry = {"file": path.name, **summarise(rows), "sha256": sha256_file(path)}
        entry.update({k.lower(): getattr(mod, k) for k in MODULE_KEYS})
        entry["name"] = name
        tests[name] = entry
        print(f"{name}: {entry['requests']} requests, {entry['fields']} fields -> {path}")

    ordered = {n: tests[n] for n in TESTS if n in tests}
    manifest = {
        "edition": EDITION,
        "kit_version": __version__,
        "seed": SEED,
        "partial": partial,
        "areas": AREAS,
        "order": list(ordered),
        "tests": ordered,
        "totals": {
            "requests": sum(t["requests"] for t in ordered.values()),
            "fields": sum(t["fields"] for t in ordered.values()),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False) + "\n")
    return manifest
