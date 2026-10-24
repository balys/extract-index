import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, drop

FIXTURE = Path(__file__).parent / "fixtures" / "drop" / "source.json"


def records() -> list[dict]:
    """The fixture's passages expanded into `load_source` records (one per question)."""
    data = json.loads(FIXTURE.read_text())
    return [{"section_id": s["section_id"], "query_id": q["query_id"], "passage": s["passage"],
             "question": q["question"], "spans": q["spans"], "types": q["types"]}
            for s in data["sections"] for q in s["qas"]]


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(drop, key), str) and getattr(drop, key)
    assert drop.NAME == "drop" and drop.AREA == "Numbers" and drop.LICENSE == "CC BY-SA 4.0"
    assert len(drop.REVISION) == 40


# ---------------------------------------------------------------- answer reading (real answer shapes)

@pytest.mark.parametrize("spans, types, expected", [
    # numbers: the most common is the value, the others alternatives
    (["2", "2", "2"], ["number"] * 3, ({"type": "number"}, {"value": 2})),
    (["2", "3", "3", "3", "3"], ["number"] * 5, ({"type": "number"}, {"value": 3, "alternatives": [2]})),
    (["89.1", "89.1", "89.1"], ["number", "number", "span"], ({"type": "number"}, {"value": 89.1})),
    # mixed: the type with more entries wins, only same-type answers become alternatives
    (["80-yard punt return", "80", "80", "80", "80"], ["span"] + ["number"] * 4,
     ({"type": "number"}, {"value": 80})),
    (["36-yard", "36-yard", "36-yard", "36", "36-yard"], ["span"] * 3 + ["number", "span"],
     ({"type": "text"}, {"value": "36-yard"})),
    # dates: full → date, bare year → number, partial → skipped
    (["23 April 1734", "23 April 1734"], ["date", "date"], ({"type": "date"}, {"value": "1734-04-23"})),
    (["04 July 1918"], ["date"], ({"type": "date"}, {"value": "1918-07-04"})),
    (["1943", "1943", "1943"], ["date", "date", "number"], ({"type": "number"}, {"value": 1943})),
    (["1946", "1946"], ["date", "span"], ({"type": "number"}, {"value": 1946})),
    (["April 1752", "April 1752"], ["date", "date"], None),
    (["July 1941", "19 July 1941"], ["date", "date"], None),  # tie between partial and full
    # spans
    (["Dallas", "Dallas"], ["span", "span"], ({"type": "text"}, {"value": "Dallas"})),
    (["Raiders", "Raiders", "Raiders", "the Raiders", "the Raiders"], ["span"] * 5,
     ({"type": "text"}, {"value": "Raiders", "alternatives": ["the Raiders"]})),
    (["7-7", "7-7", "7–7", "7-7"], ["span"] * 4, ({"type": "text"}, {"value": "7-7", "alternatives": ["7–7"]})),
    (["Tom Brady", "Carson Palmer", "Tom Brady", "Carson Palmer"], ["span"] * 4,
     ({"type": "list", "items": "text"}, {"value": ["Tom Brady", "Carson Palmer"]})),
    (["Manning", "Peyton Manning", "Manning", "Peyton Manning"], ["span"] * 4,
     ({"type": "text"}, {"value": "Manning", "alternatives": ["Peyton Manning"]})),
    (["39", "39"], ["span", "span"], ({"type": "number"}, {"value": 39})),
    # ambiguous: one multi-span answer, or annotators who disagree
    (["Chaz Schilens", "JaMarcus Russell"], ["span", "span"], None),
    (["1974", "1975", "1968", "1972", "1979"], ["span"] * 5, None),
    (["tied at 17", "0"], ["span", "number"], None),
    (["3", "11 December 1921"], ["number", "date"], None),
])
def test_answer(spans, types, expected):
    assert drop.answer(spans, types) == expected


# ---------------------------------------------------------------- rows

def test_rows_are_valid():
    rows = drop.convert(records())
    assert len(rows) == 4
    assert [r["id"] for r in rows] == [f"drop-{i:05d}" for i in range(4)]
    for row in rows:
        assert validate_row(row, test="drop") == []
        assert row["meta"]["source"] == "ucinlp/drop" and row["meta"]["split"] == "validation"
        assert {"source", "split", "source_id", "license"} <= set(row["meta"])


def test_deterministic():
    assert json.dumps(drop.convert(records())) == json.dumps(drop.convert(records()))


def test_limit_is_a_prefix():
    full = drop.convert(records())
    assert drop.convert(records(), limit=2) == full[:2]


def test_fields_and_gold_forms():
    recs = records()
    by_query = {r["query_id"]: r for r in recs}
    types = set()
    for row in drop.convert(recs):
        fields = row["request"]["fields"]
        assert 1 <= len(fields) <= 5
        assert list(fields) == [f"q{i}" for i in range(1, len(fields) + 1)]
        qids = [row["meta"]["query_ids"][n] for n in fields]
        positions = [next(i for i, r in enumerate(recs) if r["query_id"] == q) for q in qids]
        assert positions == sorted(positions)  # source order
        for name, spec in fields.items():
            src = by_query[row["meta"]["query_ids"][name]]
            assert src["section_id"] == row["meta"]["source_id"]
            assert row["request"]["state"] == src["passage"]
            assert spec["instructions"] == " ".join(src["question"].split())
            expected_spec, expected_gold = drop.answer(src["spans"], src["types"])
            assert spec == {**expected_spec, "instructions": spec["instructions"]}
            gold = row["gold"][name]
            assert gold == expected_gold
            assert gold["value"] is not None  # no nulls in DROP
            assert gold["value"] not in gold.get("alternatives", [])
            types.add(spec["type"])
    assert types == {"number", "text", "list", "date"}


def test_repeated_questions_keep_the_first_readable_copy():
    base = {"section_id": "s1", "passage": "Some passage."}
    recs = [
        {**base, "query_id": "a", "question": "Who won?", "spans": ["X", "Y"], "types": ["span", "span"]},
        {**base, "query_id": "b", "question": "who  won? ", "spans": ["X", "X"], "types": ["span", "span"]},
        {**base, "query_id": "c", "question": "Who won?", "spans": ["Y", "Y"], "types": ["span", "span"]},
        {**base, "query_id": "d", "question": "How many?", "spans": ["4", "4"], "types": ["number", "number"]},
    ]
    (row,) = drop.convert(recs)
    assert row["meta"]["query_ids"] == {"q1": "b", "q2": "d"}
    assert row["gold"] == {"q1": {"value": "X"}, "q2": {"value": 4}}


def test_rare_types_are_kept():
    rows = {r["meta"]["source_id"]: r for r in drop.convert(records())}
    kinds = [s["type"] for s in rows["history_591"]["request"]["fields"].values()]
    assert kinds.count("list") == 2 and kinds.count("date") == 1


@pytest.mark.network
def test_build_from_hub():
    rows = drop.build(limit=5)
    assert [r["id"] for r in rows] == [f"drop-{i:05d}" for i in range(5)]
    assert all(validate_row(r, test="drop") == [] for r in rows)


def test_passage_under_two_section_ids_is_one_row():
    recs = records()
    first = recs[0]["section_id"]
    twin = [dict(r, section_id="zz_twin", query_id=r["query_id"] + "-twin") for r in recs
            if r["section_id"] == first]
    rows = drop.convert(recs + twin)
    states = [r["request"]["state"] for r in rows]
    assert len(states) == len(set(states))
    assert all(r["meta"]["source_id"] != "zz_twin" for r in rows)
