import pytest

from extract_index import schema
from extract_index.schema import WrongForm, normalise


def row(**over):
    base = {
        "id": "docs-00001", "test": "docs",
        "request": {"state": "Invoice INV-1, total 10.", "fields": {"n": {"type": "text"}, "t": {"type": "number"}}},
        "gold": {"n": {"value": "INV-1"}, "t": {"value": 10}},
        "meta": {"source": "s", "split": "test", "source_id": "1", "license": "CC BY 4.0"},
    }
    base.update(over)
    return base


# ---------------------------------------------------------------- field specs and requests

@pytest.mark.parametrize("name", ["a", "_x", "invoice.total", "a-b_c.9", "A" * 64])
def test_good_field_names(name):
    assert schema.validate_field_spec(name, {"type": "text"}) == []


@pytest.mark.parametrize("name", ["", "9a", "a b", "a/b", "A" * 65, "é"])
def test_bad_field_names(name):
    assert schema.validate_field_spec(name, {"type": "text"}) == [f"field {name!r}: bad field name"]


@pytest.mark.parametrize("spec, fragment", [
    ("text", "spec is not an object"),
    ({"type": "string"}, "unknown type"),
    ({"type": "text", "color": 1}, "unknown keys"),
    ({"type": "text", "instructions": " "}, "instructions must be"),
    ({"type": "number", "unit": 5}, "unit must be a string"),
    ({"type": "duration", "unit": "fortnights"}, "duration unit"),
    ({"type": "number", "integer": "yes"}, "integer must be a boolean"),
    ({"type": "text", "integer": True}, "integer is for numbers"),
    ({"type": "number", "decimals": 7}, "decimals must be an integer 0-6"),
    ({"type": "number", "decimals": True}, "decimals must be an integer 0-6"),
    ({"type": "date", "decimals": 2}, "decimals is for numbers"),
    ({"type": "list", "items": "text", "decimals": 2}, "decimals is for numbers"),
    ({"type": "list"}, "list needs items"),
    ({"type": "list", "items": "time"}, "list needs items"),
    ({"type": "text", "items": "text"}, "items is for lists"),
    ({"type": "estimate", "min": 0}, "needs min and max"),
])
def test_bad_field_specs(spec, fragment):
    problems = schema.validate_field_spec("f", spec)
    assert problems and any(fragment in p for p in problems), problems


@pytest.mark.parametrize("spec", [
    {"type": "duration"}, {"type": "duration", "unit": "weeks", "integer": True},
    {"type": "number", "decimals": 0}, {"type": "list", "items": "number", "decimals": 2},
    {"type": "forecast", "min": 0, "max": 10, "horizon": 3}, {"type": "text", "instructions": "PO number"},
])
def test_good_field_specs(spec):
    assert schema.validate_field_spec("f", spec) == []


def test_validate_request():
    good = {"state": "x", "fields": {"a": {"type": "text"}}, "reference_date": "2026-09-02"}
    assert schema.validate_request(good) == []
    assert schema.validate_request([]) == ["request is not an object"]
    bad = schema.validate_request({"state": " ", "fields": {}, "reference_date": "2026-9-2", "x": 1})
    assert len(bad) == 4


# ---------------------------------------------------------------- canonical forms

def test_canonical_checks():
    assert schema.is_date("2024-02-29") and not schema.is_date("2023-02-29") and not schema.is_date("2026-9-02")
    assert schema.is_time("23:59") and schema.is_time("00:00:59") and not schema.is_time("24:00")
    assert not schema.is_time("9:30") and not schema.is_time("12:60")
    assert schema.is_datetime("2026-09-02T14:30") and schema.is_datetime("2026-09-02T14:30:05")
    assert not schema.is_datetime("2026-09-02 14:30") and not schema.is_datetime("2026-09-02T14:30Z")
    assert schema.is_number(3) and schema.is_number(-0.5) and not schema.is_number(True)
    assert not schema.is_number(float("nan")) and not schema.is_number("3")
    assert schema.is_canonical("text", "a") and not schema.is_canonical("text", "  ")
    assert not schema.is_canonical("list", ["a"])


# ---------------------------------------------------------------- gold and rows

def test_validate_row_ok():
    assert schema.validate_row(row()) == []
    assert schema.validate_row(row(), test="docs") == []


def test_validate_row_problems():
    assert schema.validate_row("x") == ["row is not an object"]
    assert any("bad row id" in p for p in schema.validate_row(row(id="docs-1")))
    assert any("!= 'cord'" in p for p in schema.validate_row(row(), test="cord"))
    assert any("does not start with its test" in p for p in schema.validate_row(row(id="cord-00001")))
    assert any("meta must have" in p for p in schema.validate_row(row(meta={"source": "s"})))
    assert any("missing fields" in p for p in schema.validate_row(row(gold={"n": {"value": "a"}})))
    assert any("not in the request" in p
               for p in schema.validate_row(row(gold={"n": {"value": "a"}, "t": {"value": 1}, "z": {"value": 1}})))


@pytest.mark.parametrize("spec, gold, fragment", [
    ({"type": "text"}, "INV", "must be an object with a value"),
    ({"type": "text"}, {"value": "a", "extra": 1}, "unknown keys"),
    ({"type": "number"}, {"value": "10"}, "is not a canonical number"),
    ({"type": "date"}, {"value": "2026-09-02T00:00"}, "is not a canonical date"),
    ({"type": "list", "items": "text"}, {"value": []}, "empty gold list"),
    ({"type": "list", "items": "text"}, {"value": "a"}, "list gold must be an array"),
    ({"type": "list", "items": "number"}, {"value": [1, "2"]}, "bad number items"),
    ({"type": "text"}, {"value": None, "alternatives": ["a"]}, "next to a non-null value"),
    ({"type": "text"}, {"value": "a", "alternatives": [None]}, "null alternative"),
    ({"type": "date"}, {"value": "2026-09-02", "alternatives": ["Sep 2"]}, "alternative"),
    ({"type": "list", "items": "text"}, {"value": ["a", "b"], "item_alternatives": [["A"]]}, "must parallel"),
    ({"type": "text"}, {"value": "a", "item_alternatives": [["A"]]}, "must parallel"),
    ({"type": "list", "items": "date"}, {"value": ["2026-01-01"], "item_alternatives": [["Jan 1"]]},
     "bad item_alternatives"),
    ({"type": "estimate", "min": 0, "max": 1}, {"value": 0.5}, "not scored"),
])
def test_gold_problems(spec, gold, fragment):
    problems = schema.validate_gold({"f": spec}, {"f": gold})
    assert problems and any(fragment in p for p in problems), problems


def test_gold_ok_with_alternatives():
    fields = {"a": {"type": "text"}, "b": {"type": "list", "items": "text"}, "c": {"type": "number"}}
    gold = {"a": {"value": "x", "alternatives": ["y"]},
            "b": {"value": ["p", "q"], "item_alternatives": [["P"], []], "alternatives": [["p"]]},
            "c": {"value": None}}
    assert schema.validate_gold(fields, gold) == []
    assert schema.validate_gold(fields, []) == ["gold is not an object"]


# ---------------------------------------------------------------- answers

@pytest.mark.parametrize("raw, want", [
    (5, 5.0), (2.5, 2.5), ("1,080.50", 1080.5), ("$1,080.50", 1080.5), ("12%", 12.0),
    ("€ 3.5", 3.5), ("USD 12", 12.0), ("12 EUR", 12.0), ("−4", -4.0), ("1e3", 1000.0),
    (" .5 ", 0.5), ("+7", 7.0),
])
def test_parse_number(raw, want):
    assert schema.parse_number(raw) == want


@pytest.mark.parametrize("raw", [True, None, "abc", "", ".", "1.2.3", float("inf"), "nan", [1], "12 apples"])
def test_parse_number_rejects(raw):
    assert schema.parse_number(raw) is None


@pytest.mark.parametrize("raw, want", [
    ("2026-09-02", "2026-09-02"), ("2026-09-02T10:00:00Z", "2026-09-02"), ("2026-09-02 10:00", "2026-09-02"),
    (" 2026-09-02+02:00", "2026-09-02"), ("2026-02-30", None), ("09/02/2026", None), (20260902, None),
])
def test_norm_date(raw, want):
    assert schema.norm_date(raw) == want


@pytest.mark.parametrize("raw, want", [
    ("14:30", "14:30"), ("9:05", "09:05"), ("14:30:15", "14:30:15"), ("T14:30:00Z", "14:30:00"),
    ("14:30:15.250", "14:30:15"), ("14:30+01:00", "14:30"), ("24:00", None), ("2:30 PM", None), (1430, None),
])
def test_norm_time(raw, want):
    assert schema.norm_time(raw) == want


@pytest.mark.parametrize("raw, want", [
    ("2026-09-02T14:30", "2026-09-02T14:30"), ("2026-09-02 14:30:05", "2026-09-02T14:30:05"),
    ("2026-09-02T14:30:05.5Z", "2026-09-02T14:30:05"), ("2026-09-02T14:30-0500", "2026-09-02T14:30"),
    ("2026-09-02", None), ("2026-09-02T25:00", None), (None, None),
])
def test_norm_datetime(raw, want):
    assert schema.norm_datetime(raw) == want


def test_normalise_scalars():
    assert normalise({"type": "text"}, None) is None
    assert normalise({"type": "text"}, "  INV-1 ") == "INV-1"
    assert normalise({"type": "text"}, 42) == "42"
    assert normalise({"type": "text"}, 4.5) == "4.5"
    assert normalise({"type": "number"}, "1,000") == 1000.0
    assert normalise({"type": "duration", "unit": "days"}, 3) == 3.0
    assert normalise({"type": "date"}, "2026-09-02T00:00:00Z") == "2026-09-02"
    assert normalise({"type": "time"}, "9:05") == "09:05"
    assert normalise({"type": "datetime"}, "2026-09-02 09:05") == "2026-09-02T09:05"


@pytest.mark.parametrize("spec, value", [
    ({"type": "text"}, {"a": 1}), ({"type": "text"}, ["a"]), ({"type": "text"}, True),
    ({"type": "number"}, "ten"), ({"type": "date"}, "next Tuesday"), ({"type": "time"}, "noon"),
    ({"type": "datetime"}, "2026-09-02"), ({"type": "list", "items": "text"}, "a, b"),
    ({"type": "estimate", "min": 0, "max": 1}, 0.5),
])
def test_normalise_wrong_form(spec, value):
    with pytest.raises(WrongForm):
        normalise(spec, value)


def test_normalise_lists():
    spec = {"type": "list", "items": "number"}
    assert normalise(spec, []) == []
    assert normalise(spec, ["1,000", 2, "x", None]) == [1000.0, 2.0, None, None]
    assert normalise({"type": "list", "items": "date"}, ["2026-09-02T10:00", "soon"]) == ["2026-09-02", None]


def test_answer_value():
    assert schema.answer_value({"type": "text", "value": None}) is None
    assert schema.answer_value({"value": "a"}) == "a"
    for bad in (None, "a", {"type": "text"}):
        with pytest.raises(WrongForm):
            schema.answer_value(bad)


def test_validate_response():
    fields = {"a": {"type": "text"}, "b": {"type": "number"}, "c": {"type": "date"}}
    assert schema.validate_response(fields, {"answers": {"a": {"value": "x"}, "b": {"value": "1"},
                                                         "c": {"value": None}}}) == []
    assert schema.validate_response(fields, {"answer": {}}) == ["response must be an object with an answers object"]
    problems = schema.validate_response(fields, {"answers": {"a": {"value": "x"}, "b": {"value": "lots"}}})
    assert "missing answer for 'c'" in problems and any("'b'" in p for p in problems)
