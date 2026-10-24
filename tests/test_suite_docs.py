"""The `docs` builder: validity, determinism, coverage, extractive text gold, and computed fields
re-derived from the rendered text with parsers independent of the generator (offline)."""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections import Counter

import pytest

from extract_index.schema import validate_row
from extract_index.suite import docs, summarise

TYPES = ("text", "number", "date", "time", "datetime", "duration", "list")


@pytest.fixture(scope="module")
def rows():
    return docs.build()


def by_family(rows, family, layout=None):
    out = [r for r in rows if r["meta"]["family"] == family]
    if layout:
        out = [r for r in out if r["meta"]["source_id"].startswith(f"{family}-{layout}-")]
    return out


# ---------------------------------------------------------------- independent parsers

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date(s: str, ref: str | None = None) -> dt.date:
    """Any of the generator's date styles, without using its code."""
    s = s.strip()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    words = re.findall(r"[A-Za-z]+|\d+", s)
    # weekday and month abbreviations never collide, so the first month-like word is the month
    month = next(MONTHS[w[:3].lower()] for w in words if w[:3].lower() in MONTHS)
    nums = [int(w) for w in words if w.isdigit()]
    year = next((n for n in nums if n > 31), None)
    day = next(n for n in nums if n <= 31)
    if year is None:
        assert ref, f"yearless date {s!r} needs a reference date"
        year = int(ref[:4])
    return dt.date(year, month, day)


def parse_time(s: str) -> int:
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*([AaPp])?", s)
    h, mi = int(m[1]), int(m[2])
    if m[3]:
        h = h % 12 + (12 if m[3].lower() == "p" else 0)
    return h * 60 + mi


def parse_money(s: str) -> float:
    return float(re.sub(r"[^\d.\-]", "", s.replace("USD", "").replace("EUR", "").replace("GBP", "")))


# ---------------------------------------------------------------- module and rows

def test_module_constants():
    assert docs.NAME == "docs" and docs.TITLE == "Business documents" and docs.AREA == "Documents"
    assert docs.LICENSE == "CC BY 4.0" and docs.SOURCE == "turion-ai" and docs.SPLIT == "test"
    assert docs.URL == "https://github.com/balys/extract-index"
    assert docs.REVISION and docs.METRIC and docs.DESCRIPTION.endswith(".")
    assert "no model may be trained" in docs.__doc__.lower()


def test_all_rows_valid(rows):
    assert len(rows) == 400
    problems = [p for r in rows for p in validate_row(r, test="docs")]
    assert problems == []
    assert [r["id"] for r in rows] == [f"docs-{i:05d}" for i in range(400)]
    ids = [r["meta"]["source_id"] for r in rows]
    assert len(set(ids)) == len(ids)
    for r in rows:
        meta = r["meta"]
        assert meta["source"] == "turion-ai" and meta["split"] == "test" and meta["license"] == "CC BY 4.0"
        assert re.fullmatch(rf"{meta['family']}-[a-z]+-\d+", meta["source_id"])
        assert 5 <= len(r["request"]["fields"]) <= 9
        for name in r["request"]["fields"]:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", name), name


def test_lengths(rows):
    lens = [len(r["request"]["state"]) for r in rows]
    assert min(lens) >= 400 and max(lens) <= 2500
    assert sum(n < 1500 for n in lens) / len(lens) >= 0.8


def test_deterministic_and_prefix(rows):
    again = docs.build()
    assert json.dumps(rows, sort_keys=True) == json.dumps(again, sort_keys=True)
    for n in (0, 1, 37):
        assert json.dumps(docs.build(limit=n), sort_keys=True) == json.dumps(rows[:n], sort_keys=True)


def test_build_is_fast():
    t = time.perf_counter()
    docs.build()
    assert time.perf_counter() - t < 10


# ---------------------------------------------------------------- coverage

def test_type_coverage_and_nulls(rows):
    s = summarise(rows)
    assert set(s["types"]) == set(TYPES)
    assert 0.15 <= s["null_share"] <= 0.30
    items = Counter(spec["items"] for r in rows for spec in r["request"]["fields"].values()
                    if spec["type"] == "list")
    assert set(items) == {"text", "number", "date"}
    units = {spec.get("unit") for r in rows for spec in r["request"]["fields"].values()
             if spec["type"] == "duration"}
    assert {"seconds", "minutes", "hours", "days", "weeks", "months"} <= units
    for t in TYPES:  # every type has both answered and null gold somewhere
        vals = [r["gold"][n]["value"] for r in rows for n, spec in r["request"]["fields"].items()
                if spec["type"] == t]
        assert any(v is None for v in vals) and any(v is not None for v in vals), t
    for r in rows:  # money fields carry decimals and a currency unit
        for spec in r["request"]["fields"].values():
            if spec["type"] == "number" and spec.get("unit") in ("USD", "EUR", "GBP"):
                assert spec["decimals"] == 2


def test_families_and_layouts(rows):
    fams = Counter(r["meta"]["family"] for r in rows)
    assert len(fams) == len(docs.FAMILIES) >= 12
    assert set(fams) == {f for f, _, _ in docs.FAMILIES}
    assert max(fams.values()) - min(fams.values()) <= 1
    for family, layouts, _ in docs.FAMILIES:
        seen = {r["meta"]["source_id"].split("-")[1] for r in by_family(rows, family)}
        assert seen == set(layouts), family


def test_reference_dates(rows):
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    longm = "January|February|March|April|May|June|July|August|September|October|November|December"
    yearless = re.compile(rf"\b(?:{longm}|{months}) \d{{1,2}}\b(?!,? \d{{4}})|\b\d{{1,2}} (?:{longm}|{months})\b(?! \d{{4}})")
    relative = re.compile(r"\b(tomorrow|today|yesterday|next week|this (?:Mon|Tues|Wednes|Thurs|Fri)day"
                          r"|on (?:Mon|Tues|Wednes|Thurs|Fri)day)\b")
    with_ref = 0
    for r in rows:
        s, ref = r["request"]["state"], r["request"].get("reference_date")
        if yearless.search(s) or relative.search(s):
            assert ref, (r["id"], (yearless.search(s) or relative.search(s)).group(0))
        if ref:
            with_ref += 1
            ref_d = dt.date.fromisoformat(ref)
            for name, spec in r["request"]["fields"].items():
                v = r["gold"][name]["value"]
                if v and spec["type"] in ("date", "datetime"):
                    assert abs((dt.date.fromisoformat(v[:10]) - ref_d).days) <= 120, (r["id"], name)
    assert with_ref >= 40


# ---------------------------------------------------------------- extractive text gold

def test_text_gold_is_in_the_state(rows):
    for r in rows:
        state = r["request"]["state"]
        for name, spec in r["request"]["fields"].items():
            g = r["gold"][name]
            if g["value"] is None:
                continue
            if spec["type"] == "text":
                for form in [g["value"]] + g.get("alternatives", []):
                    assert form in state, (r["id"], name, form)
            if spec["type"] == "list" and spec["items"] == "text":
                for form in g["value"] + [x for alts in g.get("item_alternatives", []) for x in alts]:
                    assert form in state, (r["id"], name, form)


def test_near_miss_nulls_exist(rows):
    near = 0
    for r in rows:
        s = r["request"]["state"]
        for name, g in r["gold"].items():
            if g["value"] is None and re.search(r"to follow|pending|assigned at check-in|under investigation|"
                                                r"not yet available|once the return is approved|"
                                                r"will be shared|when your order ships|once your parcel", s):
                near += 1
                break
    assert near >= 30


# ---------------------------------------------------------------- computed fields, re-derived from the text

def test_invoice_total_from_kv_layout(rows):
    checked = 0
    for r in by_family(rows, "invoice", "kv"):
        s = r["request"]["state"]
        parts = dict(re.findall(r"^ {20,}(Subtotal|Sales tax \([\d.]+%\)|VAT \([\d.]+%\)|Shipping|Freight|"
                                r"Delivery|Total due) {2,}(.+)$", s, re.M))
        lines = [parse_money(m) for m in re.findall(r"^\d+ {2,}.+? {2,}\d+ {2,}.+? {2,}(.+)$", s, re.M)]
        sub = parse_money(parts["Subtotal"])
        assert sub == pytest.approx(sum(lines), abs=0.005)
        tax = next(parse_money(v) for k, v in parts.items() if k.startswith(("Sales tax", "VAT")))
        extra = next((parse_money(v) for k, v in parts.items() if k in ("Shipping", "Freight", "Delivery")), 0.0)
        assert parse_money(parts["Total due"]) == pytest.approx(sub + tax + extra, abs=0.005)
        if "total_due" in r["gold"]:
            assert r["gold"]["total_due"]["value"] == pytest.approx(sub + tax + extra, abs=0.005)
            checked += 1
        if "due_date" in r["gold"]:
            issue = parse_date(re.search(r"^Invoice date: +(.+)$", s, re.M)[1])
            net = int(re.search(r"^Payment terms: +Net (\d+)$", s, re.M)[1])
            assert r["gold"]["due_date"]["value"] == (issue + dt.timedelta(days=net)).isoformat()
            checked += 1
    assert checked >= 5


def test_hotel_nights_from_kv_layout(rows):
    checked = 0
    for r in by_family(rows, "hotel_booking", "kv"):
        s, ref = r["request"]["state"], r["request"].get("reference_date")
        ci = parse_date(re.search(r"^Arrival: (.+)$", s, re.M)[1], ref)
        co = parse_date(re.search(r"^Departure: (.+)$", s, re.M)[1], ref)
        if "nights" in r["gold"]:
            assert r["gold"]["nights"]["value"] == (co - ci).days
            checked += 1
        if "check_in_date" in r["gold"]:
            assert r["gold"]["check_in_date"]["value"] == ci.isoformat()
    assert checked >= 3


def test_support_first_response_from_log(rows):
    checked = 0
    for r in by_family(rows, "support_ticket", "log"):
        if "first_response_minutes" not in r["gold"]:
            continue
        entries = re.findall(r"^\[(.+?) (\d{2}:\d{2})\] .+? \((customer|agent)\):", r["request"]["state"], re.M)
        stamp = lambda e: dt.datetime.combine(parse_date(e[0]), dt.time()) + dt.timedelta(minutes=parse_time(e[1]))
        opened = stamp(entries[0])
        first_agent = stamp(next(e for e in entries if e[2] == "agent"))
        assert entries[0][2] == "customer"
        assert r["gold"]["first_response_minutes"]["value"] == (first_agent - opened).total_seconds() / 60
        checked += 1
    assert checked >= 3


def test_utility_usage_and_amount_due_from_kv(rows):
    checked = 0
    for r in by_family(rows, "utility_bill", "kv"):
        s = r["request"]["state"]
        num = lambda label: re.search(rf"^{label}: (.+)$", s, re.M)[1]
        usage = int(num("Current reading").replace(",", "")) - int(num("Previous reading").replace(",", ""))
        due = parse_money(num("Balance forward")) + parse_money(num("Total current charges"))
        assert parse_money(num("AMOUNT DUE")) == pytest.approx(due, abs=0.005)
        if "usage" in r["gold"]:
            assert r["gold"]["usage"]["value"] == usage
            checked += 1
        if "amount_due" in r["gold"]:
            assert r["gold"]["amount_due"]["value"] == pytest.approx(due, abs=0.005)
            checked += 1
    assert checked >= 5


def test_timesheet_hours_from_table(rows):
    checked = 0
    tpat = r"\d{1,2}:\d{2}(?: ?[AaPp][Mm])?"
    for r in by_family(rows, "timesheet", "table"):
        s = r["request"]["state"]
        total = 0.0
        for day, start, end, brk, hours in re.findall(
                rf"^(Mon|Tue|Wed|Thu|Fri) +.+? +({tpat}) +({tpat}) +(\d+) min +(\d+\.\d\d)", s, re.M):
            worked = (parse_time(end) - parse_time(start) - int(brk)) / 60
            assert worked == pytest.approx(float(hours))
            total += worked
            full = {"Mon": "monday", "Tue": "tuesday", "Wed": "wednesday", "Thu": "thursday", "Fri": "friday"}[day]
            if f"hours_{full}" in r["gold"]:
                assert r["gold"][f"hours_{full}"]["value"] == pytest.approx(worked)
                checked += 1
        assert float(re.search(r"^Total hours: ([\d.]+)$", s, re.M)[1]) == pytest.approx(total)
        if "total_hours" in r["gold"]:
            assert r["gold"]["total_hours"]["value"] == pytest.approx(total)
    assert checked >= 3


def test_incident_outage_from_report_timeline(rows):
    checked = 0
    for r in by_family(rows, "incident_report", "report"):
        s = r["request"]["state"]
        current: dt.date | None = None
        marks = {}
        for when, what in re.findall(r"^- (.+?) UTC  (Impact begins|Alert fires|Mitigation|Resolved)", s, re.M):
            *date_part, hm = when.rsplit(" ", 1)
            if date_part:
                current = parse_date(date_part[0])
            marks[what] = dt.datetime.combine(current, dt.time()) + dt.timedelta(minutes=parse_time(hm))
        minutes = lambda a, b: (marks[b] - marks[a]).total_seconds() / 60
        if "outage_minutes" in r["gold"]:
            assert r["gold"]["outage_minutes"]["value"] == minutes("Impact begins", "Resolved")
            checked += 1
        if "time_to_detect" in r["gold"]:
            assert r["gold"]["time_to_detect"]["value"] == minutes("Impact begins", "Alert fires")
            checked += 1
        if "resolved_at" in r["gold"]:
            assert r["gold"]["resolved_at"]["value"] == marks["Resolved"].strftime("%Y-%m-%dT%H:%M")
    assert checked >= 3
