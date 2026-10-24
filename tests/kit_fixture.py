"""A tiny synthetic suite for the kit tests (scoring, runner, engines, board, CLI).

`make_suite(dir)` builds it through the real `build_suite`, with fake builder modules standing in
for `extract_index.suite.<test>`, so the manifest has exactly the shape a real build writes.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from extract_index.engines import Engine
from extract_index.suite import TESTS, build_suite
from extract_index.suite.common import make_row, read_jsonl_gz

AREA = {"squad2": "Spans", "cuad": "Spans", "cord": "Documents", "docs": "Documents",
        "drop": "Numbers", "tatqa": "Numbers", "fewnerd": "Entities"}


def _meta(test: str, i: int) -> dict:
    return {"source": f"fixture/{test}", "split": "test", "source_id": f"{test}-{i}", "license": "CC BY 4.0"}


def _g(value, **extra) -> dict:
    return {"value": value, **extra}


ROWS: dict[str, list[tuple[str, dict, dict]]] = {
    "squad2": [
        ("The Normans were in Normandy in the 10th century. Rollo led them.",
         {"where": {"type": "text"}, "king": {"type": "text"}, "leader": {"type": "text"}},
         {"where": _g("Normandy", alternatives=["in Normandy"]), "king": _g(None), "leader": _g("Rollo")}),
        ("Paris is the capital of France. It has 2.1 million people.",
         {"capital": {"type": "text"}, "mayor": {"type": "text"}},
         {"capital": _g("Paris"), "mayor": _g(None)}),
    ],
    "cuad": [
        ("This Agreement between Acme Corp and Beta LLC is governed by the laws of New York.",
         {"governing_law": {"type": "text"}, "parties": {"type": "list", "items": "text"},
          "non_compete": {"type": "text"}},
         {"governing_law": _g("the laws of New York"), "parties": _g(["Acme Corp", "Beta LLC"]),
          "non_compete": _g(None)}),
        ("Either party may end this Agreement with 30 days notice.",
         {"renewal": {"type": "text"}, "termination": {"type": "text"}},
         {"renewal": _g(None), "termination": _g("Either party may end this Agreement with 30 days notice")}),
    ],
    "cord": [
        ("NASI GORENG 25,000\nES TEH 5,000\nTOTAL 30,000\nCASH 50,000\nCHANGE 20,000",
         {"total": {"type": "number"}, "change": {"type": "number"}, "tax": {"type": "number"},
          "prices": {"type": "list", "items": "number"}},
         {"total": _g(30000), "change": _g(20000), "tax": _g(None), "prices": _g([25000, 5000])}),
    ],
    "docs": [
        ("Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. Total due $1,080.50. "
         "Contacts: Dana Ruiz, Priya Shah. Pickup 2026-09-05 at 14:30 for 3 days.",
         {"invoice_number": {"type": "text"}, "due_date": {"type": "date"},
          "total": {"type": "number", "decimals": 2, "unit": "USD"},
          "pickup_time": {"type": "time"}, "pickup_at": {"type": "datetime"},
          "rental": {"type": "duration", "unit": "days"},
          "contacts": {"type": "list", "items": "text"}, "po_number": {"type": "text"}},
         {"invoice_number": _g("INV-2291"), "due_date": _g("2026-10-02"), "total": _g(1080.5),
          "pickup_time": _g("14:30"), "pickup_at": _g("2026-09-05T14:30"), "rental": _g(3),
          "contacts": _g(["Dana Ruiz", "Priya Shah"]), "po_number": _g(None)}),
        ("Timesheet for week of 2026-10-05: shifts on 2026-10-05 and 2026-10-07.",
         {"shift_dates": {"type": "list", "items": "date"}, "approver": {"type": "text"}},
         {"shift_dates": _g(["2026-10-05", "2026-10-07"]), "approver": _g(None)}),
    ],
    "drop": [
        ("The war in Europe ended on 8 May 1945. The Allies and the Soviets took 3 cities.",
         {"cities": {"type": "number"}, "end": {"type": "date"}, "who": {"type": "list", "items": "text"}},
         {"cities": _g(3), "end": _g("1945-05-08"), "who": _g(["Allies", "Soviets"])}),
    ],
    "tatqa": [
        ("Revenue was 12.5 million in 2019 and 10.0 million in 2018, mostly from Cloud.",
         {"revenue_2019": {"type": "number", "decimals": 1}, "segment": {"type": "text"},
          "years": {"type": "list", "items": "number"}},
         {"revenue_2019": _g(12.5), "segment": _g("Cloud"), "years": _g([2019, 2018])}),
    ],
    "fewnerd": [
        ("Dana Ruiz joined Acme Corp after leaving Beta LLC.",
         {"person": {"type": "list", "items": "text"}, "organization": {"type": "list", "items": "text"},
          "location": {"type": "list", "items": "text"}},
         {"person": _g(["Dana Ruiz"]), "organization": _g(["Acme Corp", "Beta LLC"]), "location": _g(None)}),
    ],
}


def fake_module(test: str) -> types.ModuleType:
    mod = types.ModuleType(f"extract_index.suite.{test}")
    mod.NAME = test
    mod.TITLE = f"{test.upper()} (fixture)"
    mod.AREA = AREA[test]
    mod.DESCRIPTION = f"Fixture rows for {test}."
    mod.METRIC = "token F1"
    mod.LICENSE = "CC BY 4.0"
    mod.SOURCE = f"fixture/{test}"
    mod.REVISION = "0" * 40
    mod.SPLIT = "test"
    mod.URL = f"https://example.org/{test}"

    def build(limit: int | None = None, _test: str = test) -> list[dict]:
        rows = [make_row(_test, i, state, fields, gold, _meta(_test, i))
                for i, (state, fields, gold) in enumerate(ROWS[_test])]
        return rows if limit is None else rows[:limit]

    mod.build = build
    return mod


def make_suite(out_dir: str | Path, only: list[str] | None = None) -> Path:
    """Build the fixture suite into `out_dir` (all 7 tests, or `only`); returns the directory."""
    saved = {t: sys.modules.get(f"extract_index.suite.{t}") for t in TESTS}
    try:
        for t in TESTS:
            sys.modules[f"extract_index.suite.{t}"] = fake_module(t)
        build_suite(out_dir, only=only)
    finally:
        for t, mod in saved.items():
            if mod is None:
                sys.modules.pop(f"extract_index.suite.{t}", None)
            else:
                sys.modules[f"extract_index.suite.{t}"] = mod
    return Path(out_dir)


def suite_rows(suite_dir: str | Path) -> list[dict]:
    suite = Path(suite_dir)
    manifest = json.loads((suite / "manifest.json").read_text())
    return [r for t in manifest["tests"].values() for r in read_jsonl_gz(suite / t["file"])]


class GoldEngine(Engine):
    """Answers every field with its gold value (looked up by state). Option `suite` = suite dir."""

    name = "gold"

    def __init__(self, suite: str = "", **options) -> None:
        super().__init__(suite=suite, **options)
        self.gold = {r["request"]["state"]: r["gold"] for r in suite_rows(suite)}

    def __call__(self, request: dict) -> dict:
        gold = self.gold[request["state"]]
        return {"answers": {n: {"type": s["type"], "value": gold[n]["value"]} for n, s in request["fields"].items()},
                "usage": {"input_tokens": 10}}
