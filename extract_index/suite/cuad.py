"""CUAD (test): 250 contract windows of at most 6,000 characters, 3-5 clause fields each.

Each test contract is cut into consecutive windows on line boundaries, choosing cut points that do
not fall inside any annotated span where possible (very long lines are cut at sentence ends). A
window's fields are CUAD categories:

- answered: every span of the category that overlaps the window lies fully inside it;
- null: no span of the category overlaps the window (Parties and Document Name are never asked as
  null, since a contract names its parties and itself throughout without CUAD marking every mention);
- a category with a span cut by the window edge is never asked.

The field type is fixed per category so it does not reveal how many spans the window holds:
`text` for the single-valued categories (the first span is the value, any others alternatives),
a list of text items for the clause categories and Parties. Instructions are CUAD's own category
descriptions. Windows are drawn round-robin across contracts (each round in a fresh random
contract order) from those with at least one answered category, preferring two or more; null
fields mix categories found elsewhere in the same contract with ones it lacks.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from . import common

NAME = "cuad"
TITLE = "CUAD"
AREA = "Spans"
DESCRIPTION = ("Windows of real commercial contracts with clause fields from CUAD's 41 lawyer-labelled "
               "categories, many of which the window does not contain.")
METRIC = "token F1 / list F1"
LICENSE = "CC BY 4.0"
SOURCE = "theatticusproject/cuad-qa"
REVISION = "d9c4ee0250ae2eb97bdb5b50773ab14ea62d0631"  # refs/convert/parquet
SPLIT = "test"
URL = "https://www.atticusprojectai.org/cuad"

FILE = "default/test/0000.parquet"
WINDOWS = 250
MAX_CHARS = 6000
MIN_CHARS = 400
TEXT_CATEGORIES = {"Document Name", "Agreement Date", "Effective Date", "Expiration Date",
                   "Renewal Term", "Notice Period To Terminate Renewal", "Governing Law"}
NEVER_NULL = {"Document Name", "Parties"}
NULLS = {3: (1, 1, 2), 4: (1, 1, 2), 5: (1, 2, 2)}  # null fields to aim for, by field count

_CATEGORY_RE = re.compile(r'related to "(.+?)"')
_DETAILS_RE = re.compile(r"Details:\s*(.+)", re.S)


DETAIL_FIXES = {  # CUAD's text for this one refers to categories "above" in its own question list
    "Competitive Restriction Exception":
        "Exceptions or carve-outs to non-compete, exclusivity or no-solicit of customers clauses.",
}


SHORT_VALUES = {"Document Name", "Parties", "Agreement Date", "Effective Date"}  # labelled as short phrases


def instructions(category: str, details: str) -> str:
    """CUAD's description of the category, saying when the label is a quoted passage.

    CUAD labels most categories with whole clauses (Governing Law is the clause, not the state),
    and many descriptions are yes/no questions ("Does the contract contain ...?"), so those
    fields ask for the passage explicitly.
    """
    details = DETAIL_FIXES.get(category, details)
    if category in SHORT_VALUES:
        return details
    if category in TEXT_CATEGORIES:
        return f"The passage of the contract that answers this, quoted exactly: {details}"
    return f"Passages of the contract on this point, quoted exactly: {details}"


def field_name(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")


def load_source(cache_dir: str) -> dict:
    """{"categories": [{name, details}] in CUAD order, "contracts": [{title, context, answers}]}.

    `answers` maps each category to its spans as [text, start] pairs (categories without spans
    are left out). The parquet repeats each contract's text per question, so it is read
    dictionary-encoded and decoded once per contract.
    """
    import pyarrow.parquet as pq

    path = common.hf_file(SOURCE, FILE, REVISION, cache_dir)
    table = pq.read_table(path, columns=["title", "context", "question", "answers"],
                          read_dictionary=["context"])
    titles = table.column("title").to_pylist()
    questions = table.column("question").to_pylist()
    answers = table.column("answers").to_pylist()
    contexts = table.column("context")
    categories: dict[str, str] = {}
    contracts: dict[str, dict] = {}
    for i, (title, question, ans) in enumerate(zip(titles, questions, answers)):
        cat, details = _CATEGORY_RE.search(question), _DETAILS_RE.search(question)
        if not cat or not details:
            raise ValueError(f"cuad: unexpected question form {question[:120]!r}")
        categories.setdefault(cat[1], " ".join(details[1].split()))
        c = contracts.get(title)
        if c is None:
            c = contracts[title] = {"title": title, "context": contexts[i].as_py(), "answers": {}}
        spans = [[t, s] for t, s in zip(ans["text"], ans["answer_start"])]
        if spans:
            c["answers"][cat[1]] = spans
    return {"categories": [{"name": n, "details": d} for n, d in categories.items()],
            "contracts": list(contracts.values())}


# ---------------------------------------------------------------- windows

def _cut_points(text: str) -> list[int]:
    """Line starts, plus sentence starts (then word starts) inside stretches longer than a window."""
    points = [0] + [m.end() for m in re.finditer(r"\n", text)] + [len(text)]
    for finer in (r"[.;:]\s+", r"\s+"):
        out = []
        for a, b in zip(points, points[1:]):
            out.append(a)
            if b - a > MAX_CHARS:
                out += [a + m.end() for m in re.finditer(finer, text[a:b]) if a + m.end() < b]
        points = sorted(set(out + [len(text)]))
    return points


def windows(contract: dict) -> list[tuple[int, int]]:
    """Consecutive [start, end) windows of at most MAX_CHARS, trimmed of surrounding whitespace."""
    text = contract["context"]
    spans = [(s, s + len(t)) for v in contract["answers"].values() for t, s in v]
    points = _cut_points(text)
    clean = [p for p in points if not any(a < p < b for a, b in spans)]
    out, start = [], 0
    while start < len(text):
        limit = start + MAX_CHARS
        end = None
        for pool in (clean, points):
            i = bisect_right(pool, limit) - 1
            if i >= 0 and pool[i] > start:
                end = pool[i]
                break
        if end is None:
            end = min(limit, len(text))
        a, b = start, end
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            out.append((a, b))
        start = end
    return out


def _window_fields(contract: dict, window: tuple[int, int], names: list[str]) -> dict | None:
    """Answered categories (spans in the window) and null candidates (`absent` from the contract,
    or found only `elsewhere` in it) for one window; categories cut by an edge are left out.
    None if nothing is answered."""
    a, b = window
    answered, nulls, elsewhere = {}, [], []
    for cat in names:
        spans = sorted((s, t) for t, s in contract["answers"].get(cat, []))
        overlap = [(s, t) for s, t in spans if s < b and s + len(t) > a]
        if not overlap:
            if cat not in NEVER_NULL:
                (elsewhere if spans else nulls).append(cat)
        elif all(s >= a and s + len(t) <= b for s, t in overlap):
            answered[cat] = common.dedupe(t for _, t in overlap)
    if not answered:
        return None
    return {"answered": answered, "absent": nulls, "elsewhere": elsewhere}


def _candidates(contract: dict, names: list[str]) -> list[dict]:
    out = []
    for w in windows(contract):
        if w[1] - w[0] < MIN_CHARS and len(contract["context"].strip()) >= MIN_CHARS:
            continue
        f = _window_fields(contract, w, names)
        if f is not None:
            out.append({"title": contract["title"], "window": w, **f})
    return out


def _choose(cands_by_contract: list[list[dict]], n: int, r) -> list[dict]:
    """Round-robin over contracts (each round in a new random order) until n windows.

    Within a contract, windows with two or more answered categories come first.
    """
    queues = []
    for cands in cands_by_contract:
        q = list(cands)
        r.shuffle(q)
        q.sort(key=lambda c: len(c["answered"]) >= 2)  # pop() takes from the end
        queues.append(q)
    out: list[dict] = []
    while len(out) < n and any(queues):
        order = [q for q in queues if q]
        r.shuffle(order)
        for q in order:
            if len(out) == n:
                break
            out.append(q.pop())
    return out


def _pick_fields(cand: dict, order: dict[str, int], r) -> tuple[list[str], list[str]]:
    """(answered categories, null categories) for one window: 3-5 fields, at least one answered."""
    k = r.choice(sorted(NULLS))
    want_null = r.choice(NULLS[k])
    answered = sorted(cand["answered"], key=order.get)
    absent, elsewhere = list(cand["absent"]), list(cand["elsewhere"])
    r.shuffle(absent)
    r.shuffle(elsewhere)
    n_ans = max(1, min(len(answered), k - want_null))
    chosen = sorted(r.sample(answered, n_ans), key=order.get)
    nulls = []
    while len(chosen) + len(nulls) < k and (absent or elsewhere):
        pool = elsewhere if (elsewhere and (not absent or r.random() < 0.5)) else absent
        nulls.append(pool.pop())
    return chosen, nulls


def convert(source: dict, limit: int | None = None) -> list[dict]:
    categories = source["categories"]
    names = [c["name"] for c in categories]
    order = {n: i for i, n in enumerate(names)}
    details = {c["name"]: c["details"] for c in categories}
    contracts = sorted(source["contracts"], key=lambda c: c["title"])
    by_title = {c["title"]: c for c in contracts}

    r = common.rng(NAME)
    picked = _choose([_candidates(c, names) for c in contracts], WINDOWS, r)
    picked.sort(key=lambda c: (c["title"], c["window"]))
    rows = []
    for idx, cand in enumerate(picked):
        chosen, nulls = _pick_fields(cand, order, r)  # drawn for every window, so limits are prefixes
        if limit is not None and idx >= limit:
            continue
        a, b = cand["window"]
        fields, gold, cats = {}, {}, {}
        for cat in sorted(chosen + nulls, key=order.get):
            name = field_name(cat)
            cats[name] = cat
            if cat in TEXT_CATEGORIES:
                fields[name] = {"type": "text", "instructions": instructions(cat, details[cat])}
            else:
                fields[name] = {"type": "list", "items": "text", "instructions": instructions(cat, details[cat])}
            spans = cand["answered"].get(cat) if cat in chosen else None
            if not spans:
                gold[name] = {"value": None}
            elif cat in TEXT_CATEGORIES:
                gold[name] = {"value": spans[0], **({"alternatives": spans[1:]} if len(spans) > 1 else {})}
            else:
                gold[name] = {"value": spans}
        meta = {"source": SOURCE, "split": SPLIT, "source_id": cand["title"], "license": LICENSE,
                "window": [a, b], "categories": cats}
        rows.append(common.make_row(NAME, idx, by_title[cand["title"]]["context"][a:b], fields, gold, meta))
    return rows


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        source = load_source(d)
    return convert(source, limit=limit)
