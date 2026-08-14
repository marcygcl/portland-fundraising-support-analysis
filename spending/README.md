# Spending

## Question / purpose

How much did each candidate spend, and in what expenditure-size bins
(Micro–Mega)? Covers Portland City Council (2024, 2026) and County
Commissioner (2026).

## Main data sources

- `data/clean/orestar/{year}/{contest_type}/transactions.csv` — ORESTAR
  campaign-finance filings (reported expenditures).
- `data/processed/candidates/` — candidate crosswalk, to attach a
  `candidate_key` to each source.

## Relevant processed datasets

- `data/processed/spending/2024/city_council/`
- `data/processed/spending/2026/city_council/`
- `data/processed/spending/2026/county_commissioner/`

## Main notebooks

- `notebooks/01_orestar_city_council_spending_2024.ipynb`
- `notebooks/02_orestar_city_council_spending_2026.ipynb`
- `notebooks/03_county_commissioner_spending_2026.ipynb`

## Relevant builder scripts

- `scripts/04_clean_orestar.py`
