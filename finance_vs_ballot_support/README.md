# Finance vs. ballot support

## Question / purpose

Does campaign finance (fundraising and spending) predict ballot support
(mentions, first-place votes) in the 2024 election? Ballot support only
exists for 2024, so this topic is 2024-only until 2026 results exist.

## Main data sources

- `data/processed/fundraising/2024/`, `data/processed/spending/2024/` —
  candidate finance profiles.
- `data/processed/ballot_support/2024/candidate_ballot_support_2024.csv` —
  electoral outcomes (mentions, first-place votes).
- `data/clean/portland_contributions/contributions.csv` — used directly
  by the correlation-screening notebook.

## Relevant processed datasets

- `data/processed/finance_vs_ballot_support/2024/` — reusable merged
  candidate-level tables (finance totals/bins joined to ballot support):
  `candidate_finance_ballot_analysis_2024.csv`,
  `candidate_spending_ballot_analysis_2024.csv`,
  `spending_purpose_ballot_detail_2024.csv`.
- `data/processed/ballot_support/2024/` also holds the correlation and
  univariate-regression *result* tables from the same scripts (not
  reusable input data, so they stay separate from the merged tables above).
- `data/processed/finance_analysis/correlation_screens/openelections_contributions/`
  — output of the notebook below. **CURATE LATER**: not yet folded into
  this topic's canonical datasets; still under review.

## Main notebooks

- `notebooks/01_openelections_contribution_correlations.ipynb`

## Relevant builder scripts

- `scripts/09_build_finance_ballot_analysis.py`
- `scripts/10_build_spending_purpose_ballot_analysis.py`

## Also here

- `FINDINGS_MEMO.md` — the living findings memo for this analysis
  (originally Workplan Question 3).
