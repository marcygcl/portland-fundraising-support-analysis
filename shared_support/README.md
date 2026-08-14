# Shared support (VoteKit boost matrices)

## Question / purpose

Do Portland's ranked-choice ballots show candidates whose support
co-occurs? The "boost" of candidate *i* given candidate *j*,
`boost(i | j)`, asks how much mentioning *j* on a ballot changes the
probability that the same ballot also mentions *i*. This is directional
and about **voter behavior on the ballot**, not about fundraising.

Not to be confused with [`profile_vectors_pam/`](../profile_vectors_pam/README.md),
which compares candidates by their fundraising profiles instead.

## Main data sources

- `data/raw/report2025/2024/cleaned_votekit_profiles/` — VoteKit ballot
  preference profiles by district.
- `data/raw/report2025/shapefiles/` — precinct/block shapefiles used to
  reconstruct ballots.

## Relevant processed datasets

- `data/processed/boost/2024/` — `boost_matrix_D{1..4}.csv`,
  `boost_directional_long.csv`, `boost_pairs.csv`, `candidate_index.csv`.

## Main notebooks

None yet. This topic currently only has a builder script; no notebook
analyzes the boost matrices.

## Relevant builder scripts

- `scripts/03_build_boost_matrices.py`
