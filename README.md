# SystemOne Extract Index

A public benchmark for one-pass ("System One") extraction models. A model reads a document and a
map of typed fields, and returns a typed value, or `null`, for each field. The suite is frozen,
every run's results are public, and new entries come in by pull request.

- Leaderboard: <https://huggingface.co/spaces/balys/extract-index>
- Suite (frozen files + manifest): <https://huggingface.co/datasets/balys/extract-index-suite>
- Edition: 0.1

The kit follows the [Decision Index](https://github.com/apolinario/decision-index) kit: a frozen
suite, thin engines, a resumable runner, a scorer, and a static leaderboard built only from
`scores.json` files.

## Tests

<!-- tests-table:start -->
| Test | Area | Source (split) | Requests | Fields | Field types | Gold null | Licence |
|---|---|---|---:|---:|---|---:|---|
| `squad2` | Spans | [SQuAD 2.0 (validation)](https://rajpurkar.github.io/SQuAD-explorer/) | 300 | 2,909 | text | 50% | CC BY-SA 4.0 |
| `cuad` | Spans | [CUAD (test)](https://www.atticusprojectai.org/cuad) | 250 | 992 | text, list | 45% | CC BY 4.0 |
| `cord` | Documents | [CORD v2 (test + validation)](https://github.com/clovaai/cord) | 197 | 1,166 | number, list | 33% | CC BY 4.0 |
| `docs` | Documents | [synthetic business documents (ours)](https://github.com/balys/extract-index) | 400 | 2,813 | text, number, date, time, datetime, duration, list | 22% | CC BY 4.0 |
| `drop` | Numbers | [DROP (validation)](https://allenai.org/data/drop) | 300 | 1,380 | text, number, date, list | 0% | CC BY-SA 4.0 |
| `tatqa` | Numbers | [TAT-QA (dev)](https://nextplusplus.github.io/TAT-QA/) | 250 | 1,500 | text, number, list | 0% | CC BY 4.0 |
| `fewnerd` | Entities | [Few-NERD supervised (test)](https://ningding97.github.io/fewnerd/) | 300 | 1,517 | list | 43% | CC BY-SA 4.0 |
| **Total** | | | **1,997** | **12,277** | | | |
<!-- tests-table:end -->

`suite-0.1/manifest.json` has the exact counts, field types, null share, source revision and
sha256 of every file.

The `docs` generator (`extract_index/suite/docs.py`) is public so anyone can check its labels.
Don't train on it (see Rules).

## Request and answer

The field specs are the same as Cloudflare's Clairic (`@cf/cloudflare/clairic`), so engines stay
thin.

```json
{
  "state": "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. ...",
  "fields": {
    "invoice_number": {"type": "text"},
    "due_date": {"type": "date", "instructions": "Issue date plus the net payment days"},
    "total": {"type": "number", "decimals": 2, "unit": "USD", "instructions": "Amount due including shipping"},
    "contacts": {"type": "list", "items": "text"},
    "po_number": {"type": "text", "instructions": "Purchase order number"}
  },
  "reference_date": "2026-09-02"
}
```

```json
{"answers": {
  "invoice_number": {"type": "text", "value": "INV-2291", "span": [8, 16], "p_null": 0.0},
  "due_date": {"type": "date", "value": "2026-10-02"},
  "total": {"type": "number", "value": 1080.0},
  "contacts": {"type": "list", "value": ["Dana Ruiz", "Priya Shah"]},
  "po_number": {"type": "text", "value": null, "p_null": 1.0}
}}
```

- **Field types:** `text`, `number`, `date`, `time`, `datetime`, `duration` and `list` (items `text`, `number` or `date`).
- **Field options:** `instructions`, `unit`, `integer`, `decimals` and `items`.
- **Answers:** every requested field must be answered. `value` is `null` when the document does not determine it.
- **Value forms:**
  - `date`: `YYYY-MM-DD`;
  - `time`: `HH:MM[:SS]`;
  - `datetime`: `YYYY-MM-DDTHH:MM[:SS]`;
  - numbers and durations: numbers, durations in the field's `unit`;
  - lists: arrays.
- **Optional extras:** `p_null`, `confidence` and `span(s)`. They feed the null-calibration metrics only, never the index.

## Scoring

Each field scores between 0 and 1:

| Case | Score |
|---|---|
| Gold `null` | 1 if the answer is `null` (or `[]` for a list) |
| Gold has a value, answer `null` | 0 |
| `text` | best SQuAD token F1 over the gold value and its alternatives |
| `number`, `duration` | 1 if within half a unit of the field's `decimals` (or 1e-6 relative with no `decimals`); `,` thousands separators, `%` and currency symbols are stripped |
| `date` | exact |
| `time` | exact to the minute (seconds count only if gold has them) |
| `datetime` | exact to the minute |
| `list` | multiset F1 over items (a text item matches at token F1 ≥ 0.5) |
| Unsupported request, error, missing field, wrong value form | 0 |

- **Test score:** the mean field score × 100.
- **Index:** the mean of the 7 test scores.
- **Also reported:**
  - per-area scores;
  - per-type scores;
  - null precision and recall;
  - latency per request (median, mean and p80).

## Run it

```bash
pip install -e ".[build,test]"
python -m extract_index suite download            # or: suite build (rebuilds from the public sources)
python -m extract_index suite verify
python -m extract_index pipeline --engine null --out runs/null --compact
```

Built-in engines:

| Engine | What it calls |
|---|---|
| `http` | your server at `POST {base_url}/v1/extract` in the format above (`--option base_url=...`, bearer token from `EXTRACT_INDEX_API_KEY`) |
| `clairic` | Cloudflare Workers AI (`CLOUDFLARE_API_TOKEN`, optional `CLOUDFLARE_ACCOUNT_ID`) |
| `openai_json` | an OpenAI-compatible chat model writing JSON. This is a System Two reference, never ranked. |
| `null` | answers `null` everywhere |
| `module:Class` | your own subclass of `extract_index.engines.Engine` |

How a run works:

- It is resumable: rerun the same command and only missing or failed rows are sent again.
- Requests go one at a time, so latency is per request.
- `scores.json` has `complete: true` once every row is `ok` or `unsupported`.

## Rules

- No truncation. Use one configuration for every test, with no per-test prompt tuning.
- Don't train on the suite's rows or on the `docs` generator's templates.
- A System One listing reads the input in a single pass per field group and generates no tokens.
  Generating (System Two) models may be shown as reference rows, but they are not ranked.

## Submit

1. Run the full suite with one fixed configuration: `python -m extract_index pipeline --engine ... --out runs/<name> --compact`.
   Check that `runs/<name>/scores.json` has `complete: true`.
2. Upload the run to a Hub dataset: `python -m extract_index upload --run runs/<name> --repo <you>/<name> --public`.
3. Open a pull request adding one row to [`submissions/README.md`](submissions/README.md). The row gives:
   - the model, and whether it is open weights or an API;
   - the results link;
   - the engine and kit commit;
   - the hardware;
   - the exact options;
   - any declared limits.

The maintainers re-run open-weights entries on one NVIDIA RTX PRO 6000 to confirm their scores and
latency.

## Disclosure

Maintained by [Turion AI](https://turion.ai). The maintainers also submit their own models. All code,
the suite and every run's results are public, so anyone can check them.

## Licence

The code is MIT. Each test keeps its source dataset's licence (see the table above and the
manifest). The `docs` test is CC BY 4.0.
