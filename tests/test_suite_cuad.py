import json
from pathlib import Path

import pytest

from extract_index.schema import validate_row
from extract_index.suite import MODULE_KEYS, cuad

FIXTURE = Path(__file__).parent / "fixtures" / "cuad" / "source.json"
LOHA = "LohaCompanyltd_20191209_F-1_EX-10.16_11917878_EX-10.16_Supply Agreement"


def source() -> dict:
    return json.loads(FIXTURE.read_text())


def contract_spans(contract: dict, category: str) -> list[tuple[int, int, str]]:
    return [(s, s + len(t), t) for t, s in contract["answers"].get(category, [])]


def test_module_constants():
    for key in MODULE_KEYS + ("NAME",):
        assert isinstance(getattr(cuad, key), str) and getattr(cuad, key)
    assert cuad.NAME == "cuad" and cuad.AREA == "Spans" and cuad.LICENSE == "CC BY 4.0"
    assert len(cuad.REVISION) == 40


def test_field_names():
    assert cuad.field_name("Document Name") == "document_name"
    assert cuad.field_name("Rofr/Rofo/Rofn") == "rofr_rofo_rofn"
    assert cuad.field_name("Unlimited/All-You-Can-Eat-License") == "unlimited_all_you_can_eat_license"
    assert cuad.field_name("Affiliate License-Licensor") == "affiliate_license_licensor"
    names = [cuad.field_name(c["name"]) for c in source()["categories"]]
    assert len(names) == 41 and len(set(names)) == 41


def test_windows_cover_the_contract_on_line_boundaries():
    src = source()
    for contract in src["contracts"]:
        text = contract["context"]
        ws = cuad.windows(contract)
        assert ws and all(0 < b - a <= cuad.MAX_CHARS for a, b in ws)
        # consecutive, and only whitespace between or around them
        edges = [0] + [x for w in ws for x in w] + [len(text)]
        assert all(not text[x:y].strip() for x, y in zip(edges[::2], edges[1::2]))
        for a, b in ws:
            assert a == 0 or text[a - 1].isspace()
    loha = next(c for c in src["contracts"] if c["title"] == LOHA)
    ws = cuad.windows(loha)
    assert len(ws) == 3
    assert all(loha["context"][a - 1] == "\n" for a, _ in ws[1:])  # this one has no over-long lines


def test_rows_are_valid():
    rows = cuad.convert(source())
    assert len(rows) == 5  # every window with an answered category (fewer than WINDOWS exist)
    assert [r["id"] for r in rows] == [f"cuad-{i:05d}" for i in range(len(rows))]
    for row in rows:
        assert validate_row(row, test="cuad") == []
        assert row["meta"]["source"] == "theatticusproject/cuad-qa" and row["meta"]["split"] == "test"
        assert {"source", "split", "source_id", "license"} <= set(row["meta"])
        assert 3 <= len(row["request"]["fields"]) <= 5


def test_deterministic():
    assert json.dumps(cuad.convert(source())) == json.dumps(cuad.convert(source()))


def test_limit_is_a_prefix():
    full = cuad.convert(source())
    assert cuad.convert(source(), limit=3) == full[:3]


def test_gold_spans_lie_inside_the_window():
    src = source()
    contracts = {c["title"]: c for c in src["contracts"]}
    details = {c["name"]: c["details"] for c in src["categories"]}
    nulls = answered = 0
    for row in cuad.convert(src):
        contract = contracts[row["meta"]["source_id"]]
        a, b = row["meta"]["window"]
        assert row["request"]["state"] == contract["context"][a:b]
        assert len(row["request"]["state"]) <= cuad.MAX_CHARS
        for name, spec in row["request"]["fields"].items():
            category = row["meta"]["categories"][name]
            assert name == cuad.field_name(category)
            assert spec["instructions"] == cuad.instructions(category, details[category])
            if category in cuad.TEXT_CATEGORIES:
                assert spec == {"type": "text", "instructions": cuad.instructions(category, details[category])}
            else:
                assert spec == {"type": "list", "items": "text", "instructions": cuad.instructions(category, details[category])}
            spans = contract_spans(contract, category)
            overlapping = sorted((s, e, t) for s, e, t in spans if s < b and e > a)
            # no field has a span cut by the window edge
            assert all(a <= s and e <= b for s, e, _ in overlapping)
            inside = list(dict.fromkeys(t for _, _, t in overlapping))
            gold = row["gold"][name]
            if gold["value"] is None:
                nulls += 1
                assert not overlapping
                assert category not in cuad.NEVER_NULL
            else:
                answered += 1
                given = gold["value"] if spec["type"] == "list" else [gold["value"], *gold.get("alternatives", [])]
                assert given == inside  # every span in the window, in text order, once
                for t in given:
                    assert t in row["request"]["state"]
    assert nulls and answered


def synthetic() -> dict:
    """Two 4,000-char lines; the 'Governing Law' span straddles the only line break."""
    line1 = ("Alpha " * 667)[:3999] + "\n"
    line2 = ("Omega " * 667)[:4000]
    text = line1 + line2
    cats = ["Document Name", "Parties", "Governing Law", "Audit Rights", "Insurance", "Non-Compete"]
    return {
        "categories": [{"name": c, "details": f"About {c.lower()}"} for c in cats],
        "contracts": [{"title": "T", "context": text, "answers": {
            "Parties": [[text[6:11], 6]],                    # inside window 1
            "Governing Law": [[text[3900:4100], 3900]],     # cut by the window edge
            "Insurance": [[text[4500:4520], 4500]],         # inside window 2
        }}],
    }


def test_a_category_cut_by_the_edge_is_never_asked():
    src = synthetic()
    contract = src["contracts"][0]
    assert cuad.windows(contract) == [(0, 3999), (4000, 8000)]
    rows = cuad.convert(src)
    assert len(rows) == 2
    for row in rows:
        assert "governing_law" not in row["request"]["fields"]
        assert validate_row(row, test="cuad") == []
    first, second = rows
    assert first["gold"]["parties"] == {"value": ["Alpha"]}
    assert second["gold"]["insurance"]["value"] == [contract["context"][4500:4520]]
    # Parties and Document Name are never asked as null
    assert "parties" not in second["request"]["fields"]
    assert "document_name" not in first["request"]["fields"]


def test_long_lines_are_cut_at_sentence_ends():
    text = "This is a sentence. " * 600  # 12,000 chars, one line
    contract = {"title": "T", "context": text.strip(), "answers": {}}
    ws = cuad.windows(contract)
    assert len(ws) >= 2 and all(b - a <= cuad.MAX_CHARS for a, b in ws)
    assert all(text[b - 1] == "." for _, b in ws)


@pytest.mark.network
def test_build_from_hub():
    rows = cuad.build(limit=5)
    assert [r["id"] for r in rows] == [f"cuad-{i:05d}" for i in range(5)]
    assert all(validate_row(r, test="cuad") == [] for r in rows)
