from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


def _cross_process_fingerprint(hash_seed: str, repository_root: Path) -> str:
    script = """
import hashlib
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from tuva_synthetic.io import write_tables
from tuva_synthetic.pipeline import build_payer_dataset

root = Path.cwd()
generated = build_payer_dataset(
    payer='aetna', member_count=100, start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31), seed=20260829,
    schema_root=root / 'schemas', issue_profile='connector_eval',
)
with TemporaryDirectory() as directory:
    paths = write_tables(generated.tables, Path(directory))
    digest = hashlib.sha256()
    for name, path in sorted(paths.items()):
        digest.update(name.encode())
        digest.update(path.read_bytes())
    print(digest.hexdigest())
"""
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_generation_is_deterministic_across_python_hash_seeds() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    assert _cross_process_fingerprint("1", repository_root) == _cross_process_fingerprint(
        "8675309", repository_root
    )
