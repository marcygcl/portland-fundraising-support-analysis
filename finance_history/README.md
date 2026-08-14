# Finance history

## Question / purpose

How have Portland City Council fundraising and spending totals changed
across election years? This topic looks across years rather than within
a single one, so it sits apart from `fundraising/` and `spending/`
(which each cover one year/contest at a time).

## Main data sources

- `data/clean/orestar/**/city_council/transactions.csv` — cleaned ORESTAR
  transactions across all available years.

## Relevant processed datasets

- `data/processed/finance_history/city_council/` — `year_finance_summary.csv`,
  `candidate_year_finance.csv`, and transaction descriptive tables.

## Main notebooks

- `notebooks/01_city_council_finance_history.ipynb`

## Relevant builder scripts

None specific to this topic — it's built directly from the shared
`scripts/04_clean_orestar.py` output.
