# Candidate Profiles

Human-curated qualitative profiles for 2024 and 2026 Portland City Council
candidates.

After the candidate master exists:

```bash
uv run python scripts/08_initialize_candidate_profiles.py --year 2024
uv run python scripts/08_initialize_candidate_profiles.py --year 2026
```

The initializer never overwrites an existing candidate Markdown file.

Keep factual claims sourced and separate source-derived facts from interpretation.
