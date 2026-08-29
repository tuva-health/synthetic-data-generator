from pathlib import Path

from tuva_synthetic.cli import REPOSITORY_ROOT, _portable_path


def test_default_report_paths_are_repository_relative() -> None:
    path = REPOSITORY_ROOT / "data" / "generated" / "aetna" / "claims.csv.gz"

    assert _portable_path(path) == "data/generated/aetna/claims.csv.gz"


def test_explicit_external_report_paths_remain_absolute(tmp_path: Path) -> None:
    path = tmp_path / "claims.csv.gz"

    assert _portable_path(path) == str(path.resolve())
