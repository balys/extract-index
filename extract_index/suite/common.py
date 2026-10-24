"""Shared helpers for the suite builders: rows, deterministic sampling, gzip JSONL, hashes."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

SEED = 20261024

T = TypeVar("T")


def rng(test: str) -> random.Random:
    """A generator seeded from the build seed and the test name (stable across Python runs)."""
    return random.Random(f"{SEED}:{test}")


def sample_sorted(items: Iterable[T], k: int, r: random.Random,
                  key: Callable[[T], Any] | None = None) -> list[T]:
    """Sort `items` by `key`, draw `k` of them with `r`, and return the draw in sorted order."""
    pool = sorted(items, key=key) if key else sorted(items)  # type: ignore[type-var]
    if k >= len(pool):
        return pool
    picked = sorted(r.sample(range(len(pool)), k))
    return [pool[i] for i in picked]


def dedupe(values: Iterable[T]) -> list[T]:
    """Drop repeats, keeping first occurrences in order."""
    seen: set = set()
    out: list[T] = []
    for v in values:
        marker = json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
        if marker not in seen:
            seen.add(marker)
            out.append(v)
    return out


def make_row(test: str, idx: int, state: str, fields: dict, gold: dict, meta: dict,
             reference_date: str | None = None) -> dict:
    request: dict[str, Any] = {"state": state, "fields": fields}
    if reference_date:
        request["reference_date"] = reference_date
    return {"id": f"{test}-{idx:05d}", "test": test, "request": request, "gold": gold, "meta": meta}


def write_jsonl_gz(path: str | Path, rows: Iterable[dict]) -> None:
    """Gzip JSONL with mtime=0 and sorted keys, so the same rows give the same bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
            for row in rows:
                gz.write((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def read_jsonl_gz(path: str | Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@contextlib.contextmanager
def temp_hf_cache(test: str) -> Iterator[str]:
    """A throwaway download cache, deleted on exit (the build machine is short on disk).

    Pass the yielded path as `cache_dir=` to `hf_hub_download` / `load_dataset`. The parent
    directory is `$EXTRACT_INDEX_TMP` if set, else the system temp directory.
    """
    base = os.environ.get("EXTRACT_INDEX_TMP") or tempfile.gettempdir()
    Path(base).mkdir(parents=True, exist_ok=True)
    path = tempfile.mkdtemp(prefix=f"extract-index-{test}-", dir=base)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def hf_file(repo_id: str, filename: str, revision: str, cache_dir: str) -> str:
    """Download one file of a Hub dataset at a pinned revision; returns the local path."""
    from huggingface_hub import hf_hub_download

    return hf_hub_download(repo_id=repo_id, filename=filename, repo_type="dataset",
                           revision=revision, cache_dir=cache_dir)


def take(rows: Sequence[T], limit: int | None) -> list[T]:
    return list(rows) if limit is None else list(rows[:limit])
