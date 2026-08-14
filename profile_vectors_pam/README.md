# Profile vectors / PAM

## Question / purpose

Which candidates have *similar fundraising profiles*, and does that
similarity relate to electoral support? The approach: represent each
candidate's fundraising profile as a vector (e.g. contribution-bin
shares), compute distances between candidates, cluster with PAM
(Partitioning Around Medoids / k-medoids), and visualize with MDS.

Not to be confused with [`shared_support/`](../shared_support/README.md),
which is about VoteKit boost matrices / co-occurring ballot support, not
fundraising similarity.

## Status

**Not built yet.** No notebooks, scripts, or processed data exist for
this topic. The `kmedoids` dependency is already in `pyproject.toml` in
anticipation of this work.

## Main data sources (planned)

- `data/processed/fundraising/` — candidate fundraising profiles, the
  input this topic will vectorize.
- `data/processed/ballot_support/` — for comparing clusters to support.

## Relevant processed datasets (planned)

- `data/processed/profile_vectors/` — not created yet.
