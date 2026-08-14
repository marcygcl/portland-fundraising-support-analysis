# Fundraising

## Question / purpose

How much did each candidate raise, from whom, and in what contribution-size
bins (Micro–Mega)? Covers Portland City Council (2024, 2026) and County
Commissioner (2026).

## Main data sources

- `data/clean/portland_contributions/contributions.csv` — Portland's own
  contributions API (in-district private fundraising).
- `data/clean/orestar/{year}/{contest_type}/transactions.csv` — ORESTAR
  campaign-finance filings.
- `data/processed/candidates/` — candidate crosswalk, to attach a
  `candidate_key` to each source.

## Relevant processed datasets

- `data/processed/fundraising/2024/city_council/`
- `data/processed/fundraising/2026/city_council/`
- `data/processed/fundraising/2026/county_commissioner/`

## Main notebooks

- `notebooks/01_portland_contributions_profiles_2024.ipynb`
- `notebooks/02_orestar_city_council_fundraising_2024.ipynb`
- `notebooks/03_orestar_city_council_fundraising_2026.ipynb`
- `notebooks/04_county_commissioner_fundraising_2026.ipynb`

## Relevant builder scripts

- `scripts/01_download_portland_contributions.py`
- `scripts/02_clean_portland_contributions.py`
- `scripts/04_clean_orestar.py`
