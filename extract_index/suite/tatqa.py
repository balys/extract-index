"""TAT-QA: questions over financial report tables and their surrounding text.

Source: `next-tat/TAT-QA` (the authors' raw JSON), file `tatqa_dataset_dev.json`: 274 documents,
each a table, its paragraphs and 6 questions. 250 documents are drawn with the build seed from
the documents sorted by table uid.

State: the table as plain-text rows (`| cell | cell |`, empty rows dropped, whitespace in cells
collapsed), a blank line, then the paragraphs in their order, separated by blank lines.

Fields: the document's questions in their order, `q1`..`qN` (N <= 6), each with the question as
its instructions. TAT-QA has no unanswerable questions, so no gold is null.

- `arithmetic` and `count` answers are `number` fields. Answers TAT-QA writes as decimals are
  rounded to 2 places in the source (trailing zeros dropped, so 52.5 is 52.50), so they get
  `decimals: 2`. Integer answers get no `decimals` (exact), and `count` answers also get
  `integer: true`.
- `span` answers are `text` fields, with the span as written (`$1.9 million`).
- `multi-span` answers are `list` fields of text items, as written, in the source's order, with
  repeats kept ("the values in 2018 and 2019 respectively" can be `$672`, `$672`). Spans stay text
  even when they are purely numbers; one rule for every span.

Scale: a number field's gold stays in the scale the document states, as TAT-QA records it (an
arithmetic answer of 8325 with scale "thousand" is $8,325 thousand). The scale is given in the
field's `unit` ("thousands", "millions", "billions" or "%") and in a short sentence appended to
the instructions ("Answer in thousands, the scale the document uses."). Answers with no scale
get neither. Text and list fields are copied as written, so they carry no scale.
"""

from __future__ import annotations

import json
from typing import Any

from . import common

NAME = "tatqa"
TITLE = "TAT-QA"
AREA = "Numbers"
DESCRIPTION = ("Questions over financial report tables and their text, answered with exact "
               "numbers, text spans or lists of spans.")
METRIC = "exact number / token F1"
LICENSE = "CC BY 4.0"
SOURCE = "next-tat/TAT-QA"
REVISION = "c96247f5077eac447f63527fd3dcfdc58bb56d6a"
SPLIT = "dev"
URL = "https://nextplusplus.github.io/TAT-QA/"

FILENAME = "tatqa_dataset_dev.json"
N_DOCS = 250
MAX_QUESTIONS = 6

SCALES = {
    "": None,
    "thousand": ("thousands", "Answer in thousands, the scale the document uses."),
    "million": ("millions", "Answer in millions, the scale the document uses."),
    "billion": ("billions", "Answer in billions, the scale the document uses."),
    "percent": ("%", "Answer as a percentage."),
}


def _clean(s: Any) -> str:
    return " ".join(str(s).split())


def render_table(table: list[list[Any]]) -> str:
    lines = []
    for row in table:
        cells = [_clean(c) for c in row]
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_state(doc: dict) -> str:
    paragraphs = sorted(doc.get("paragraphs") or [], key=lambda p: int(p["order"]))
    parts = [render_table(doc["table"]["table"])]
    parts += [t for t in (_clean(p["text"]) for p in paragraphs) if t]
    return "\n\n".join(p for p in parts if p)


def question_field(q: dict) -> tuple[dict, dict] | None:
    """(field spec, gold) for one question, or None if its answer is unusable."""
    kind, answer, question = q["answer_type"], q["answer"], _clean(q["question"])
    if not question:
        return None
    if kind in ("arithmetic", "count"):
        if kind == "count":
            try:
                value: Any = int(str(answer).strip())
            except ValueError:
                return None
        elif isinstance(answer, bool) or not isinstance(answer, (int, float)):
            return None
        else:
            value = answer
        spec: dict = {"type": "number", "instructions": question}
        if isinstance(value, float):
            spec["decimals"] = 2
        if kind == "count":
            spec["integer"] = True
        scale = SCALES.get(q.get("scale") or "", False)
        if scale is False:
            return None
        if scale:
            spec["unit"] = scale[0]
            spec["instructions"] = f"{question} {scale[1]}"
        return spec, {"value": value}
    if kind in ("span", "multi-span"):
        items = [_clean(a) for a in (answer if isinstance(answer, list) else [answer])]
        items = [a for a in items if a]
        if not items:
            return None
        if kind == "span":
            if len(items) != 1:
                return None
            return {"type": "text", "instructions": question}, {"value": items[0]}
        return {"type": "list", "items": "text", "instructions": question}, {"value": items}
    return None


def load_source(cache_dir: str) -> list[dict]:
    path = common.hf_file(SOURCE, FILENAME, REVISION, cache_dir)
    with open(path, encoding="utf-8") as f:
        docs = json.load(f)
    return sorted(docs, key=lambda d: d["table"]["uid"])


def convert(records: list[dict], limit: int | None = None) -> list[dict]:
    r = common.rng(NAME)
    picked = common.sample_sorted(records, N_DOCS, r, key=lambda d: d["table"]["uid"])
    rows = []
    for doc in picked:
        state = render_state(doc)
        fields: dict[str, dict] = {}
        gold: dict[str, dict] = {}
        uids: dict[str, str] = {}
        for q in sorted(doc["questions"], key=lambda q: int(q["order"])):
            if len(fields) == MAX_QUESTIONS:
                break
            made = question_field(q)
            if made is None:
                continue
            name = f"q{len(fields) + 1}"
            fields[name], gold[name] = made
            uids[name] = q["uid"]
        if not fields or not state.strip():
            continue
        meta = {"source": SOURCE, "split": SPLIT, "source_id": doc["table"]["uid"],
                "license": LICENSE, "question_uids": uids}
        rows.append(common.make_row(NAME, len(rows), state, fields, gold, meta))
    return common.take(rows, limit)


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        records = load_source(d)
    return convert(records, limit)
