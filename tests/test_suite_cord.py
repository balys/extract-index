import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, cord

FIXTURE = Path(__file__).parent / "fixtures" / "cord" / "source.json"


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text())["records"]


def by_source(rows: list[dict]) -> dict[str, dict]:
    return {r["meta"]["source_id"]: r for r in rows}


def receipt(split: str, image_id: int) -> dict:
    return next(r["ground_truth"] for r in records()
                if r["split"] == split and r["image_id"] == image_id)


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(cord, key), str) and getattr(cord, key)
    assert cord.NAME == "cord" and cord.AREA == "Documents" and cord.LICENSE == "CC BY 4.0"
    assert cord.SOURCE == "naver-clova-ix/cord-v2" and len(cord.REVISION) == 40


@pytest.mark.parametrize("text, value", [
    ("60.000", 60000), ("60,000", 60000), ("60000", 60000), ("Rp. 60.000", 60000),
    ("Rp 60.000", 60000), ("Rp.60.000", 60000), ("IDR 22,000", 22000), ("1,944,000", 1944000),
    ("5.455", 5455), ("18 000", 18000), ("60000.00", 60000), ("60,000.00", 60000),
    ("60.000,00", 60000), ("Rp 316017.00", 316017), ("2.00", 2), ("0", 0), ("-60.000", -60000),
    ("-Rp 25,000", -25000), ("(0)", 0), ("*46000", 46000), (":5,000", 5000), ("[1,000]", None),
    ("48982.68", None), ("Rp 5272.73", None), ("12,50", None), ("1.000.00", None),
    ("1.000,000", None), ("60.000 60.000", None), ("-", None), ("Discount(0%)", None),
    ("", None), (None, None), (60000, None),
])
def test_parse_amount(text, value):
    assert cord.parse_amount(text) == value


@pytest.mark.parametrize("text, value", [
    ("2", 2), ("2.00", 2), ("(2", 2), ("2.00xITEMs", 2), ("1.00xITEMS", 1), ("(Qty=2.00)", 2),
    ("171", 171), ("1.5", None), ("2 pcs", None), ("", None), (None, None),
])
def test_parse_count(text, value):
    assert cord.parse_count(text) == value


def test_receipt_lines_group_and_order_words():
    assert cord.receipt_lines(receipt("test", 1)) == [
        "J.STB PROMO 17500", "Y.B.BAT 46000", "Y.BASO PROM 27500", "TOTAL 91000", "CASH 91000"]
    lines = cord.receipt_lines(receipt("validation", 78))
    assert lines[0] == "2 Mineral Water 18 000" and lines[-1] == "6 Total 177.870"


def test_receipt_lines_merge_a_split_baseline():
    def word(text, row, x0, x1, y0=100, y1=120):
        return {"text": text, "row_id": row, "quad": {"x1": x0, "x2": x1, "x3": x1, "x4": x0,
                                                      "y1": y0, "y2": y0, "y3": y1, "y4": y1}}
    gt = {"valid_line": [
        {"category": "sub_total.discount_price", "words": [word("3.795", 2, 300, 360, 102, 121)]},
        {"category": "sub_total.discount_price", "words": [word("DISCOUNT", 1, 10, 90)]},
        {"category": "total.total_price", "words": [word("TOTAL", 3, 10, 70, 140, 160),
                                                    word("30.000", 3, 300, 360, 140, 160)]},
    ]}
    assert cord.receipt_lines(gt) == ["DISCOUNT 3.795", "TOTAL 30.000"]


def test_candidates_and_nulls():
    gt = receipt("test", 0)  # paid by card, with a bill discount printed as -60.000
    got = cord.candidates(gt, "\n".join(cord.receipt_lines(gt)))
    assert got == {"total": 60000, "subtotal": 60000, "tax": 5455, "service_charge": None,
                   "discount": 60000, "cash_paid": None, "change": None, "total_quantity": 2,
                   "item_names": ["-TICKET CP"], "item_prices": [60000]}


def test_unclear_fields_are_left_out():
    gt = receipt("test", 9)  # no labelled total; "Discount (0%)" printed but not labelled
    got = cord.candidates(gt, "\n".join(cord.receipt_lines(gt)))
    assert "total" not in got and "discount" not in got
    assert got["subtotal"] == 36000 and got["cash_paid"] == 50000 and got["change"] == 14000
    gt = receipt("test", 41)  # service charge 48982.68 is not whole rupiah
    assert "service_charge" not in cord.candidates(gt, "\n".join(cord.receipt_lines(gt)))
    gt = receipt("validation", 3)  # sub-items ("70%", "Less Ice"): item lists are ambiguous
    got = cord.candidates(gt, "\n".join(cord.receipt_lines(gt)))
    assert "item_names" not in got and "item_prices" not in got
    assert got["tax"] == 0 and got["change"] == 0


def test_rows_are_valid():
    rows = cord.convert(records())
    assert len(rows) == 7
    assert [r["id"] for r in rows] == [f"cord-{i:05d}" for i in range(7)]
    assert [r["meta"]["source_id"] for r in rows] == [
        "test/0", "test/1", "test/9", "test/41", "validation/3", "validation/29", "validation/78"]
    for row in rows:
        assert validate_row(row, test="cord") == []
        assert row["meta"]["source"] == cord.SOURCE and row["meta"]["license"] == "CC BY 4.0"
        assert row["meta"]["split"] in ("test", "validation")


def test_deterministic():
    assert json.dumps(cord.convert(records())) == json.dumps(cord.convert(records()))


def test_limit_is_a_prefix():
    full = cord.convert(records())
    assert cord.convert(records(), limit=3) == full[:3]
    assert cord.convert(records(), limit=0) == []


def test_fields_and_gold_forms():
    recs = records()
    for row in cord.convert(recs):
        gt = next(r["ground_truth"] for r in recs
                  if f"{r['split']}/{r['image_id']}" == row["meta"]["source_id"])
        state = row["request"]["state"]
        assert state == "\n".join(cord.receipt_lines(gt))
        fields = row["request"]["fields"]
        assert cord.MIN_FIELDS <= len(fields) <= cord.MAX_FIELDS
        assert list(fields) == [f for f in cord.ORDER if f in fields]
        cands = cord.candidates(gt, state)
        assert all(f in fields for f in cord.CORE if f in cands)
        for name, spec in fields.items():
            assert spec == cord.SPECS[name]
            value = row["gold"][name]["value"]
            assert value == cands[name]
            if spec["type"] == "number":
                assert spec["decimals"] == 0
                assert value is None or (isinstance(value, int) and value >= 0)
            elif spec["items"] == "number":
                assert all(isinstance(v, int) for v in value)
            else:
                assert all(isinstance(v, str) and v for v in value)
        assert row["gold"].get("total", {"value": 1})["value"] is not None


@pytest.mark.network
def test_build_from_hub():
    rows = cord.build(limit=5)
    assert len(rows) == 5 and [r["id"] for r in rows] == [f"cord-{i:05d}" for i in range(5)]
    assert all(validate_row(r, test="cord") == [] for r in rows)
    assert rows[0]["meta"]["source_id"] == "test/0"


def test_repeated_receipt_text_is_kept_once():
    recs = records()
    twin = dict(recs[0], split="zz", image_id=999)  # same ground truth under another id
    rows = cord.convert(recs + [twin])
    states = [r["request"]["state"] for r in rows]
    assert len(states) == len(set(states))
    assert "zz/999" not in by_source(rows)
