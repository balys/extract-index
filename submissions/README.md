# Submissions

One row per submitted run. The board (`space/data/board.json`) is built only from
`submissions/entries.json` and the `scores.json` each entry points to; nothing on the page is
typed in by hand.

| Model | Weights or API | Results | Engine and commit | Hardware | Options | Declared limits |
|---|---|---|---|---|---|---|
| Clairic (preview), Cloudflare | API, `@cf/cloudflare/clairic` | [balys/extract-index-run-clairic-preview](https://huggingface.co/datasets/balys/extract-index-run-clairic-preview) | `clairic` at `151f52a` | Cloudflare Workers AI (REST API, called from Europe) | none (defaults) | 65,536-token context, 8,192-token passes |

## How to submit

1. Get the frozen suite and check it:
   `python -m extract_index suite download` then `python -m extract_index suite verify`.
2. Run every test with one configuration (no truncation, no per-test tuning):
   `python -m extract_index pipeline --engine <name|module:Class> --option k=v ... --compact --out runs/<name>`.
   The run resumes if interrupted; rerun the same command until `scores.json` says `"complete": true`
   (rows the engine declines with `Unsupported` count as answered and score 0).
3. Upload the run: `python -m extract_index upload --run runs/<name> --repo <user>/<name> --public`.
   This puts `results.jsonl`, `scores.json` and `environment.json` in a Hub dataset.
4. Open a pull request that adds:
   - a row to the table above: the model, whether the weights are public (with a link) or it is an
     API, the results dataset link, the engine spec and kit commit (from `environment.json`), the
     hardware, the exact `--option` values, and the model's declared limits (context, pass size);
   - an entry to `submissions/entries.json`:
     ```json
     {"name": "My Model 1.0", "org": "Me", "kind": "open", "system": "one",
      "scores": "https://huggingface.co/datasets/<user>/<name>/resolve/main/scores.json",
      "hardware": "1x NVIDIA RTX PRO 6000",
      "links": {"model": "...", "results": "https://huggingface.co/datasets/<user>/<name>", "submission": "<PR URL>"},
      "date": "YYYY-MM-DD", "notes": "..."}
     ```
     `kind` is `open` (weights public) or `api`; `system` is `one` (one pass, no generated tokens;
     ranked) or `two` (a generating model; shown as a reference row, not ranked).
5. The maintainers rebuild the board with
   `python -m extract_index board --entries submissions/entries.json --manifest suite-0.1/manifest.json --out space/data/board.json`,
   which refuses entries whose `suite_sha256` differs from the suite manifest or whose run is
   incomplete. Open-weights entries are re-run by the maintainers on one NVIDIA RTX PRO 6000 to
   confirm scores and latency.

Do not train on the suite's rows or on the `docs` generator's templates.
