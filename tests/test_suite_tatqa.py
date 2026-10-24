import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, tatqa

FIXTURE = Path(__file__).parent / "fixtures" / "tatqa" / "source.json"


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text())["records"]


def clean(s: str) -> str:
    return " ".join(s.split())


def by_source(rows: list[dict]) -> dict[str, dict]:
    return {r["meta"]["source_id"]: r for r in rows}


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(tatqa, key), str) and getattr(tatqa, key)
    assert tatqa.NAME == "tatqa" and tatqa.AREA == "Numbers" and tatqa.LICENSE == "CC BY 4.0"
    assert tatqa.SOURCE == "next-tat/TAT-QA" and len(tatqa.REVISION) == 40


def test_rows_are_valid():
    rows = tatqa.convert(records())
    assert len(rows) == 4
    assert [r["id"] for r in rows] == [f"tatqa-{i:05d}" for i in range(4)]
    uids = [r["meta"]["source_id"] for r in rows]
    assert uids == sorted(uids)
    for row in rows:
        assert validate_row(row, test="tatqa") == []
        assert row["meta"]["source"] == tatqa.SOURCE and row["meta"]["split"] == "dev"
        assert row["meta"]["license"] == "CC BY 4.0"


def test_deterministic():
    assert json.dumps(tatqa.convert(records())) == json.dumps(tatqa.convert(records()))


def test_limit_is_a_prefix():
    full = tatqa.convert(records())
    assert tatqa.convert(records(), limit=2) == full[:2]
    assert tatqa.convert(records(), limit=0) == []


def test_state_is_table_then_paragraphs():
    doc = next(d for d in records() if d["table"]["uid"] == "f6368ece2c45f8080d07ccc5817d2431")
    state = by_source(tatqa.convert(records()))[doc["table"]["uid"]]["request"]["state"]
    table, *paragraphs = state.split("\n\n")
    assert table.splitlines() == [
        "|  | Years Ended December 31, |  | Change |  |",
        "|  | 2019 | 2018 | $ | % |",
        "|  |  | (dollars in thousands) |  |  |",
        "| Impairment of goodwill | $1,910 | $14,740 | $(12,830) | (87%) |",
        "| Percent of revenues, net | 4% | 26% |  |  |",
    ]
    assert paragraphs[0] == "Impairment of Goodwill"
    assert paragraphs[1].startswith("We recorded a goodwill impairment charge of $1.9 million")


def test_fields_follow_question_order_with_gold_forms():
    recs = records()
    rows = by_source(tatqa.convert(recs))
    for doc in recs:
        row = rows[doc["table"]["uid"]]
        questions = sorted(doc["questions"], key=lambda q: int(q["order"]))
        assert list(row["request"]["fields"]) == [f"q{i}" for i in range(1, len(questions) + 1)]
        assert list(row["meta"]["question_uids"].values()) == [q["uid"] for q in questions]
        for (name, spec), q in zip(row["request"]["fields"].items(), questions):
            gold = row["gold"][name]["value"]
            assert spec["instructions"].startswith(clean(q["question"]))
            kind = q["answer_type"]
            if kind == "span":
                assert spec == {"type": "text", "instructions": clean(q["question"])}
                assert gold == clean(q["answer"][0])
            elif kind == "multi-span":
                assert spec["type"] == "list" and spec["items"] == "text"
                assert gold == [clean(a) for a in q["answer"] if a.strip()]
            else:
                assert spec["type"] == "number"
                assert gold == (int(q["answer"]) if kind == "count" else q["answer"])
                assert spec.get("decimals") == (2 if isinstance(gold, float) else None)
                assert spec.get("integer") == (True if kind == "count" else None)
                unit = {"": None, "thousand": "thousands", "million": "millions",
                        "billion": "billions", "percent": "%"}[q["scale"]]
                assert spec.get("unit") == unit
                if unit:
                    assert spec["instructions"] != clean(q["question"])


def test_specific_golds():
    rows = by_source(tatqa.convert(records()))
    row = rows["f6368ece2c45f8080d07ccc5817d2431"]
    assert row["gold"]["q3"]["value"] == ["$14,740", "$1,910"]
    assert row["gold"]["q4"]["value"] == 8325 and row["request"]["fields"]["q4"]["unit"] == "thousands"
    assert "Answer in thousands" in row["request"]["fields"]["q4"]["instructions"]
    assert row["gold"]["q6"]["value"] == 87.04
    assert row["request"]["fields"]["q6"] == {
        "type": "number", "decimals": 2, "unit": "%",
        "instructions": "What is the value of the change in goodwill impairment between 2018 and "
                        "2019 as a percentage of the 2018 goodwill impairment? Answer as a percentage."}
    land = rows["47cd3cbe2a147ee3584ec5227b61321e"]
    assert land["gold"]["q3"]["value"] == ["$672", "$672"]  # "respectively": repeats are kept
    schemes = rows["6cd66ee81b5b1225e601b3c31b157ae2"]
    assert schemes["gold"]["q1"]["value"] == ["Defined contribution schemes", "Defined benefit schemes"]
    count = rows["58b58094569a43f8804e831c5cda5189"]["request"]["fields"]["q5"]
    assert count == {"type": "number", "integer": True,
                     "instructions": "How many years did Gross deferred tax assets exceed $400 million?"}


def test_unusable_answers_are_skipped():
    assert tatqa.question_field({"answer_type": "multi-span", "answer": ["", " "],
                                 "question": "Which?", "scale": ""}) is None
    assert tatqa.question_field({"answer_type": "count", "answer": "two", "question": "How many?",
                                 "scale": ""}) is None
    assert tatqa.question_field({"answer_type": "arithmetic", "answer": 1.5, "question": "What?",
                                 "scale": "dozens"}) is None


@pytest.mark.network
def test_build_from_hub():
    rows = tatqa.build(limit=5)
    assert len(rows) == 5 and [r["id"] for r in rows] == [f"tatqa-{i:05d}" for i in range(5)]
    assert all(validate_row(r, test="tatqa") == [] for r in rows)
