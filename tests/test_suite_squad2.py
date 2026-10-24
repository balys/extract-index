import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, squad2

FIXTURE = Path(__file__).parent / "fixtures" / "squad2" / "source.json"


def records() -> list[dict]:
    """The fixture's paragraphs expanded into `load_source` records (one per question)."""
    data = json.loads(FIXTURE.read_text())
    return [{"id": q["id"], "title": p["title"], "context": p["context"], "question": q["question"],
             "answers": q["answers"]} for p in data["paragraphs"] for q in p["qas"]]


def by_title(rows: list[dict]) -> dict[str, dict]:
    return {r["meta"]["title"]: r for r in rows}


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(squad2, key), str) and getattr(squad2, key)
    assert squad2.NAME == "squad2" and squad2.AREA == "Spans" and squad2.LICENSE == "CC BY-SA 4.0"
    assert len(squad2.REVISION) == 40


def test_rows_are_valid():
    rows = squad2.convert(records())
    assert len(rows) == 3
    assert [r["id"] for r in rows] == [f"squad2-{i:05d}" for i in range(3)]
    for row in rows:
        assert validate_row(row, test="squad2") == []
        assert {"source", "split", "source_id", "license"} <= set(row["meta"])
        assert row["meta"]["source"] == "rajpurkar/squad_v2" and row["meta"]["split"] == "validation"


def test_deterministic():
    assert json.dumps(squad2.convert(records())) == json.dumps(squad2.convert(records()))


def test_limit_is_a_prefix():
    full = squad2.convert(records())
    assert squad2.convert(records(), limit=2) == full[:2]
    assert squad2.convert(records(), limit=0) == []


def test_fields_follow_source_order_with_gold_forms():
    recs = records()
    row = by_title(squad2.convert(recs))["Normans"]
    source = [r for r in recs if r["title"] == "Normans"]
    assert row["request"]["state"] == source[0]["context"]
    assert list(row["request"]["fields"]) == [f"q{i:02d}" for i in range(1, len(source) + 1)]
    for (name, spec), r in zip(row["request"]["fields"].items(), source):
        assert spec == {"type": "text", "instructions": " ".join(r["question"].split())}
        gold = row["gold"][name]
        answers = list(dict.fromkeys(a.strip() for a in r["answers"]))
        if not answers:
            assert gold == {"value": None}
        else:
            assert gold["value"] == answers[0]
            assert gold.get("alternatives", []) == answers[1:]
        assert row["meta"]["question_ids"][name] == r["id"]


def test_has_both_answerable_and_unanswerable():
    gold = [g for row in squad2.convert(records()) for g in row["gold"].values()]
    assert any(g["value"] is None for g in gold) and any(g["value"] is not None for g in gold)


def test_repeated_questions_are_merged_or_dropped():
    rows = by_title(squad2.convert(records()))
    steam = [s["instructions"].lower() for s in rows["Steam_engine"]["request"]["fields"].values()]
    # "Who designed Salamanca?" is asked twice, once answerable and once not: dropped.
    assert "who designed salamanca?" not in steam
    assert "what type of locomotive was salamanca?" in steam
    assert len(steam) == 8  # 10 source questions, both copies of the conflicting one dropped
    rhine = rows["Rhine"]
    asked = [s["instructions"].lower() for s in rhine["request"]["fields"].values()]
    assert asked.count("how long is the rhine?") == 1  # two answerable copies: merged
    name = next(n for n, s in rhine["request"]["fields"].items() if s["instructions"].lower() == "how long is the rhine?")
    gold = rhine["gold"][name]
    assert {gold["value"], *gold.get("alternatives", [])} == {"1,230 km (760 mi)", "1,230 km"}
    assert isinstance(rhine["meta"]["question_ids"][name], list)


@pytest.mark.network
def test_build_from_hub():
    rows = squad2.build(limit=5)
    assert [r["id"] for r in rows] == [f"squad2-{i:05d}" for i in range(5)]
    assert all(validate_row(r, test="squad2") == [] for r in rows)
