"""DROP (validation): 300 passages, up to 5 discrete-reasoning questions each, typed by their answers.

The Hub copy keeps only each question's validated answers, flattened into parallel `spans` /
`types` lists: one entry per number or date answer, one entry per span of a span answer. The
original grouping of spans into answers is lost, so span answers are read conservatively:

- every span the same, or the distinct spans all wordings of the most common one (the words of
  each lie within it, or the reverse: "Raiders" / "the Raiders") → `text`, the other wordings as
  alternatives;
- otherwise, the same block of two or more spans repeated by every annotator → `list` (a
  multi-span answer);
- anything else (a multi-span answer seen once, or annotators who disagree) is skipped.

Number answers → `number`; a full date (day, month, year) → `date`; a bare year → `number` (a year
question); a partial date (month and year, day and month) → skipped. A numeric span counts as a
number answer next to number or date answers, or when all spans are that one number. When answer
types are mixed, the type with more entries wins and only same-type answers become alternatives; a
tie is skipped. The most common answer is the gold value, the others are alternatives. No DROP
field is null. Each passage's usable questions are drawn at random, preferring the rare date and
list ones.
"""

from __future__ import annotations

import re
from collections import Counter

from ..schema import is_date
from . import common

NAME = "drop"
TITLE = "DROP"
AREA = "Numbers"
DESCRIPTION = ("Wikipedia and NFL-report passages with questions that need counting, arithmetic, "
               "sorting or dates, answered as numbers, dates or spans.")
METRIC = "exact number / token F1"
LICENSE = "CC BY-SA 4.0"
SOURCE = "ucinlp/drop"
REVISION = "95cda593fae71b60b5b19f82de3fcf3298c1239c"
SPLIT = "validation"
URL = "https://allenai.org/data/drop"

FILE = "data/validation-00000-of-00001.parquet"
PASSAGES = 300
PER_PASSAGE = 5

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_NUMBER_RE = re.compile(r"^-?(\d+(\.\d*)?|\.\d+)$")
_YEAR_RE = re.compile(r"^\d{3,4}$")
_ARTICLES = {"a", "an", "the"}


def load_source(cache_dir: str) -> list[dict]:
    """The validation questions in source order: {section_id, query_id, passage, question, spans, types}."""
    import pyarrow.parquet as pq

    path = common.hf_file(SOURCE, FILE, REVISION, cache_dir)
    table = pq.read_table(path, columns=["section_id", "query_id", "passage", "question", "answers_spans"])
    return [{"section_id": r["section_id"], "query_id": r["query_id"], "passage": r["passage"],
             "question": r["question"], "spans": list(r["answers_spans"]["spans"]),
             "types": list(r["answers_spans"]["types"])} for r in table.to_pylist()]


# ---------------------------------------------------------------- answers

def _number(s: str) -> int | float | None:
    s = s.strip().replace(",", "").replace("−", "-")
    if not _NUMBER_RE.match(s):
        return None
    x = float(s)
    return int(x) if x.is_integer() else x


def _date(s: str) -> tuple[str, int | str] | None:
    """('number', year) for a bare year, ('date', 'YYYY-MM-DD') for a full date, else None.

    The Hub copy writes dates as '{day} {month} {year}' with blank parts left out.
    """
    parts = s.split()
    if len(parts) == 1 and _YEAR_RE.match(parts[0]):
        return "number", int(parts[0])
    if len(parts) != 3:
        return None
    day, month, year = parts
    m = _MONTHS.get(month.lower().rstrip("."))
    if not (day.isdigit() and m and _YEAR_RE.match(year)):
        return None
    iso = f"{int(year):04d}-{m:02d}-{int(day):02d}"
    return ("date", iso) if is_date(iso) else None


def _words(s: str) -> set[str]:
    return {w for w in re.sub(r"[\W_]+", " ", s.lower()).split() if w not in _ARTICLES}


def _ranked(values: list) -> list:
    """Distinct values, most common first (ties keep first-seen order)."""
    counts = Counter(values)
    return sorted(common.dedupe(values), key=lambda v: -counts[v])


def _wordings(spans: list[str]) -> list[str] | None:
    """The spans' distinct texts, most common first, if all are wordings of the top one."""
    ranked = _ranked(spans)
    top = _words(ranked[0])
    if not top:
        return None
    for other in ranked[1:]:
        w = _words(other)
        if not w or not (w <= top or top <= w):
            return None
    return ranked


def answer(spans: list[str], types: list[str]) -> tuple[dict, dict] | None:
    """(field spec without instructions, gold) for one question's answers, or None to skip it."""
    typed: list[tuple[str, object]] = []  # non-span answers: (kind, value), kind number|date|bad
    texts: list[str] = []
    for s, t in zip(spans, types):
        if t == "span":
            if s.strip():
                texts.append(s.strip())
        elif t == "number":
            x = _number(s)
            typed.append(("number", x) if x is not None else ("bad", s))
        elif t == "date":
            typed.append(_date(s) or ("bad", s))
        else:
            typed.append(("bad", s))

    # A numeric span ("1946") is a number answer marked as a span when it sits beside number or
    # date answers, or when every span is that same number. Distinct numeric spans on their own
    # may be one multi-span answer ("1974", "1975"), so they stay spans.
    numeric = [_number(s) for s in texts]
    if texts and all(x is not None for x in numeric) and len(set(numeric)) == 1 and not typed:
        typed, texts = [("number", numeric[0])] * len(texts), []
    elif typed:
        typed = typed + [("number", x) for x in numeric if x is not None]
        texts = [s for s, x in zip(texts, numeric) if x is None]

    if len(typed) > len(texts):
        kinds = Counter(k for k, _ in typed).most_common()
        if len(kinds) > 1 and kinds[0][1] == kinds[1][1]:
            return None
        kind = kinds[0][0]
        if kind == "bad":
            return None
        ranked = _ranked([v for k, v in typed if k == kind])
        gold = {"value": ranked[0]}
        if len(ranked) > 1:
            gold["alternatives"] = ranked[1:]
        return {"type": kind}, gold

    if len(texts) > len(typed):
        wordings = _wordings(texts)
        if wordings is not None:
            gold = {"value": wordings[0]}
            if len(wordings) > 1:
                gold["alternatives"] = wordings[1:]
            return {"type": "text"}, gold
        distinct = common.dedupe(texts)
        reps = len(texts) // len(distinct)
        if not typed and reps >= 2 and texts == distinct * reps:
            return {"type": "list", "items": "text"}, {"value": distinct}
    return None


# ---------------------------------------------------------------- rows

def _passages(records: list[dict]) -> list[dict]:
    """Passages with their usable questions in source order.

    DROP repeats some questions word for word within a passage (case and spacing aside); the
    first copy whose answers can be read is kept. A few passages appear under two section ids;
    they are merged into one (the first section id seen), so no document is in the test twice.
    """
    out: dict[str, dict] = {}
    for r in records:
        key = " ".join(r["passage"].split())
        p = out.setdefault(key, {"section_id": r["section_id"], "passage": r["passage"],
                                 "questions": [], "seen": set()})
        question = " ".join(r["question"].split())
        if not question or question.lower() in p["seen"]:
            continue
        typed = answer(r["spans"], r["types"])
        if typed is not None:
            p["seen"].add(question.lower())
            spec, gold = typed
            p["questions"].append({"query_id": r["query_id"], "question": question,
                                   "spec": spec, "gold": gold})
    return [{k: v for k, v in p.items() if k != "seen"} for p in out.values() if p["questions"]]


def _pick(questions: list[dict], r) -> list[dict]:
    """Up to PER_PASSAGE questions at random, date and list ones first, back in source order."""
    order = list(range(len(questions)))
    r.shuffle(order)
    order.sort(key=lambda i: questions[i]["spec"]["type"] not in ("date", "list"))
    return [questions[i] for i in sorted(order[:PER_PASSAGE])]


def convert(records: list[dict], limit: int | None = None) -> list[dict]:
    r = common.rng(NAME)
    picked = common.sample_sorted(_passages(records), PASSAGES, r, key=lambda p: p["section_id"])
    chosen = [(p, _pick(p["questions"], r)) for p in picked]  # draw for every passage, then cut
    rows = []
    for idx, (p, questions) in enumerate(common.take(chosen, limit)):
        fields, gold, qids = {}, {}, {}
        for i, q in enumerate(questions, 1):
            name = f"q{i}"
            fields[name] = {**q["spec"], "instructions": q["question"]}
            gold[name] = q["gold"]
            qids[name] = q["query_id"]
        meta = {"source": SOURCE, "split": SPLIT, "source_id": p["section_id"], "license": LICENSE,
                "query_ids": qids}
        rows.append(common.make_row(NAME, idx, p["passage"], fields, gold, meta))
    return rows


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        records = load_source(d)
    return convert(records, limit=limit)
