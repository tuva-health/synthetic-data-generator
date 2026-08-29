"""Command-line interface."""

from __future__ import annotations

import argparse
import gc
import json
from datetime import date
from pathlib import Path

from tuva_synthetic.io import write_issue_manifest, write_tables, write_validation_report
from tuva_synthetic.pipeline import build_payer_dataset
from tuva_synthetic.validation import summarize


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PAYERS = ("aetna", "priority_health", "hcci")


def _portable_path(path: Path) -> str:
    """Keep default reports portable while preserving explicit external paths."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(resolved)


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuva-synthetic",
        description="Generate payer-shaped synthetic claims data files.",
    )
    parser.add_argument("--payer", choices=("all", *PAYERS), default="all")
    parser.add_argument("--members", type=int, default=10_000)
    parser.add_argument("--start-date", type=_iso_date, default=date(2024, 1, 1))
    parser.add_argument("--end-date", type=_iso_date, default=date(2025, 12, 31))
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--issue-profile", choices=("connector_eval", "none"), default="connector_eval")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "data" / "generated")
    parser.add_argument("--reports-dir", type=Path, default=REPOSITORY_ROOT / "reports" / "generated")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.members <= 0:
        raise SystemExit("--members must be positive")
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")
    payers = PAYERS if args.payer == "all" else (args.payer,)
    consolidated: dict[str, object] = {}
    for payer in payers:
        print(f"Generating {payer} ({args.members:,} members)...", flush=True)
        generated = build_payer_dataset(
            payer=payer, member_count=args.members, start_date=args.start_date,
            end_date=args.end_date, seed=args.seed,
            schema_root=REPOSITORY_ROOT / "schemas", issue_profile=args.issue_profile,
        )
        payer_output = args.output_dir / payer
        payer_reports = args.reports_dir / payer
        paths = write_tables(generated.tables, payer_output)
        manifest_path = write_issue_manifest(
            generated.issue_manifest, payer_reports / "issue_manifest.csv"
        )
        row_counts = {table.name: len(table.rows) for table in generated.tables}
        report_path = write_validation_report(
            payer=payer, summary=summarize(generated.canonical),
            results=generated.validations, row_counts=row_counts,
            path=payer_reports / "validation_report.json",
        )
        consolidated[payer] = {
            "files": {name: _portable_path(path) for name, path in paths.items()},
            "row_counts": row_counts,
            "issue_count": len(generated.issue_manifest),
            "private_issue_manifest": _portable_path(manifest_path),
            "validation_report": _portable_path(report_path),
        }
        print(
            f"Completed {payer}: {sum(row_counts.values()):,} rows across "
            f"{len(row_counts)} tables; {len(generated.issue_manifest):,} documented issues.",
            flush=True,
        )
        # A 10,000-member payer build deliberately materializes both the
        # canonical cohort and its wide payer projection.  Release those rows
        # before the next payer is constructed so `--payer all` does not retain
        # two complete datasets during the assignment of the next iteration.
        del generated
        gc.collect()
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    run_report = args.reports_dir / "run_report.json"
    run_report.write_text(json.dumps(consolidated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Run report: {run_report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
