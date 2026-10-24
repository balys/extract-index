"""Publish the suite, a run and the leaderboard page to the Hugging Face Hub (maintainers only).

    python scripts/publish_hub.py suite   # suite-0.1/ -> datasets/balys/extract-index-suite
    python scripts/publish_hub.py space   # space/     -> spaces/balys/extract-index (static)
    python scripts/publish_hub.py run runs/clairic balys/extract-index-run-clairic-preview

Repos are created public. Needs HF_TOKEN with write access.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE_REPO = "balys/extract-index-suite"
SPACE_REPO = "balys/extract-index"
GITHUB = "https://github.com/balys/extract-index"
SPACE_URL = f"https://huggingface.co/spaces/{SPACE_REPO}"


def suite_card(manifest: dict) -> str:
    configs = "\n".join(f"- config_name: {n}\n  data_files: {t['file']}" for n, t in manifest["tests"].items())
    rows = "\n".join(
        f"| `{n}` | {t['area']} | {t['requests']:,} | {t['fields']:,} | {', '.join(t['types'])} | "
        f"{round(100 * t['null_share'])}% | {t['license']} | [{t['source']}]({t['url']}) |"
        for n, t in manifest["tests"].items())
    return f"""---
license: other
license_name: per-test
license_link: {GITHUB}#licence
pretty_name: SystemOne Extract Index suite {manifest['edition']}
language:
- en
tags:
- extraction
- information-extraction
- benchmark
size_categories:
- 1K<n<10K
viewer: false
configs:
{configs}
---

# SystemOne Extract Index: suite {manifest['edition']}

The frozen test suite of the [SystemOne Extract Index]({SPACE_URL}). It measures one-pass typed
extraction: a model reads a document (`state`) and a map of typed `fields`, and returns a value
or `null` for each field. The kit, scorer and rules are at <{GITHUB}>.

| Test | Area | Requests | Fields | Field types | Gold null | Licence | Source |
|---|---|---:|---:|---|---:|---|---|
{rows}

Total: {manifest['totals']['requests']:,} requests, {manifest['totals']['fields']:,} fields.

## Files

- `<test>.jsonl.gz`: one row per line, `{{"id", "test", "request", "gold", "meta"}}`. Engines see only
  `request` (`state`, `fields`, optional `reference_date`). `gold[field].value` is the expected
  value (`null` when the document does not determine it), with optional `alternatives` and, for
  lists, `item_alternatives`.
- `manifest.json`: counts, field types, null share, source dataset and pinned revision, licence
  and sha256 of every file. Runs record the manifest's sha256, and the board accepts only runs on
  this exact suite.

The files are rebuilt byte for byte from the public sources with
`python -m extract_index suite build` (seed {manifest['seed']}, pinned dataset revisions).

## Rules

Don't train on these rows or on the `docs` generator's templates. Use one configuration for every
test, with no truncation. See the kit README for the full rules and how to submit.

## Licences

Each test keeps its source's licence (table above). `docs` is our own synthetic set (CC BY 4.0).
Please cite the original datasets when you use their tests.
"""


def publish_suite(api) -> None:
    suite = ROOT / "suite-0.1"
    check = subprocess.run([sys.executable, "-m", "extract_index", "suite", "verify", "--dir", str(suite)],
                           cwd=ROOT)
    if check.returncode != 0:
        sys.exit("suite verify failed; not publishing")
    manifest = json.loads((suite / "manifest.json").read_text())
    if manifest.get("partial"):
        sys.exit("suite-0.1 is a partial build; not publishing")
    api.create_repo(SUITE_REPO, repo_type="dataset", private=False, exist_ok=True)
    (suite / "README.md").write_text(suite_card(manifest))
    try:
        api.upload_folder(repo_id=SUITE_REPO, repo_type="dataset", folder_path=str(suite),
                          allow_patterns=["*.jsonl.gz", "manifest.json", "README.md"],
                          commit_message=f"Suite {manifest['edition']}")
    finally:
        (suite / "README.md").unlink()
    print(f"suite -> https://huggingface.co/datasets/{SUITE_REPO}")


def publish_space(api) -> None:
    api.create_repo(SPACE_REPO, repo_type="space", space_sdk="static", private=False, exist_ok=True)
    api.upload_folder(repo_id=SPACE_REPO, repo_type="space", folder_path=str(ROOT / "space"),
                      commit_message="Leaderboard page")
    print(f"space -> {SPACE_URL}")


def publish_run(run_dir: str, repo: str) -> None:
    cmd = [sys.executable, "-m", "extract_index", "upload", "--run", run_dir, "--repo", repo, "--public"]
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        sys.exit(f"upload of {run_dir} failed")


def main(argv: list[str]) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    what = argv[0] if argv else ""
    if what == "suite":
        publish_suite(api)
    elif what == "space":
        publish_space(api)
    elif what == "run" and len(argv) == 3:
        publish_run(argv[1], argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
