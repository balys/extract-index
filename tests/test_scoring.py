import json

import pytest

from kit_fixture import make_suite, suite_rows
from extract_index.scoring import (MISSING, list_f1, max_matching, normalize_answer, percentile, score_field,
                                   score_run, token_f1)
from extract_index.suite import TESTS


def a(value, **extra):
    return {"value": value, **extra}


TEXT = {"type": "text"}
NUM = {"type": "number"}


# ---------------------------------------------------------------- text

def test_squad_normalisation():
    assert normalize_answer("The  Normans, in 'Normandy'!") == "normans in normandy"
    assert normalize_answer("An apple a day") == "apple day"
    assert normalize_answer("Theater") == "theater"  # articles only as whole words


def test_token_f1():
    assert token_f1("Normandy", "normandy.") == 1.0
    assert token_f1("in Normandy", "Normandy") == pytest.approx(2 / 3)
    assert token_f1("the the", "a") == 1.0  # both normalise to empty
    assert token_f1("the", "Normandy") == 0.0
    assert token_f1("Paris", "London") == 0.0
    assert token_f1("w x y z", "w x") == pytest.approx(2 * (1 / 2) * 1 / 1.5)
    assert token_f1("x x y", "x y y") == pytest.approx(2 / 3)  # multiset overlap


def test_text_field_and_alternatives():
    gold = {"value": "Normandy", "alternatives": ["in Normandy", "the north of France"]}
    assert score_field(TEXT, gold, a("in Normandy")) == 1.0
    assert score_field(TEXT, gold, a("north France")) == pytest.approx(token_f1("north France", "the north of France"))
    assert score_field(TEXT, {"value": "Rollo"}, a("Rollo the Walker")) == pytest.approx(2 * (1 / 2) / 1.5)
    assert score_field(TEXT, {"value": "42"}, a(42)) == 1.0  # numbers are accepted as text


# ---------------------------------------------------------------- null and unanswered

def test_gold_null():
    gold = {"value": None}
    assert score_field(TEXT, gold, a(None)) == 1.0
    assert score_field(TEXT, gold, a("x")) == 0.0
    assert score_field(TEXT, gold, a("")) == 0.0  # empty text is an answer, not null
    lst = {"type": "list", "items": "text"}
    assert score_field(lst, gold, a([])) == 1.0
    assert score_field(lst, gold, a(None)) == 1.0
    assert score_field(lst, gold, a(["x"])) == 0.0
    assert score_field(TEXT, gold, a([])) == 0.0  # [] is the wrong form for text


def test_answer_null_on_non_null_gold():
    assert score_field(TEXT, {"value": "x"}, a(None)) == 0.0
    assert score_field({"type": "list", "items": "text"}, {"value": ["x"]}, a([])) == 0.0


@pytest.mark.parametrize("answer", [MISSING, None, "x", {"type": "text"}, a({"x": 1}), a(["x"]), a(True)])
def test_unanswered_and_wrong_forms_score_zero_even_on_null_gold(answer):
    assert score_field(TEXT, {"value": None}, answer) == 0.0
    assert score_field(TEXT, {"value": "x"}, answer) == 0.0


@pytest.mark.parametrize("spec, value", [
    (NUM, "ten"), ({"type": "date"}, "Sept 2"), ({"type": "time"}, "half past two"),
    ({"type": "datetime"}, "2026-09-02"), ({"type": "list", "items": "text"}, "a, b"),
])
def test_wrong_forms(spec, value):
    assert score_field(spec, {"value": None}, a(value)) == 0.0


# ---------------------------------------------------------------- numbers and durations

@pytest.mark.parametrize("decimals, gold, answer, want", [
    (2, 1080.5, 1080.5, 1.0),
    (2, 1080.5, "1,080.50", 1.0),
    (2, 1080.5, "$1,080.504", 1.0),
    (2, 1080.5, 1080.505, 1.0),   # exactly half a unit in the last place: inside (+1e-9)
    (2, 1080.5, 1080.506, 0.0),
    (2, 1080.5, 1080.49, 0.0),
    (0, 5, 5.5, 1.0),
    (0, 5, 5.51, 0.0),
    (0, 5, 4.5, 1.0),
    (3, 0.125, 0.1255, 1.0),
    (3, 0.125, 0.1256, 0.0),
    (6, 1.0, 1.0000005, 1.0),
    (6, 1.0, 1.0000006, 0.0),
])
def test_number_decimals_tolerance(decimals, gold, answer, want):
    assert score_field({"type": "number", "decimals": decimals}, {"value": gold}, a(answer)) == want


@pytest.mark.parametrize("gold, answer, want", [
    (1000, 1000.0009, 1.0),        # 1e-6 relative: 0.001 allowed
    (1000, 1000.0011, 0.0),
    (0.5, 0.5000009, 1.0),         # max(1, |g|): 1e-6 absolute near zero
    (0.5, 0.5000011, 0.0),
    (0, 0.0000009, 1.0),
    (-250, "-250", 1.0),
    (12, "12%", 1.0),
    (3, 3.1, 0.0),
])
def test_number_relative_tolerance(gold, answer, want):
    assert score_field(NUM, {"value": gold}, a(answer)) == want


def test_duration_uses_number_rule():
    spec = {"type": "duration", "unit": "hours", "decimals": 1}
    assert score_field(spec, {"value": 2.5}, a("2.5")) == 1.0
    assert score_field(spec, {"value": 2.5}, a(2.56)) == 0.0
    assert score_field({"type": "duration", "unit": "days"}, {"value": 3}, a(3)) == 1.0


def test_number_alternatives():
    gold = {"value": 1080.5, "alternatives": [1050.5]}
    assert score_field({"type": "number", "decimals": 2}, gold, a(1050.5)) == 1.0
    assert score_field({"type": "number", "decimals": 2}, gold, a(1060)) == 0.0


# ---------------------------------------------------------------- dates and times

def test_date():
    spec = {"type": "date"}
    assert score_field(spec, {"value": "2026-10-02"}, a("2026-10-02")) == 1.0
    assert score_field(spec, {"value": "2026-10-02"}, a("2026-10-02T09:00:00Z")) == 1.0
    assert score_field(spec, {"value": "2026-10-02"}, a("2026-10-03")) == 0.0
    assert score_field(spec, {"value": "2026-10-02", "alternatives": ["2026-10-01"]}, a("2026-10-01")) == 1.0


def test_time_seconds_only_when_gold_has_them():
    spec = {"type": "time"}
    assert score_field(spec, {"value": "14:30"}, a("14:30:59")) == 1.0
    assert score_field(spec, {"value": "14:30"}, a("2:30")) == 0.0
    assert score_field(spec, {"value": "09:05"}, a("9:05")) == 1.0
    assert score_field(spec, {"value": "14:30:15"}, a("14:30:15")) == 1.0
    assert score_field(spec, {"value": "14:30:15"}, a("14:30:16")) == 0.0
    assert score_field(spec, {"value": "14:30:15"}, a("14:30")) == 0.0
    assert score_field(spec, {"value": "14:30:00"}, a("14:30")) == 1.0


def test_datetime_to_the_minute():
    spec = {"type": "datetime"}
    gold = {"value": "2026-09-05T14:30"}
    assert score_field(spec, gold, a("2026-09-05T14:30:45")) == 1.0
    assert score_field(spec, gold, a("2026-09-05 14:30")) == 1.0
    assert score_field(spec, gold, a("2026-09-05T14:30:00Z")) == 1.0
    assert score_field(spec, gold, a("2026-09-05T14:30+02:00")) == 1.0  # offset dropped, not applied
    assert score_field(spec, gold, a("2026-09-05T14:31")) == 0.0
    assert score_field(spec, {"value": "2026-09-05T14:30:10"}, a("2026-09-05T14:30:50")) == 1.0


# ---------------------------------------------------------------- lists

LT = {"type": "list", "items": "text"}
LN = {"type": "list", "items": "number"}
LD = {"type": "list", "items": "date"}


def test_list_exact_and_order_free():
    assert score_field(LT, {"value": ["Dana Ruiz", "Priya Shah"]}, a(["priya shah", "Dana Ruiz."])) == 1.0


def test_list_partial_f1():
    # 1 of 2 answers right, 1 of 3 gold found: p = 1/2, r = 1/3, F1 = 0.4
    assert score_field(LT, {"value": ["a1", "b2", "c3"]}, a(["a1", "zz"])) == pytest.approx(0.4)


def test_list_text_items_match_at_half_f1_and_count_as_one():
    gold = {"value": ["Acme Corp International"]}
    assert score_field(LT, gold, a(["Acme Corp"])) == 1.0          # F1 0.8
    assert score_field(LT, gold, a(["Acme"])) == 1.0               # F1 0.5: matches
    assert score_field(LT, {"value": ["Acme Corp International Ltd"]}, a(["Acme"])) == 0.0  # F1 0.4


def test_list_multiset_duplicates():
    assert score_field(LT, {"value": ["x"]}, a(["x", "x"])) == pytest.approx(2 / 3)
    assert score_field(LT, {"value": ["x", "x"]}, a(["x", "x"])) == 1.0
    assert score_field(LT, {"value": ["x", "x"]}, a(["x"])) == pytest.approx(2 / 3)


def test_list_optimal_matching():
    # "Bank" matches both gold items, "Bank Holdings Group" only "Bank" (F1 0.5; 0.4 with "Bank Corp").
    # Greedy in answer order would give "Bank" -> "Bank" and leave the second answer unmatched.
    gold = {"value": ["Bank", "Bank Corp"]}
    assert score_field(LT, gold, a(["Bank", "Bank Holdings Group"])) == 1.0
    assert max_matching(3, [[0, 1], [0], [1]]) == 2


def test_list_numbers_and_dates():
    assert score_field({**LN, "decimals": 2}, {"value": [500, 550.5]}, a(["550.50", "$500"])) == 1.0
    assert score_field(LN, {"value": [500, 550.5]}, a([500, 550.4])) == pytest.approx(0.5)
    assert score_field(LD, {"value": ["2026-10-05", "2026-10-07"]},
                       a(["2026-10-07T08:00", "2026-10-05"])) == 1.0


def test_list_wrong_form_items_match_nothing():
    assert score_field(LN, {"value": [1, 2]}, a([1, "two"])) == pytest.approx(0.5)


def test_list_item_alternatives():
    gold = {"value": ["United States", "UK"], "item_alternatives": [["USA", "US"], ["United Kingdom"]]}
    assert score_field(LT, gold, a(["USA", "United Kingdom"])) == 1.0
    assert score_field(LT, gold, a(["US"])) == pytest.approx(2 / 3)


def test_list_whole_alternatives():
    gold = {"value": ["a1", "b2"], "alternatives": [["c3"]]}
    assert score_field(LT, gold, a(["c3"])) == 1.0
    assert score_field(LT, gold, a(["a1"])) == pytest.approx(2 / 3)


def test_list_f1_both_empty():
    assert list_f1(LT, [], []) == 1.0
    assert list_f1(LT, [["x"]], []) == 0.0
    assert list_f1(LT, [], ["x"]) == 0.0


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 80) == pytest.approx(4.2)
    assert percentile([7], 80) == 7


# ---------------------------------------------------------------- runs

def write_results(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def gold_answers(row):
    return {n: {"type": s["type"], "value": row["gold"][n]["value"]} for n, s in row["request"]["fields"].items()}


@pytest.fixture()
def suite(tmp_path):
    return make_suite(tmp_path / "suite")


def test_score_run_perfect(suite, tmp_path):
    rows = suite_rows(suite)
    results = [{"id": r["id"], "test": r["test"], "status": "ok", "answers": gold_answers(r),
                "wall_ms": 10.0 * (i + 1), "engine": "gold", "usage": {"input_tokens": 5, "passes": 1}}
               for i, r in enumerate(rows)]
    write_results(tmp_path / "results.jsonl", results)
    s = score_run(suite, tmp_path / "results.jsonl")
    assert s["complete"] is True and s["index"] == 100.0
    assert set(s["tests"]) == set(TESTS) and all(t["score"] == 100.0 for t in s["tests"].values())
    assert list(s["areas"]) == ["Spans", "Documents", "Numbers", "Entities"]
    assert list(s["types"]) == ["text", "number", "date", "time", "datetime", "duration", "list"]
    assert s["null"]["precision"] == 100.0 and s["null"]["recall"] == 100.0 and s["null"]["f1"] == 100.0
    assert s["null"]["brier"] is None and s["null"]["p_null_coverage"] == 0.0
    assert s["latency_ms"] == {"median": 55.0, "mean": 55.0, "p80": 82.0}
    assert s["usage"] == {"input_tokens": 50, "passes": 10}
    assert s["rows"] == {"total": 10, "ok": 10, "unsupported": 0, "error": 0, "missing": 0, "ignored": 0}
    assert s["engine"] == "gold" and s["edition"] == "0.1" and len(s["suite_sha256"]) == 64
    assert s["tests"]["docs"] == {"score": 100.0, "requests": 2, "fields": 10, "ok": 2, "unsupported": 0,
                                  "error": 0, "missing": 0}


def test_score_run_aggregation(suite, tmp_path):
    """Hand-computed per-test, per-area, per-type, null and index numbers on the fixture suite."""
    rows = {r["id"]: r for r in suite_rows(suite)}
    res = []
    # squad2-00000: where right (1), king null right (1), leader wrong (0); squad2-00001 missing.
    res.append({"id": "squad2-00000", "status": "ok", "wall_ms": 30, "answers": {
        "where": a("in Normandy", p_null=0.0), "king": a(None, p_null=1.0), "leader": a("Bob", p_null=0.5)}})
    # cuad: 00000 errors first then succeeds with everything null; 00001 unsupported.
    res.append({"id": "cuad-00000", "status": "error", "error": "boom", "wall_ms": 5})
    res.append({"id": "cuad-00000", "status": "ok", "wall_ms": 10, "answers": {
        "governing_law": a(None), "parties": a([]), "non_compete": a(None)}})
    res.append({"id": "cuad-00001", "status": "unsupported", "error": "too long", "wall_ms": 1})
    # every other test: perfect answers
    for rid, r in rows.items():
        if r["test"] not in ("squad2", "cuad"):
            res.append({"id": rid, "status": "ok", "wall_ms": 20, "answers": gold_answers(r)})
    res.append({"id": "ghost-00001", "status": "ok", "answers": {}})
    write_results(tmp_path / "results.jsonl", res)

    s = score_run(suite, tmp_path / "results.jsonl")
    assert s["tests"]["squad2"]["score"] == 40.0          # 2 of 5 fields
    assert s["tests"]["squad2"]["missing"] == 1
    assert s["tests"]["cuad"]["score"] == 20.0            # non_compete null right, 1 of 5
    assert (s["tests"]["cuad"]["ok"], s["tests"]["cuad"]["unsupported"]) == (1, 1)
    assert s["areas"]["Spans"] == 30.0
    assert s["areas"]["Documents"] == 100.0
    assert s["index"] == round((40 + 20 + 100 * 5) / 7, 2)
    assert s["complete"] is False                          # squad2-00001 is missing
    assert s["rows"] == {"total": 10, "ok": 8, "unsupported": 1, "error": 0, "missing": 1, "ignored": 1}
    # text fields: squad2 1 + 0 + 1 (null) + 0 + 0 (missing); cuad 0 + 1 + 0 + 0; docs 3; tatqa 1 -> 7 / 13
    assert s["types"]["text"] == round(100 * 7 / 13, 2)
    # null: 8 gold nulls suite-wide (king, mayor, non_compete, renewal, tax, po_number, approver,
    # location). Predicted null: king, governing_law, parties, non_compete + the perfect tests'
    # tax, po_number, approver, location = 8, of which 6 are gold null (mayor is missing and
    # renewal unsupported, so neither is predicted).
    assert s["null"]["precision"] == 75.0
    assert s["null"]["recall"] == 75.0
    assert s["null"]["f1"] == 75.0
    assert s["null"]["brier"] == round((0 + 0 + 0.25) / 3, 4)
    assert s["null"]["p_null_coverage"] == round(3 / 33, 4)
    assert s["latency_ms"]["median"] == 20.0


def test_score_run_without_all_tests_has_no_index(tmp_path):
    suite = make_suite(tmp_path / "suite", only=["squad2", "docs"])
    write_results(tmp_path / "results.jsonl", [])
    s = score_run(suite, tmp_path / "results.jsonl")
    assert s["index"] is None and s["complete"] is False
    assert list(s["tests"]) == ["squad2", "docs"] and s["rows"]["missing"] == 4
    assert s["areas"] == {"Spans": 0.0, "Documents": 0.0}
    assert s["latency_ms"] == {"median": None, "mean": None, "p80": None}
    assert s["null"]["precision"] is None and s["null"]["recall"] == 0.0


def test_score_run_reads_run_dir_and_skips_partial_lines(suite, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    r = suite_rows(suite)[0]
    (run / "results.jsonl").write_text(json.dumps({"id": r["id"], "status": "ok", "answers": gold_answers(r),
                                                   "engine": "x"}) + "\n" + '{"id": "squad2-0000')
    s = score_run(suite, run)
    assert s["tests"]["squad2"]["ok"] == 1 and s["rows"]["missing"] == 9


def test_unsupported_rows_count_as_complete(suite, tmp_path):
    res = [{"id": r["id"], "status": "unsupported", "error": "too long"} for r in suite_rows(suite)]
    write_results(tmp_path / "results.jsonl", res)
    s = score_run(suite, tmp_path / "results.jsonl")
    assert s["complete"] is True and s["index"] == 0.0
    assert s["null"]["precision"] is None and s["latency_ms"]["median"] is None
