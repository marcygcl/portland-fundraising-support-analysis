# Portland fundraising & support analysis

Campaign-finance and electoral-support research for Portland City Council
(and, starting 2026, County Commissioner) races: who raised and spent
what, how that relates to ballot support, and how candidates' fundraising
profiles and ballot-preference patterns compare to each other.

## How this repo is organized

```text
scripts/          -> code that builds reusable data (raw, clean, processed)
helpers/          -> shared Python code used by scripts and notebooks
data/             -> the datasets themselves (raw / clean / processed)
<topic folders>/  -> notebooks and human-facing analysis, one folder per question
archive/          -> superseded or historical work, kept for reference
```

`scripts/` and `data/` don't belong to any one topic — several topics
reuse the same cleaned ORESTAR transactions or candidate crosswalk.
Topic folders are where you go to *read* an analysis; `scripts/` is
where that analysis's inputs came from.

### `data/`

- `data/raw/` — exactly what was downloaded or scraped, unmodified.
- `data/clean/` — standardized, combined tables straight from raw
  sources (still source-shaped, not yet analysis-shaped).
- `data/processed/` — analysis-ready tables, organized by topic
  (`fundraising/`, `spending/`, `ballot_support/`,
  `finance_vs_ballot_support/`, `boost/`, `finance_history/`,
  `candidates/`). If more than one notebook could reuse a table as
  input, it lives here.

### Topic folders

| Folder | Question |
|---|---|
| [`fundraising/`](fundraising/README.md) | Who raised how much, from whom? |
| [`spending/`](spending/README.md) | Who spent how much, on what? |
| [`profile_vectors_pam/`](profile_vectors_pam/README.md) | Which candidates have similar fundraising profiles? (not built yet) |
| [`shared_support/`](shared_support/README.md) | Which candidates' voter support co-occurs on ranked ballots? |
| [`finance_vs_ballot_support/`](finance_vs_ballot_support/README.md) | Does finance predict ballot support? |
| [`finance_history/`](finance_history/README.md) | How have City Council finances changed over time? |
| [`candidate_profiles/`](candidate_profiles/README.md) | Who are the candidates, qualitatively? |

Each has its own short README with its data sources, relevant processed
datasets, and main notebooks.

### `archive/`

Superseded notebooks and processed-data outputs, kept for provenance
rather than deleted. Nothing here is imported by active code.

## Running the pipeline

```bash
uv sync
uv run python run_pipeline.py
```

`run_pipeline.py` is a switchboard: edit the `RUN` dict to turn stages
on/off and `YEARS` to pick which years to (re)build. Every stage skips
work that already exists unless `FORCE = True`. See `scripts/` for what
each numbered stage does.

## Where to start

- To explore an existing analysis, open a topic folder's README, then
  its `notebooks/`.
- To understand where a processed dataset came from, check the
  topic README's "Relevant builder scripts" and read that script's
  docstring in `scripts/`.
- To add a new source or rebuild existing data, extend `scripts/` and
  register it in `run_pipeline.py`.

See `docs/uv_setup.md` for environment setup details.
