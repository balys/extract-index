"""`docs`: synthetic business documents with exact labels (Turion AI's own generator).

Sixteen document families (invoices, receipts, order and shipping emails, bank statements,
timesheets, flight and hotel bookings, meeting threads, support tickets, maintenance logs,
payslips, purchase orders, utility bills, lease summaries, incident reports), each in two or
three layouts. Every document is rendered from structured values drawn first, and the gold is
computed from those values, never parsed back from the text. Each request asks 5-9 typed
fields: values read from the text, one- or two-step computed values (totals, due dates,
durations, counts, differences) with plain instructions, and fields the document does not
determine (gold null), some next to a near miss such as "PO: to follow".

The build is deterministic: all randomness comes from `common.rng("docs")` (one sub-generator
per row, seeded from it), with no clock, no hashing and no external data, and a limited build is
a prefix of the full one. Every person, company, city and product is invented.

Rule: no model may be trained on these templates or on rows made from them. Turion AI trains its
own models on a separate generator.
"""

from __future__ import annotations

import random

from ..schema import validate_row
from . import docs_fam_a as A
from . import docs_fam_b as B
from .common import make_row, rng
from .docs_kit import Doc, add_footer

NAME = "docs"
TITLE = "Business documents"
AREA = "Documents"
DESCRIPTION = ("Synthetic invoices, receipts, emails, statements, bookings, logs and reports, "
               "each with 5-9 typed fields to read, compute or leave null.")
METRIC = "exact / token F1 / list F1"
LICENSE = "CC BY 4.0"
SOURCE = "turion-ai"
REVISION = "docs-gen-0.1"
SPLIT = "test"
URL = "https://github.com/balys/extract-index"

REQUESTS = 400
MIN_FIELDS, MAX_FIELDS = 5, 9
MIN_CHARS, MAX_CHARS = 400, 2500

# (family, layouts, generator)
FAMILIES = (
    ("invoice", ("email", "kv", "table"), A.invoice),
    ("receipt", ("thermal", "email"), A.receipt),
    ("order_confirmation", ("email", "summary"), A.order_confirmation),
    ("shipping_notice", ("email", "tracking"), A.shipping_notice),
    ("bank_statement", ("table", "summary"), A.bank_statement),
    ("timesheet", ("table", "email"), A.timesheet),
    ("flight_itinerary", ("eticket", "email"), A.flight_itinerary),
    ("hotel_booking", ("email", "kv"), A.hotel_booking),
    ("meeting_thread", ("thread", "invite"), B.meeting_thread),
    ("support_ticket", ("log", "email"), B.support_ticket),
    ("maintenance_log", ("workorder", "history"), B.maintenance_log),
    ("payslip", ("table", "kv"), B.payslip),
    ("purchase_order", ("table", "email"), B.purchase_order),
    ("utility_bill", ("kv", "email"), B.utility_bill),
    ("lease_summary", ("abstract", "letter"), B.lease_summary),
    ("incident_report", ("report", "update"), B.incident_report),
)
# How many null fields a request gets (before capping by what the document offers).
NULL_COUNTS = (0, 1, 1, 2, 2, 2, 3)


def _schedule(master: random.Random) -> list[tuple[int, int]]:
    """(family index, occurrence within the family) for every row: balanced, shuffled."""
    n = len(FAMILIES)
    fams = [i % n for i in range(REQUESTS)]
    master.shuffle(fams)
    seen = [0] * n
    out = []
    for f in fams:
        out.append((f, seen[f]))
        seen[f] += 1
    return out


def _weighted_pick(cands: list, k: int, r: random.Random) -> list:
    """`k` candidates without replacement, favouring higher weights (Efraimidis-Spirakis)."""
    keyed = sorted(((r.random() ** (1.0 / c.weight), i) for i, c in enumerate(cands)), reverse=True)
    return [cands[i] for _, i in keyed[:k]]


def _select(doc: Doc, r: random.Random) -> list:
    k = r.randint(MIN_FIELDS, MAX_FIELDS)
    nulls = [c for c in doc.cands if c.value is None]
    vals = [c for c in doc.cands if c.value is not None]
    n_null = min(r.choice(NULL_COUNTS), len(nulls), k - 3)
    k = min(k, len(vals) + n_null)
    picked = _weighted_pick(nulls, n_null, r) + _weighted_pick(vals, k - n_null, r)
    order = {id(c): i for i, c in enumerate(doc.cands)}
    return sorted(picked, key=lambda c: order[id(c)])


def _check_spans(doc: Doc) -> None:
    """Text gold (and every alternative) must be an exact substring of the document."""
    for c in doc.cands:
        if c.value is None:
            continue
        t = c.spec["type"]
        if t == "text":
            forms = [c.value] + (c.alternatives or [])
        elif t == "list" and c.spec["items"] == "text":
            forms = list(c.value) + [x for alts in (c.item_alternatives or []) for x in alts]
        else:
            continue
        for f in forms:
            if f not in doc.state:
                raise AssertionError(f"{doc.family}/{doc.layout}: {c.name} gold {f!r} not in the text")


def _generate(fam: int, occ: int, seed: int) -> Doc:
    family, layouts, gen = FAMILIES[fam]
    r = random.Random(seed)
    layout = layouts[occ % len(layouts)]
    for _ in range(50):
        doc = gen(r, layout)
        doc.family, doc.layout = family, layout
        add_footer(doc)
        if MIN_CHARS <= len(doc.state) <= MAX_CHARS:
            _check_spans(doc)
            return doc
    raise RuntimeError(f"{family}/{layout}: no document within {MIN_CHARS}-{MAX_CHARS} chars")


def build(limit: int | None = None) -> list[dict]:
    master = rng(NAME)
    schedule = _schedule(master)
    n = REQUESTS if limit is None else max(0, min(limit, REQUESTS))
    rows = []
    for idx in range(n):
        fam, occ = schedule[idx]
        seed = master.getrandbits(64)
        doc = _generate(fam, occ, seed)
        picked = _select(doc, random.Random(seed ^ 0x5EED))
        fields = {c.name: c.spec for c in picked}
        gold = {c.name: c.gold() for c in picked}
        meta = {"source": SOURCE, "split": SPLIT, "source_id": f"{doc.family}-{doc.layout}-{occ}",
                "license": LICENSE, "family": doc.family}
        ref = doc.reference_date.isoformat() if doc.reference_date else None
        row = make_row(NAME, idx, doc.state, fields, gold, meta, reference_date=ref)
        problems = validate_row(row, test=NAME)
        if problems:
            raise AssertionError(problems)
        rows.append(row)
    return rows
