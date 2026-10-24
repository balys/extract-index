"""Per-field metrics and the `scores.json` aggregate (per test, area, type, null, latency, usage).

`score_field` gives one field a score in [0, 1]; `score_run` scores a run's `results.jsonl`
against a suite directory and returns the `scores.json` dict described in SPEC.md.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import re
import statistics
import string
from pathlib import Path
from typing import Any, Iterable

from . import EDITION, __version__
from .schema import WrongForm, answer_value, normalise
from .suite import TESTS
from .suite.common import read_jsonl_gz, sha256_file

TYPE_ORDER = ["text", "number", "date", "time", "datetime", "duration", "list"]
TEXT_ITEM_MATCH = 0.5  # list text items match at token F1 >= 0.5 (and then count as 1)


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Any = _Missing()  # the field has no answer (missing, or the request was not answered)


# ---------------------------------------------------------------- text

_ARTICLES_RE = re.compile(r"\b(a|an|the)\b")
_PUNCT = set(string.punctuation)


def normalize_answer(s: str) -> str:
    """SQuAD's normalisation: lowercase, strip punctuation, drop a/an/the, collapse whitespace."""
    s = s.lower()
    s = "".join(ch for ch in s if ch not in _PUNCT)
    s = _ARTICLES_RE.sub(" ", s)
    return " ".join(s.split())


def token_f1(pred: str, gold: str) -> float:
    """SQuAD token F1. When either side normalises to no tokens: 1 if both are empty, else 0."""
    p, g = normalize_answer(pred).split(), normalize_answer(gold).split()
    if not p or not g:
        return float(p == g)
    common = collections.Counter(p) & collections.Counter(g)
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision, recall = same / len(p), same / len(g)
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------- scalars

def numbers_match(answer: float, gold: float, decimals: int | None) -> bool:
    if decimals is not None:
        return abs(answer - gold) <= 0.5 * 10 ** (-decimals) + 1e-9
    return abs(answer - gold) <= 1e-6 * max(1.0, abs(gold))


def _hms(t: str) -> tuple[str, str]:
    return t[:5], (t[6:8] if len(t) > 5 else "00")


def scalar_score(t: str, spec: dict, gold: Any, answer: Any) -> float:
    """Score of a normalised non-null `answer` against one canonical non-null `gold` value."""
    if answer is None or gold is None:
        return 0.0
    if t == "text":
        return token_f1(answer, gold)
    if t in ("number", "duration"):
        return float(numbers_match(float(answer), float(gold), spec.get("decimals")))
    if t == "date":
        return float(answer == gold)
    if t == "time":
        g_hm, g_s = _hms(gold)
        a_hm, a_s = _hms(answer)
        return float(a_hm == g_hm and (len(gold) <= 5 or a_s == g_s))
    if t == "datetime":
        return float(answer[:16] == gold[:16])
    return 0.0


def item_matches(item_type: str, spec: dict, gold_forms: list, answer: Any) -> bool:
    """Whether one answer item matches a gold item given all its accepted forms."""
    if answer is None:
        return False
    if item_type == "text":
        return any(token_f1(answer, g) >= TEXT_ITEM_MATCH for g in gold_forms)
    return any(scalar_score(item_type, spec, g, answer) == 1.0 for g in gold_forms)


def max_matching(n_left: int, edges: list[list[int]]) -> int:
    """Size of a maximum bipartite matching (Kuhn's augmenting paths); `edges[i]` = right nodes."""
    match_right: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in match_right or augment(match_right[j], seen):
                match_right[j] = i
                return True
        return False

    return sum(augment(i, set()) for i in range(n_left))


def list_f1(spec: dict, gold_items: list[list], answer_items: list) -> float:
    """Multiset F1 between answer items and gold items (each gold item = its accepted forms)."""
    if not gold_items and not answer_items:
        return 1.0
    if not gold_items or not answer_items:
        return 0.0
    item_type = spec["items"]
    edges = [[j for j, forms in enumerate(gold_items) if item_matches(item_type, spec, forms, a)]
             for a in answer_items]
    matched = max_matching(len(answer_items), edges)
    if matched == 0:
        return 0.0
    precision, recall = matched / len(answer_items), matched / len(gold_items)
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------- fields

def _gold_candidates(spec: dict, gold: dict) -> list[Any]:
    """Gold value and alternatives; for lists each candidate is a list of per-item form lists."""
    values = [gold["value"]] + list(gold.get("alternatives") or [])
    if spec["type"] != "list":
        return values
    item_alts = gold.get("item_alternatives") or []
    out = []
    for k, v in enumerate(values):
        items = list(v or [])
        if k == 0:
            out.append([[x] + list(item_alts[i] if i < len(item_alts) else []) for i, x in enumerate(items)])
        else:
            out.append([[x] for x in items])
    return out


def is_null(value: Any) -> bool:
    return value is None or value == []


def answered_value(spec: dict, answer: Any) -> Any:
    """The normalised value of an answer object; raise `WrongForm` if unanswered or malformed."""
    if answer is MISSING:
        raise WrongForm("missing answer")
    return normalise(spec, answer_value(answer))


def score_field(spec: dict, gold: dict, answer: Any = MISSING) -> float:
    """Score in [0, 1] of one answer object (or `MISSING`) against its gold entry."""
    try:
        value = answered_value(spec, answer)
    except WrongForm:
        return 0.0
    if gold["value"] is None:
        return float(is_null(value))
    if value is None:
        return 0.0
    t = spec["type"]
    candidates = _gold_candidates(spec, gold)
    if t == "list":
        return max(list_f1(spec, c, value) for c in candidates)
    return max(scalar_score(t, spec, g, value) for g in candidates)


# ---------------------------------------------------------------- runs

def read_results(path: str | Path) -> list[dict]:
    """Result rows of a `results.jsonl`, skipping blank or partial lines."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                rows.append(row)
    return rows


def last_by_id(rows: Iterable[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        out[row["id"]] = row
    return out


def _pct(x: float) -> float:
    return round(100.0 * x, 2)


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (as numpy's default), `q` in [0, 100]."""
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def latency_summary(wall_ms: list[float]) -> dict:
    if not wall_ms:
        return {"median": None, "mean": None, "p80": None}
    return {"median": round(statistics.median(wall_ms), 1), "mean": round(statistics.fmean(wall_ms), 1),
            "p80": round(percentile(wall_ms, 80), 1)}


def _add_usage(total: dict, usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for k, v in usage.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total[k] = total.get(k, 0) + v


def _p_null(answer: Any) -> float | None:
    p = answer.get("p_null") if isinstance(answer, dict) else None
    if isinstance(p, (int, float)) and not isinstance(p, bool) and 0.0 <= p <= 1.0:
        return float(p)
    return None


class _Tally:
    """Running sums for one run: fields per test and type, nulls, Brier, latency, usage."""

    def __init__(self) -> None:
        self.test_sum: dict[str, float] = collections.defaultdict(float)
        self.test_n: dict[str, int] = collections.defaultdict(int)
        self.type_sum: dict[str, float] = collections.defaultdict(float)
        self.type_n: dict[str, int] = collections.defaultdict(int)
        self.null_tp = self.null_pred = self.null_gold = 0
        self.brier_sum, self.brier_n, self.fields = 0.0, 0, 0
        self.wall_ms: list[float] = []
        self.usage: dict[str, float] = {}

    def add_field(self, test: str, spec: dict, gold: dict, answer: Any) -> None:
        s = score_field(spec, gold, answer)
        t = spec["type"]
        self.test_sum[test] += s
        self.test_n[test] += 1
        self.type_sum[t] += s
        self.type_n[t] += 1
        self.fields += 1
        gold_null = gold["value"] is None
        self.null_gold += gold_null
        try:
            pred_null = is_null(answered_value(spec, answer))
        except WrongForm:
            return
        self.null_pred += pred_null
        self.null_tp += pred_null and gold_null
        p = _p_null(answer)
        if p is not None:
            self.brier_sum += (p - float(gold_null)) ** 2
            self.brier_n += 1

    def null_metrics(self) -> dict:
        precision = _ratio(self.null_tp, self.null_pred)
        recall = _ratio(self.null_tp, self.null_gold)
        f1 = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and precision + recall > 0 else
              (0.0 if precision is not None and recall is not None else None))
        brier = _ratio(self.brier_sum, self.brier_n)
        return {
            "precision": None if precision is None else _pct(precision),
            "recall": None if recall is None else _pct(recall),
            "f1": None if f1 is None else _pct(f1),
            "brier": None if brier is None else round(brier, 4),
            "p_null_coverage": round(self.brier_n / self.fields, 4) if self.fields else 0.0,
        }


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _engine_name(results: list[dict], run_dir: Path) -> str | None:
    for row in reversed(results):
        if row.get("engine"):
            return str(row["engine"])
    env_path = run_dir / "environment.json"
    if env_path.exists():
        env = json.loads(env_path.read_text())
        engine = env.get("engine")
        return (engine.get("spec") or engine.get("name")) if isinstance(engine, dict) else engine
    return None


def score_run(suite_dir: str | Path, results_path: str | Path) -> dict:
    """Score a run (`results.jsonl`, or the run directory holding it) against a suite directory."""
    suite = Path(suite_dir)
    results_path = Path(results_path)
    if results_path.is_dir():
        results_path = results_path / "results.jsonl"
    manifest_path = suite / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    results = read_results(results_path)
    last = last_by_id(results)

    tally = _Tally()
    seen: set[str] = set()
    tests_out: dict[str, dict] = {}
    rows_out = {"total": 0, "ok": 0, "unsupported": 0, "error": 0, "missing": 0}
    for name, entry in manifest["tests"].items():
        counts = {"ok": 0, "unsupported": 0, "error": 0, "missing": 0}
        rows = read_jsonl_gz(suite / entry["file"])
        for row in rows:
            seen.add(row["id"])
            result = last.get(row["id"])
            status = result.get("status") if result else None
            status = status if status in ("ok", "unsupported", "error") else "missing"
            counts[status] += 1
            answers = (result.get("answers") if status == "ok" else None) or {}
            if not isinstance(answers, dict):
                answers = {}
            if status == "ok" and isinstance(result.get("wall_ms"), (int, float)):
                tally.wall_ms.append(float(result["wall_ms"]))
            if result:
                _add_usage(tally.usage, result.get("usage"))
            for fname, spec in row["request"]["fields"].items():
                tally.add_field(name, spec, row["gold"][fname], answers.get(fname, MISSING))
        n = tally.test_n[name]
        tests_out[name] = {"score": _pct(tally.test_sum[name] / n) if n else 0.0,
                           "requests": len(rows), "fields": n, **counts}
        rows_out["total"] += len(rows)
        for k, v in counts.items():
            rows_out[k] += v
    rows_out["ignored"] = sum(1 for rid in last if rid not in seen)

    raw_test = {t: tally.test_sum[t] / tally.test_n[t] for t in tests_out if tally.test_n[t]}
    areas: dict[str, float] = {}
    for area in manifest.get("areas", []):
        members = [raw_test[t] for t, e in manifest["tests"].items() if e.get("area") == area and t in raw_test]
        if members:
            areas[area] = _pct(sum(members) / len(members))
    index = (_pct(sum(raw_test[t] for t in TESTS) / len(TESTS))
             if all(t in raw_test for t in TESTS) else None)
    types = {t: _pct(tally.type_sum[t] / tally.type_n[t]) for t in TYPE_ORDER if tally.type_n.get(t)}
    types.update({t: _pct(tally.type_sum[t] / tally.type_n[t]) for t in tally.type_n if t not in types})

    return {
        "edition": manifest.get("edition", EDITION),
        "kit_version": __version__,
        "suite_sha256": sha256_file(manifest_path),
        "engine": _engine_name(results, results_path.parent),
        "complete": rows_out["total"] > 0 and rows_out["ok"] + rows_out["unsupported"] == rows_out["total"],
        "rows": rows_out,
        "index": index,
        "areas": areas,
        "tests": tests_out,
        "types": types,
        "null": tally.null_metrics(),
        "latency_ms": latency_summary(tally.wall_ms),
        "usage": tally.usage,
        "generated_utc": _utc_now(),
    }
