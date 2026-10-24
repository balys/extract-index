"""CORD v2: totals, taxes, payments and line items from Indonesian receipts.

Source: `naver-clova-ix/cord-v2`, all 100 test and 100 validation receipts. Only the
`ground_truth` column of the two parquet files is read (the embedded images are never decoded),
and each file is deleted as soon as it has been read.

State: the receipt's annotated OCR words (`valid_line`), grouped into text lines by their
`row_id`. Lines are ordered top to bottom by the mean height of their words, and words left to
right. Two lines on the same baseline with no horizontal overlap (a key and its value annotated
as separate rows) are merged. CORD does not annotate store headers or footers, so they are not
in the text.

Fields (5-7 per receipt, drawn with the build seed): `total`, `item_names` and `item_prices` are
always asked when the receipt determines them; the rest are drawn from `subtotal`, `tax`,
`service_charge`, `discount`, `cash_paid`, `change` and `total_quantity`. A field the receipt
lacks gets gold `null`, but only if the receipt text has no word hinting at it (for `tax`: no
"tax", "PB1", "PPN", ...). Otherwise the field is left out of that request. `discount` is the
bill discount as a positive amount; it is left out when there are item-level discounts.
`item_names` and `item_prices` are left out of receipts with sub-items (modifiers such as
"Less Ice"), because the text does not show which lines are sub-items.

Amounts are whole rupiah, written `60.000`, `60,000`, `Rp. 60.000`, `60000.00` or `60.000,00`.
`parse_amount` turns them into exact integers. It returns `None` for anything it cannot read
with certainty (a non-zero minor part, mixed separators, stray text), and the field is then left
out. Number fields use `decimals: 0`.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from typing import Any

from . import common

NAME = "cord"
TITLE = "CORD v2"
AREA = "Documents"
DESCRIPTION = ("Totals, taxes, payments and line items from the OCR text of 200 Indonesian shop "
               "and restaurant receipts.")
METRIC = "exact number / list F1"
LICENSE = "CC BY 4.0"
SOURCE = "naver-clova-ix/cord-v2"
REVISION = "7f0115a4b758a71d6473b8d085751692da2fef98"
SPLIT = "test+validation"
URL = "https://github.com/clovaai/cord"

FILES = {
    "test": "data/test-00000-of-00001-9c204eb3f4e11791.parquet",
    "validation": "data/validation-00000-of-00001-cc3c5779fe22e8ca.parquet",
}
N_RECEIPTS = 200
MIN_FIELDS, MAX_FIELDS = 5, 7

AMOUNT_NOTE = "Amounts are whole rupiah: 60.000, 60,000 and 60000.00 all mean 60000."
ORDER = ["total", "subtotal", "tax", "service_charge", "discount", "cash_paid", "change",
         "total_quantity", "item_names", "item_prices"]
CORE = ("total", "item_names", "item_prices")


def _money(instructions: str) -> dict:
    return {"type": "number", "decimals": 0, "instructions": f"{instructions} {AMOUNT_NOTE}"}


SPECS: dict[str, dict] = {
    "total": _money("Total amount due on the receipt."),
    "subtotal": _money("Subtotal as printed (before tax and service charge); null if the receipt "
                       "has no subtotal line."),
    "tax": _money("Tax amount (e.g. PB1, PPN or VAT); null if the receipt has no tax line, 0 if "
                  "it shows 0."),
    "service_charge": _money("Service charge amount; null if the receipt has no service charge "
                             "line, 0 if it shows 0."),
    "discount": _money("Discount on the bill, as a positive amount; null if the receipt has no "
                       "discount line, 0 if it shows 0."),
    "cash_paid": _money("Cash handed over by the customer; null if the receipt shows no cash "
                        "payment, 0 if it shows 0."),
    "change": _money("Change given back to the customer; null if the receipt has no change line, "
                     "0 if it shows 0."),
    "total_quantity": {"type": "number", "decimals": 0,
                       "instructions": "Total quantity of items bought, as printed on the receipt "
                                       "(e.g. 'Qty 3' or '3 items'); null if the receipt prints none."},
    "item_names": {"type": "list", "items": "text",
                   "instructions": "Name of each item line, in receipt order (repeated if an item "
                                   "has two lines); not quantities, codes, prices or modifiers."},
    "item_prices": {"type": "list", "items": "number", "decimals": 0,
                    "instructions": "Line amount of each item line (not the unit price), in "
                                    f"receipt order. {AMOUNT_NOTE}"},
}

# (section, key) in gt_parse for each scalar field, and the words that hint at the field in the
# receipt text (a missing field with a hint is left out instead of getting gold null).
SCALARS = {
    "total": ("total", "total_price"),
    "subtotal": ("sub_total", "subtotal_price"),
    "tax": ("sub_total", "tax_price"),
    "service_charge": ("sub_total", "service_price"),
    "discount": ("sub_total", "discount_price"),
    "cash_paid": ("total", "cashprice"),
    "change": ("total", "changeprice"),
    "total_quantity": ("total", "menuqty_cnt"),
}
HINTS = {
    "subtotal": re.compile(r"sub|jumlah", re.I),
    "tax": re.compile(r"tax|pajak|ppn|pb\s*-?\s*1|vat", re.I),
    "service_charge": re.compile(r"serv|svc|\bs\s*/\s*c\b|\bsc\b", re.I),
    "discount": re.compile(r"disc|diskon|potong|voucher|hemat", re.I),
    "cash_paid": re.compile(r"cash|tunai|tender", re.I),
    "change": re.compile(r"change|kembali|\bchg\b", re.I),
    "total_quantity": re.compile(r"qty|quantity|\bitems?\b|\bjml|jumlah", re.I),
}


# ---------------------------------------------------------------- numbers

_GROUPED_RE = re.compile(r"\d{1,3}([., ])\d{3}(?:\1\d{3})*")
_POINT_DECIMAL_RE = re.compile(r"(\d+|\d{1,3}(?:,\d{3})+)\.(\d{2})")
_COMMA_DECIMAL_RE = re.compile(r"(\d+|\d{1,3}(?:\.\d{3})+),(\d{2})")
_CURRENCY_RE = re.compile(r"^(?:rp\.?|idr)\s*", re.I)
_COUNT_RE = re.compile(r"\(?\s*(?:qty\s*[=:.]?\s*)?(\d+)(?:[.,]0{1,2})?\s*(?:x?\s*items?)?\s*\)?", re.I)


def _whole(t: str) -> int | None:
    if re.fullmatch(r"\d+", t):
        return int(t)
    if _GROUPED_RE.fullmatch(t):
        return int(re.sub(r"\D", "", t))
    for pattern, sep in ((_POINT_DECIMAL_RE, ","), (_COMMA_DECIMAL_RE, ".")):
        m = pattern.fullmatch(t)
        if m:
            return int(m[1].replace(sep, "")) if m[2] == "00" else None
    return None


def parse_amount(s: Any) -> int | None:
    """Exact whole-rupiah value of a CORD amount string, or None if it is not certain.

    `60.000`, `60,000`, `60 000`, `Rp. 60.000`, `60000.00`, `60,000.00` and `60.000,00` are all
    60000; a leading `-` or wrapping parentheses make it negative; stray `*` and `:` marks are
    ignored. A non-zero minor part (`5272.73`), mixed or irregular separators (`1.000.00`) and
    any other text give None.
    """
    if not isinstance(s, str):
        return None
    t = s.replace(" ", " ").strip().strip("*:").strip()
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    if t.startswith("-"):
        neg, t = True, t[1:].strip()
    t = _CURRENCY_RE.sub("", t).strip()
    if t.startswith("-") and not neg:
        neg, t = True, t[1:].strip()
    value = _whole(t)
    if value is None:
        return None
    return -value if neg else value


def parse_count(s: Any) -> int | None:
    """A printed item count: `2`, `2.00`, `(2`, `2.00xITEMs`, `(Qty=2.00)` -> 2; else None."""
    if not isinstance(s, str):
        return None
    m = _COUNT_RE.fullmatch(s.strip())
    return int(m[1]) if m else None


# ---------------------------------------------------------------- receipt text

def receipt_lines(gt: dict) -> list[str]:
    """The receipt's text lines, top to bottom, words left to right."""
    rows: dict[Any, list[tuple]] = {}
    for line in gt.get("valid_line") or []:
        for w in line.get("words") or []:
            text = " ".join(str(w.get("text", "")).split())
            if not text:
                continue
            q = w["quad"]
            x0, x1 = min(q["x1"], q["x4"]), max(q["x2"], q["x3"])
            yc = (q["y1"] + q["y2"] + q["y3"] + q["y4"]) / 4
            h = max(q["y3"], q["y4"]) - min(q["y1"], q["y2"])
            rows.setdefault(w["row_id"], []).append((x0, yc, x1, h, text))
    lines = []
    for words in rows.values():
        lines.append({"y": statistics.fmean(w[1] for w in words),
                      "h": max(1.0, statistics.median(w[3] for w in words)),
                      "x0": min(w[0] for w in words), "x1": max(w[2] for w in words),
                      "words": sorted(words)})
    lines.sort(key=lambda ln: (ln["y"], ln["x0"]))
    merged: list[dict] = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if (prev and abs(ln["y"] - prev["y"]) < 0.5 * min(ln["h"], prev["h"])
                and (ln["x0"] >= prev["x1"] or ln["x1"] <= prev["x0"])):
            prev["words"] = sorted(prev["words"] + ln["words"])
            prev["x0"], prev["x1"] = min(prev["x0"], ln["x0"]), max(prev["x1"], ln["x1"])
            continue
        merged.append(dict(ln))
    return [" ".join(w[4] for w in ln["words"]) for ln in merged]


# ---------------------------------------------------------------- fields

def _menu(gp: dict) -> list[dict]:
    menu = gp.get("menu") or []
    menu = menu if isinstance(menu, list) else [menu]
    return [m for m in menu if isinstance(m, dict)]


def _scalar_gold(name: str, gp: dict, text: str) -> tuple[bool, Any]:
    """(determined, value) for one scalar field; value None means gold null."""
    section, key = SCALARS[name]
    sec = gp.get(section)
    raw = sec.get(key) if isinstance(sec, dict) else None
    if raw is None:
        if name == "total":
            return False, None  # every receipt has a total; an unlabelled one is not "absent"
        if name == "discount" and any("discountprice" in m for m in _menu(gp)):
            return False, None
        if name == "total_quantity" and isinstance(gp.get("total"), dict) \
                and "menutype_cnt" in gp["total"]:
            return False, None
        if HINTS[name].search(text):
            return False, None
        return True, None
    if not isinstance(raw, str):
        return False, None  # two lines for one field (a list): ambiguous
    value = parse_count(raw) if name == "total_quantity" else parse_amount(raw)
    if value is None:
        return False, None
    if name == "discount":
        value = abs(value)
    elif value < 0:
        return False, None
    return True, value


def _item_golds(gp: dict) -> dict[str, list]:
    """Gold lists for item_names and item_prices, when the receipt determines them."""
    menu = _menu(gp)
    if not menu or any("sub" in m for m in menu):
        return {}
    out: dict[str, list] = {}
    names = [m.get("nm") for m in menu]
    if all(isinstance(n, str) for n in names):
        names = [" ".join(n.split()) for n in names]
        if all(names):
            out["item_names"] = names
    prices = [parse_amount(m.get("price")) for m in menu]
    if prices and all(p is not None for p in prices):
        out["item_prices"] = prices
    return out


def candidates(gt: dict, text: str) -> dict[str, Any]:
    """Every field this receipt determines, name -> gold value (None for gold null)."""
    gp = gt.get("gt_parse") or {}
    out: dict[str, Any] = {}
    for name in SCALARS:
        ok, value = _scalar_gold(name, gp, text)
        if ok:
            out[name] = value
    out.update(_item_golds(gp))
    return out


# ---------------------------------------------------------------- build

def load_source(cache_dir: str) -> list[dict]:
    """The ground truth of every test and validation receipt, sorted by (split, image id)."""
    import pyarrow.parquet as pq

    records = []
    for split, filename in FILES.items():
        path = common.hf_file(SOURCE, filename, REVISION, cache_dir)
        column = pq.read_table(path, columns=["ground_truth"]).column("ground_truth").to_pylist()
        _discard(path)  # free the disk before the next download
        for raw in column:
            gt = json.loads(raw)
            records.append({"split": split, "image_id": int(gt["meta"]["image_id"]),
                            "ground_truth": {k: gt[k] for k in ("gt_parse", "meta", "valid_line")}})
    return sorted(records, key=lambda r: (r["split"], r["image_id"]))


def _discard(path: str) -> None:
    for p in {os.path.realpath(path), path}:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def convert(records: list[dict], limit: int | None = None) -> list[dict]:
    r = common.rng(NAME)
    picked = common.sample_sorted(records, N_RECEIPTS, r, key=lambda x: (x["split"], x["image_id"]))
    rows, seen = [], set()
    for rec in picked:
        gt = rec["ground_truth"]
        lines = receipt_lines(gt)
        state = "\n".join(lines)
        if not state.strip() or state in seen:  # a few receipts repeat across test and validation
            continue
        seen.add(state)
        cands = candidates(gt, state)
        core = [f for f in CORE if f in cands]
        extras = [f for f in ORDER if f in cands and f not in CORE]
        k = r.randint(MIN_FIELDS, MAX_FIELDS)
        chosen = set(core) | set(r.sample(extras, min(len(extras), max(0, k - len(core)))))
        names = [f for f in ORDER if f in chosen]
        if not names:
            continue
        fields = {f: dict(SPECS[f]) for f in names}
        gold = {f: {"value": cands[f]} for f in names}
        meta = {"source": SOURCE, "split": rec["split"],
                "source_id": f"{rec['split']}/{rec['image_id']}", "license": LICENSE}
        rows.append(common.make_row(NAME, len(rows), state, fields, gold, meta))
    return common.take(rows, limit)


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        records = load_source(d)
    return convert(records, limit)
