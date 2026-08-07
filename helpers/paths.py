from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root from a script or notebook location."""
    current = (start or Path.cwd()).resolve()

    for candidate in (current, *current.parents):
        if (
            (candidate / "run_pipeline.py").exists()
            and (candidate / "data").is_dir()
        ):
            return candidate

    raise FileNotFoundError(
        f"Could not locate the repository root from {current}"
    )


ROOT = find_repo_root()
DATA = ROOT / "data"
RAW = DATA / "raw"
CLEAN = DATA / "clean"
PROCESSED = DATA / "processed"
CONFIG_DIR = ROOT / "config"
OUTPUTS = ROOT / "outputs"
CANDIDATE_PROFILES = ROOT / "candidate_profiles"
