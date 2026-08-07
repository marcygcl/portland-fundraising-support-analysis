# UV setup

From the repository root:

```bash
uv sync
```

Then:

```bash
uv run python run_pipeline.py
uv run jupyter lab
```

This starter archive does not include `uv.lock` because the build environment
cannot access the package registry. Your first successful `uv sync` will create
it. Commit `uv.lock` afterward for reproducibility.
