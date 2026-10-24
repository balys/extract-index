"""Board data: `submissions/entries.json` + each entry's `scores.json` -> `space/data/board.json`.

The page renders only this file. Tests and areas come from the suite manifest; each entry's
scores are copied in from its `scores.json` (a path relative to the entries file, or an https
URL). Entries whose `suite_sha256` differs from the manifest's, or whose run is not complete,
are refused.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from . import EDITION
from .suite.common import sha256_file

KINDS = ("open", "api")
SYSTEMS = ("one", "two", "baseline")  # ranked, reference (generating), floor (e.g. null)
REQUIRED = ("name", "org", "kind", "system", "scores")


class BoardError(ValueError):
    """An entry cannot be put on the board."""


def board_test(name: str, entry: dict) -> dict:
    return {
        "name": name,
        "title": entry.get("title", name),
        "area": entry.get("area"),
        "description": entry.get("description"),
        "requests": entry.get("requests"),
        "fields": entry.get("fields"),
        "types": list(entry.get("types") or {}),
        "null_share": entry.get("null_share"),
        "metric": entry.get("metric"),
        "license": entry.get("license"),
        "source_url": entry.get("url"),
    }


def load_scores(ref: str, base: Path) -> dict:
    """A `scores.json` from a path (relative to `base`) or an https URL."""
    if ref.startswith("https://"):
        import httpx

        r = httpx.get(ref, follow_redirects=True, timeout=60)
        r.raise_for_status()
        return r.json()
    if "://" in ref:
        raise BoardError(f"scores must be a local path or an https URL, not {ref!r}")
    path = Path(ref)
    return json.loads((path if path.is_absolute() else base / path).read_text())


def entry_id(entry: dict) -> str:
    """A stable id for links: the entry's own `id`, else a slug of org and name."""
    if entry.get("id"):
        return str(entry["id"])
    return re.sub(r"[^a-z0-9]+", "-", f"{entry['org']} {entry['name']}".lower()).strip("-")


def board_entry(entry: dict, scores: dict) -> dict:
    """One board row: the entry's own fields with the scores copied in, in a readable order."""
    null = scores.get("null") or {}
    out: dict[str, Any] = {"id": entry_id(entry)}
    out.update({k: entry[k] for k in ("name", "org", "kind", "system")})
    out.update({
        "index": scores.get("index"),
        "areas": scores.get("areas", {}),
        "tests": {t: v.get("score") for t, v in (scores.get("tests") or {}).items()},
        "types": scores.get("types", {}),
        "null": {"precision": null.get("precision"), "recall": null.get("recall")},
        "latency_ms": scores.get("latency_ms", {}),
        "rows": {k: v for k, v in (scores.get("rows") or {}).items() if k != "ignored"},
    })
    for k in ("avatar", "hardware", "links", "date", "notes"):
        if k in entry:
            out[k] = entry[k]
    return out


def _check_entry(i: int, entry: Any) -> str:
    if not isinstance(entry, dict):
        raise BoardError(f"entry {i} is not an object")
    label = entry.get("name") or f"entry {i}"
    missing = [k for k in REQUIRED if not entry.get(k)]
    if missing:
        raise BoardError(f"{label}: missing {missing}")
    if entry["kind"] not in KINDS:
        raise BoardError(f"{label}: kind must be one of {KINDS}")
    if entry["system"] not in SYSTEMS:
        raise BoardError(f"{label}: system must be one of {SYSTEMS}")
    return label


def _sort_key(e: dict) -> tuple:
    index = e.get("index")
    return (SYSTEMS.index(e["system"]), index is None, -(index or 0.0), e["name"])


def build_board(entries_path: str | Path, manifest_path: str | Path) -> dict:
    """The board dict (SPEC "Board data") for the entries file and the suite manifest."""
    entries_path, manifest_path = Path(entries_path), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("partial"):
        raise BoardError(f"{manifest_path} is from a partial (--limit) build")
    suite_sha = sha256_file(manifest_path)
    tests = [board_test(name, t) for name, t in manifest["tests"].items()]
    present_areas = {t["area"] for t in tests}
    areas = [a for a in manifest.get("areas", []) if a in present_areas]

    entries = json.loads(entries_path.read_text())
    if not isinstance(entries, list):
        raise BoardError(f"{entries_path} must hold a JSON list")
    rows = []
    for i, entry in enumerate(entries):
        label = _check_entry(i, entry)
        scores = load_scores(str(entry["scores"]), entries_path.parent)
        if scores.get("suite_sha256") != suite_sha:
            raise BoardError(f"{label}: scores are for suite {str(scores.get('suite_sha256'))[:12]}…, "
                             f"not this manifest ({suite_sha[:12]}…)")
        if not scores.get("complete"):
            raise BoardError(f"{label}: the run is not complete (scores.json complete is false)")
        rows.append(board_entry(entry, scores))
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise BoardError(f"duplicate entry ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    rows.sort(key=_sort_key)

    return {
        "edition": manifest.get("edition", EDITION),
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "areas": areas,
        "tests": tests,
        "entries": rows,
    }


def write_board(board: dict, out_path: str | Path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
