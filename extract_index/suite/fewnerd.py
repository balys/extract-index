"""Few-NERD: lists of named-entity mentions, by category, from short Wikipedia passages.

Source: `DFKI-SLT/few-nerd`, `supervised` config, test split (37,648 sentences, read from the
parquet file on the repo's main branch). The supervised split is a random split of sentences, so
consecutive sentences usually come from different articles.

Passages: the sentences, in id order, are cut into consecutive runs of 2-4 (lengths drawn with
the build seed). Runs with at least two entity categories and at most 1,500 characters are
eligible, and 300 are drawn with the build seed.

State: the tokens detokenised into plain text (`detokenise`): no space before closing punctuation
or after opening brackets and currency signs, PTB quotes (`` and '') become paired straight
double quotes, single quotes pair up or attach as plural possessives (`Dolphins' final`), and
split apostrophes are joined (`doesn ’ t` -> `doesn’t`). Sentences are joined with a space.
Every mention is cut from the state by its tokens' character offsets, so it is an exact
substring of the state.

Mentions: Few-NERD tags are IO (no B- tags), so a mention is a maximal run of tokens with the same
fine tag. Quote marks and `,;:` at a mention's edges are trimmed, as is an unmatched bracket.
Mentions with no letter or digit (a bare `$`) are dropped. Each field's gold is the deduplicated
mentions in order of appearance.

Fields (4-6 per passage): the 8 coarse categories as `people`, `organizations`, `locations`,
`buildings`, `works_of_art`, `products`, `events` and `other_entities`, and in about 30% of
passages one fine category (e.g. `sports_teams`, `politicians`). Each field is a list of text
items; a category the passage does not mention has gold null (about 43% of the fields asked).
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import common

NAME = "fewnerd"
TITLE = "Few-NERD"
AREA = "Entities"
DESCRIPTION = ("Every mention of a named-entity category (people, organizations, places, works, "
               "products, events and more) in short Wikipedia passages.")
METRIC = "list F1"
LICENSE = "CC BY-SA 4.0"
SOURCE = "DFKI-SLT/few-nerd"
REVISION = "205f3e9c9f3577ea2561d43f2f62dc249ab92d5b"
SPLIT = "test"
URL = "https://ningding97.github.io/fewnerd/"

FILENAME = "supervised/test-00000-of-00001.parquet"
N_PASSAGES = 300
MAX_CHARS = 1500
MIN_FIELDS, MAX_FIELDS = 4, 6
NULL_RATE = 0.33  # chance that each coarse field asked is an absent category
FINE_RATE = 0.3  # chance that a passage also asks one fine category

COARSE_LABELS = ["O", "art", "building", "event", "location", "organization", "other", "person",
                 "product"]
FINE_LABELS = [
    "O", "art-broadcastprogram", "art-film", "art-music", "art-other", "art-painting",
    "art-writtenart", "building-airport", "building-hospital", "building-hotel", "building-library",
    "building-other", "building-restaurant", "building-sportsfacility", "building-theater",
    "event-attack/battle/war/militaryconflict", "event-disaster", "event-election", "event-other",
    "event-protest", "event-sportsevent", "location-GPE", "location-bodiesofwater",
    "location-island", "location-mountain", "location-other", "location-park",
    "location-road/railway/highway/transit", "organization-company", "organization-education",
    "organization-government/governmentagency", "organization-media/newspaper",
    "organization-other", "organization-politicalparty", "organization-religion",
    "organization-showorganization", "organization-sportsleague", "organization-sportsteam",
    "other-astronomything", "other-award", "other-biologything", "other-chemicalthing",
    "other-currency", "other-disease", "other-educationaldegree", "other-god", "other-language",
    "other-law", "other-livingthing", "other-medical", "person-actor", "person-artist/author",
    "person-athlete", "person-director", "person-other", "person-politician", "person-scholar",
    "person-soldier", "product-airplane", "product-car", "product-food", "product-game",
    "product-other", "product-ship", "product-software", "product-train", "product-weapon",
]

EACH = "Each distinct name once, as written."
COARSE = {  # coarse label -> (field name, instructions), in field order
    "person": ("people", "Names of people, real or fictional."),
    "organization": ("organizations", "Names of organizations: companies, government bodies, "
                     "political parties, schools and universities, sports teams and leagues, "
                     "bands, media outlets, religious groups and the like."),
    "location": ("locations", "Names of places: countries, cities and regions, rivers, lakes and "
                 "seas, islands, mountains, parks, roads and railways."),
    "building": ("buildings", "Names of buildings and facilities: airports, hospitals, hotels, "
                 "libraries, restaurants, stadiums, theatres and others."),
    "art": ("works_of_art", "Titles of creative works: films, TV and radio programmes, songs and "
            "albums, books and other writing, paintings."),
    "product": ("products", "Names of products: cars, aircraft, ships, trains, weapons, software, "
                "games, foods and other products."),
    "event": ("events", "Names of events: wars, battles and attacks, disasters, elections, "
              "protests, sports events and others."),
    "other": ("other_entities", "Other named things that are not people, organizations, places, "
              "buildings, works, products or events: awards, laws, languages, currencies, "
              "diseases and medical terms, gods, academic degrees, astronomical objects, species "
              "and chemical names."),
}
FINE = {  # fine label -> (field name, instructions)
    "organization-sportsteam": ("sports_teams", "Names of sports teams and clubs."),
    "person-athlete": ("athletes", "Names of athletes and sportspeople."),
    "person-politician": ("politicians", "Names of politicians."),
    "organization-company": ("companies", "Names of companies and businesses."),
    "organization-politicalparty": ("political_parties", "Names of political parties."),
    "organization-education": ("schools_and_universities",
                               "Names of schools, colleges and universities."),
    "location-GPE": ("countries_and_cities", "Names of countries, states and provinces, cities "
                     "and towns."),
    "location-bodiesofwater": ("bodies_of_water", "Names of rivers, lakes, seas and oceans."),
    "event-attack/battle/war/militaryconflict": ("wars_and_battles", "Names of wars, battles, "
                                                 "attacks and other military conflicts."),
    "event-sportsevent": ("sports_events", "Names of sports events, competitions and seasons."),
    "art-film": ("films", "Titles of films."),
    "other-award": ("awards", "Names of awards and prizes."),
    "other-language": ("languages", "Names of languages."),
    "product-software": ("software", "Names of software products."),
}

# ---------------------------------------------------------------- detokeniser

_NO_SPACE_BEFORE = {",", ".", ";", ":", "!", "?", ")", "]", "}", "%", "...", "..", "…", "”", "»"}
_NO_SPACE_AFTER = {"(", "[", "{", "$", "£", "€", "#", "“", "«"}
_DOUBLE_QUOTES = {"``", "''", '"'}
_APOSTROPHES = {"'", "’", "`", "‘"}
_CONTRACTION_RE = re.compile(r"(?i)'(?:s|m|d|re|ve|ll)|n't|n’t|’(?:s|m|d|re|ve|ll)")
_FRAGMENT_RE = re.compile(r"[a-z]{1,3}")
_WORD_END_RE = re.compile(r"\w$")


def detokenise(tokens: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Plain text for a token list, plus each token's (start, end) character offsets."""
    out: list[str] = []
    offsets: list[tuple[int, int]] = []
    pos = 0
    quote_open = single_open = False
    glue_next = False  # the previous token asked for no space after it
    for i, tok in enumerate(tokens):
        text = tok
        space = bool(out) and not glue_next
        glue_next = False
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prev = tokens[i - 1] if i else ""
        if tok in _DOUBLE_QUOTES:
            text = '"'
            if quote_open:
                space = False
            else:
                glue_next = True
            quote_open = not quote_open
        elif tok in _APOSTROPHES and _WORD_END_RE.search(prev) and _FRAGMENT_RE.fullmatch(nxt):
            space, glue_next = False, True  # doesn ’ t, Gluck ’ s, Hawai ` i
        elif tok == "'":
            plural = prev[-1:] in ("s", "S")
            if single_open:  # closing a 'quoted' phrase
                space, single_open = False, False
            elif plural and (nxt[:1].islower() or "'" not in tokens[i + 1:]):
                space = False  # plural possessive: the Dolphins' final loss, Workers' Party
            else:
                glue_next, single_open = True, True
        elif tok == "‘":
            glue_next = True
        elif tok == "’":
            space = False
        elif tok in _NO_SPACE_BEFORE or _CONTRACTION_RE.fullmatch(tok):
            space = False
        if tok in _NO_SPACE_AFTER:
            glue_next = True
        if space:
            out.append(" ")
            pos += 1
        out.append(text)
        offsets.append((pos, pos + len(text)))
        pos += len(text)
    return "".join(out), offsets


# ---------------------------------------------------------------- passages

_EDGE_TRIM = {"``", "''", '"', "'", "’", "‘", "`", "“", "”", "«", "»", ",", ";", ":"}
_HAS_WORD_RE = re.compile(r"\w")


def _trim(tokens: list[str], a: int, b: int) -> tuple[int, int]:
    """Trim quote marks, `,;:` and an unmatched bracket from token span [a, b)."""
    while True:
        if a < b and tokens[a] in _EDGE_TRIM:
            a += 1
        elif a < b and tokens[b - 1] in _EDGE_TRIM:
            b -= 1
        elif a < b and tokens[b - 1] == ")" and "(" not in tokens[a:b - 1]:
            b -= 1
        elif a < b and tokens[a] == "(" and ")" not in tokens[a + 1:b]:
            a += 1
        else:
            return a, b


def make_passage(sentences: list[dict]) -> dict:
    """State text and mentions [(coarse, fine, text)] of consecutive sentences."""
    parts: list[str] = []
    mentions: list[tuple[str, str, str]] = []
    base = 0
    spans: list[tuple[str, str, int, int]] = []
    for s in sentences:
        tokens, fine = list(s["tokens"]), list(s["fine_ner_tags"])
        coarse = list(s["ner_tags"])
        text, offsets = detokenise(tokens)
        i = 0
        while i < len(tokens):
            if not fine[i]:
                i += 1
                continue
            j = i
            while j < len(tokens) and fine[j] == fine[i]:
                j += 1
            a, b = _trim(tokens, i, j)
            if a < b:
                spans.append((COARSE_LABELS[coarse[i]], FINE_LABELS[fine[i]],
                              base + offsets[a][0], base + offsets[b - 1][1]))
            i = j
        parts.append(text)
        base += len(text) + 1
    state = " ".join(parts)
    for c, f, a, b in spans:
        mention = state[a:b]
        if _HAS_WORD_RE.search(mention):
            mentions.append((c, f, mention))
    return {"ids": [str(s["id"]) for s in sentences], "state": state, "mentions": mentions}


def golds(passage: dict) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Deduplicated mentions in order of appearance, per coarse and per fine label."""
    coarse: dict[str, list[str]] = {}
    fine: dict[str, list[str]] = {}
    for c, f, m in passage["mentions"]:
        coarse.setdefault(c, []).append(m)
        fine.setdefault(f, []).append(m)
    return ({k: common.dedupe(v) for k, v in coarse.items()},
            {k: common.dedupe(v) for k, v in fine.items()})


def choose_fields(passage: dict, r) -> tuple[dict, dict]:
    by_coarse, by_fine = golds(passage)
    present = [c for c in COARSE if c in by_coarse]
    absent = [c for c in COARSE if c not in by_coarse]
    n = r.randint(MIN_FIELDS, MAX_FIELDS)
    fine_label = None
    if r.random() < FINE_RATE:
        here = [f for f in FINE if f in by_fine]
        away = [f for f in FINE if f not in by_fine]
        pool = here if (here and r.random() < 0.5) or not away else away
        fine_label = r.choice(pool)
        n -= 1
    n_null = sum(r.random() < NULL_RATE for _ in range(n))
    n_null = max(n - len(present), min(n_null, len(absent)))
    n_present = min(n - n_null, len(present))
    chosen = set(r.sample(present, n_present)) | set(r.sample(absent, min(n_null, len(absent))))
    fields: dict[str, dict] = {}
    gold: dict[str, dict] = {}
    for label, (name, instructions) in COARSE.items():
        if label in chosen:
            fields[name] = {"type": "list", "items": "text", "instructions": f"{instructions} {EACH}"}
            gold[name] = {"value": by_coarse.get(label) or None}
    if fine_label:
        name, instructions = FINE[fine_label]
        fields[name] = {"type": "list", "items": "text", "instructions": f"{instructions} {EACH}"}
        gold[name] = {"value": by_fine.get(fine_label) or None}
    return fields, gold


# ---------------------------------------------------------------- build

def load_source(cache_dir: str) -> list[dict]:
    """The test sentences as {id, tokens, ner_tags, fine_ner_tags}, in id order."""
    import pyarrow.parquet as pq

    path = common.hf_file(SOURCE, FILENAME, REVISION, cache_dir)
    pf = pq.ParquetFile(path)
    features = json.loads(pf.schema_arrow.metadata[b"huggingface"])["info"]["features"]
    if (features["ner_tags"]["feature"]["names"] != COARSE_LABELS
            or features["fine_ner_tags"]["feature"]["names"] != FINE_LABELS):
        raise ValueError("Few-NERD label names differ from the pinned revision's")
    table = pf.read(columns=["id", "tokens", "ner_tags", "fine_ner_tags"])
    records = table.to_pylist()
    return sorted(records, key=lambda s: int(s["id"]))


def _runs(sentences: list[dict], r) -> list[list[dict]]:
    """Consecutive runs of 2-4 sentences; a gap in the ids ends a run."""
    out: list[list[dict]] = []
    i = 0
    while i < len(sentences):
        n = r.randint(2, 4)
        run = [sentences[i]]
        while len(run) < n and i + len(run) < len(sentences) \
                and int(sentences[i + len(run)]["id"]) == int(run[-1]["id"]) + 1:
            run.append(sentences[i + len(run)])
        i += len(run)
        if len(run) >= 2:
            out.append(run)
    return out


def _eligible(p: dict) -> bool:
    return len(p["state"]) <= MAX_CHARS and len({c for c, _, _ in p["mentions"]}) >= 2


def convert(records: list[dict], limit: int | None = None) -> list[dict]:
    r = common.rng(NAME)
    sentences = sorted(records, key=lambda s: int(s["id"]))
    passages = [p for p in (make_passage(run) for run in _runs(sentences, r)) if _eligible(p)]
    picked = common.sample_sorted(passages, N_PASSAGES, r, key=lambda p: int(p["ids"][0]))
    rows = []
    for p in picked:
        fields, gold = choose_fields(p, r)
        meta = {"source": SOURCE, "split": SPLIT, "source_id": ",".join(p["ids"]),
                "license": LICENSE}
        rows.append(common.make_row(NAME, len(rows), p["state"], fields, gold, meta))
    return common.take(rows, limit)


def build(limit: int | None = None) -> list[dict]:
    with common.temp_hf_cache(NAME) as d:
        records = load_source(d)
    return convert(records, limit)
