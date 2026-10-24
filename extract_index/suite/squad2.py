"""SQuAD 2.0 (validation): 300 Wikipedia paragraphs, every question on a paragraph as one text field.

Unanswerable questions have gold `null`. A paragraph's questions keep their source order as fields
`q01`, `q02`, ... . Exact repeats of a question within one paragraph (case and surrounding space
ignored) are merged; a repeat whose copies disagree on answerability is dropped, since one request
cannot hold both golds.
"""

from __future__ import annotations

from . import common

NAME = "squad2"
TITLE = "SQuAD 2.0"
AREA = "Spans"
DESCRIPTION = ("Wikipedia paragraphs with every crowd-written question on them, about half of which "
               "the paragraph cannot answer.")
METRIC = "token F1"
LICENSE = "CC BY-SA 4.0"
SOURCE = "rajpurkar/squad_v2"
REVISION = "3ffb306f725f7d2ce8394bc1873b24868140c412"
SPLIT = "validation"
URL = "https://rajpurkar.github.io/SQuAD-explorer/"

FILE = "squad_v2/validation-00000-of-00001.parquet"
CONTEXTS = 300


def load_source(cache_dir: str) -> list[dict]:
    """The validation questions in source order: {id, title, context, question, answers}."""
    import pyarrow.parquet as pq

    path = common.hf_file(SOURCE, FILE, REVISION, cache_dir)
    table = pq.read_table(path, columns=["id", "title", "context", "question", "answers"])
    return [{"id": r["id"], "title": r["title"], "context": r["context"], "question": r["question"],
             "answers": list(r["answers"]["text"])} for r in table.to_pylist()]


def _paragraphs(records: list[dict]) -> list[dict]:
    """Group questions by paragraph, numbering paragraphs within each article in source order."""
    by_key: dict[tuple[str, str], dict] = {}
    per_title: dict[str, int] = {}
    for r in records:
        key = (r["title"], r["context"])
        if key not in by_key:
            n = per_title.get(r["title"], 0)
            per_title[r["title"]] = n + 1
            by_key[key] = {"title": r["title"], "p": n, "context": r["context"], "questions": []}
        by_key[key]["questions"].append(r)
    return list(by_key.values())


def _fields(questions: list[dict]) -> list[tuple[str, list[str], list[str]]]:
    """(question, answer texts, question ids) per distinct question, in source order."""
    merged: dict[str, dict] = {}
    for q in questions:
        text = " ".join(q["question"].split())
        answers = [a.strip() for a in q["answers"] if a.strip()]
        m = merged.setdefault(text.lower(), {"question": text, "groups": [], "ids": []})
        m["groups"].append(answers)
        m["ids"].append(q["id"])
    out = []
    for m in merged.values():
        answered = [bool(g) for g in m["groups"]]
        if any(answered) and not all(answered):
            continue  # the copies disagree on whether the paragraph answers it
        out.append((m["question"], common.dedupe(a for g in m["groups"] for a in g), m["ids"]))
    return out


def convert(records: list[dict], limit: int | None = None) -> list[dict]:
    paragraphs = [p for p in _paragraphs(records) if _fields(p["questions"])]
    picked = common.sample_sorted(paragraphs, CONTEXTS, common.rng(NAME),
                                  key=lambda p: (p["title"], p["p"]))
    rows = []
    for idx, para in enumerate(common.take(picked, limit)):
        fields, gold, qids = {}, {}, {}
        for i, (question, answers, ids) in enumerate(_fields(para["questions"]), 1):
            name = f"q{i:02d}"
            fields[name] = {"type": "text", "instructions": question}
            gold[name] = {"value": answers[0] if answers else None}
            if len(answers) > 1:
                gold[name]["alternatives"] = answers[1:]
            qids[name] = ids[0] if len(ids) == 1 else ids
        meta = {"source": SOURCE, "split": SPLIT, "source_id": f"{para['title']}/p{para['p']}",
                "license": LICENSE, "title": para["title"], "question_ids": qids}
        rows.append(common.make_row(NAME, idx, para["context"], fields, gold, meta))
    return rows


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        records = load_source(d)
    return convert(records, limit=limit)
