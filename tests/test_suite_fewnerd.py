import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, fewnerd

FIXTURE = Path(__file__).parent / "fixtures" / "fewnerd" / "source.json"
FIELD_NAMES = {name for name, _ in fewnerd.COARSE.values()} | {n for n, _ in fewnerd.FINE.values()}


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text())["records"]


def sentences(ids: str) -> list[dict]:
    wanted = ids.split(",")
    return [s for s in records() if s["id"] in wanted]


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(fewnerd, key), str) and getattr(fewnerd, key)
    assert fewnerd.NAME == "fewnerd" and fewnerd.AREA == "Entities"
    assert fewnerd.LICENSE == "CC BY-SA 4.0" and fewnerd.METRIC == "list F1"
    assert fewnerd.SOURCE == "DFKI-SLT/few-nerd" and len(fewnerd.REVISION) == 40


@pytest.mark.parametrize("tokens, text", [
    (["renamed", "``", "George", "Hall", "``", "."], 'renamed "George Hall".'),
    (["the", "``", "Big", "''", "show", ",", "then"], 'the "Big" show, then'),
    (["Thriller", "(", "album", ")", ",", "$", "5", "million", "."], "Thriller (album), $5 million."),
    (["Zambia", "doesn", "’", "t", "anticipate"], "Zambia doesn’t anticipate"),
    (["they", "do", "n't", "know", "Gamer", "'s", "Edge"], "they don't know Gamer's Edge"),
    (["Raban", "wrote", "'", "Arabia", "'", "during"], "Raban wrote 'Arabia' during"),
    (["the", "Dolphins", "'", "final", "loss"], "the Dolphins' final loss"),
    (["the", "Polish", "Workers", "'", "Party", "(", "PPR", ")"], "the Polish Workers' Party (PPR)"),
    (["his", "'", "Arabia", "'", "book"], "his 'Arabia' book"),
    (["the", "island", "of", "Kaua", "‘", "i", "."], "the island of Kaua‘i."),
    (["British", "Rail", "‘", "Standard", "’", "class"], "British Rail ‘Standard’ class"),
    (["rate", "of", "5", "%", ";", "see", "[", "1", "]", "!"], "rate of 5%; see [1]!"),
])
def test_detokenise(tokens, text):
    out, offsets = fewnerd.detokenise(tokens)
    assert out == text
    assert len(offsets) == len(tokens)
    for tok, (a, b) in zip(tokens, offsets):
        assert out[a:b] == ('"' if tok in ("``", "''") else tok)


def test_mentions_are_io_runs_of_one_fine_tag():
    fine = fewnerd.FINE_LABELS
    coarse = fewnerd.COARSE_LABELS
    person, org = coarse.index("person"), coarse.index("organization")
    sent = {"id": "0", "tokens": ["``", "Ann", "Lee", "''", "of", "Acme", "Corp", "Tigers", ",", "Ann", "Lee", "."],
            "ner_tags": [0, person, person, 0, 0, org, org, org, 0, person, person, 0],
            "fine_ner_tags": [0, fine.index("person-actor"), fine.index("person-actor"), 0, 0,
                              fine.index("organization-company"), fine.index("organization-company"),
                              fine.index("organization-sportsteam"), 0,
                              fine.index("person-actor"), fine.index("person-actor"), 0]}
    p = fewnerd.make_passage([sent])
    assert p["state"] == '"Ann Lee" of Acme Corp Tigers, Ann Lee.'
    assert [m for _, _, m in p["mentions"]] == ["Ann Lee", "Acme Corp", "Tigers", "Ann Lee"]
    by_coarse, by_fine = fewnerd.golds(p)
    assert by_coarse == {"person": ["Ann Lee"], "organization": ["Acme Corp", "Tigers"]}
    assert by_fine["organization-sportsteam"] == ["Tigers"]


def test_rows_are_valid():
    rows = fewnerd.convert(records())
    assert len(rows) == 19
    assert [r["id"] for r in rows] == [f"fewnerd-{i:05d}" for i in range(len(rows))]
    for row in rows:
        assert validate_row(row, test="fewnerd") == []
        assert row["meta"]["source"] == fewnerd.SOURCE and row["meta"]["split"] == "test"
        assert row["meta"]["license"] == "CC BY-SA 4.0"
        ids = [int(i) for i in row["meta"]["source_id"].split(",")]
        assert 2 <= len(ids) <= 4 and ids == list(range(ids[0], ids[0] + len(ids)))


def test_deterministic():
    assert json.dumps(fewnerd.convert(records())) == json.dumps(fewnerd.convert(records()))


def test_limit_is_a_prefix():
    full = fewnerd.convert(records())
    assert fewnerd.convert(records(), limit=5) == full[:5]
    assert fewnerd.convert(records(), limit=0) == []


def test_mentions_are_substrings_and_gold_matches_the_source():
    rows = fewnerd.convert(records())
    nulls = total = 0
    for row in rows:
        state, fields = row["request"]["state"], row["request"]["fields"]
        assert fewnerd.MIN_FIELDS <= len(fields) <= fewnerd.MAX_FIELDS
        assert set(fields) <= FIELD_NAMES
        passage = fewnerd.make_passage(sentences(row["meta"]["source_id"]))
        assert passage["state"] == state
        by_coarse, by_fine = fewnerd.golds(passage)
        by_name = {name: by_coarse.get(label) for label, (name, _) in fewnerd.COARSE.items()}
        by_name.update({name: by_fine.get(label) for label, (name, _) in fewnerd.FINE.items()})
        for name, spec in fields.items():
            assert spec["type"] == "list" and spec["items"] == "text" and spec["instructions"]
            value = row["gold"][name]["value"]
            assert value == by_name[name]
            total += 1
            if value is None:
                nulls += 1
                continue
            assert len(value) == len(set(value))
            for mention in value:
                assert mention in state and mention == mention.strip()
    assert 0.2 <= nulls / total <= 0.6


def test_passage_text_is_readable():
    rows = fewnerd.convert(records())
    first = rows[0]["request"]["state"]
    assert first.startswith("In the early 1930s the band moved to the Grill Room of the Taft Hotel "
                            'in New York; the band was renamed "George Hall and His Hotel Taft '
                            'Orchestra". The final season')
    for row in rows:
        assert " ," not in row["request"]["state"] and "( " not in row["request"]["state"]


@pytest.mark.network
def test_build_from_hub():
    rows = fewnerd.build(limit=5)
    assert len(rows) == 5 and [r["id"] for r in rows] == [f"fewnerd-{i:05d}" for i in range(5)]
    for row in rows:
        assert validate_row(row, test="fewnerd") == []
        for g in row["gold"].values():
            assert all(m in row["request"]["state"] for m in g["value"] or [])
