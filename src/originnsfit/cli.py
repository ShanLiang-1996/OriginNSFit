from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .data_loader import discover_files, numeric_xy_columns, read_table
from .fitting import linear_fit
from .origin_client import OriginAutomationError, OriginClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origin-ns-fit",
        description="Batch read data, fit X/Y columns, and optionally plot with Origin.",
    )
    parser.add_argument("--input", type=Path, default=Path("data"), help="Input data directory.")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="File glob pattern. Can be passed multiple times.",
    )
    parser.add_argument("--x", help="X column name. Defaults to first numeric column.")
    parser.add_argument("--y", help="Y column name. Defaults to second numeric column.")
    parser.add_argument("--dry-run", action="store_true", help="Skip Origin automation.")
    parser.add_argument("--hidden-origin", action="store_true", help="Do not show Origin UI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_dir: Path = args.input
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    patterns = args.pattern or ["*.csv", "*.tsv", "*.txt", "*.xlsx", "*.xls"]
    files = discover_files(input_dir, patterns)
    if not files:
        print(f"No supported data files found in {input_dir}.")
        return 1

    summaries: list[dict[str, object]] = []
    origin = None
    if not args.dry_run:
        try:
            origin = OriginClient(visible=not args.hidden_origin).__enter__()
        except OriginAutomationError as exc:
            print(f"Origin automation disabled: {exc}")

    try:
        for path in files:
            for table in read_table(path):
                x_column, y_column = numeric_xy_columns(table.frame, args.x, args.y)
                result = linear_fit(table.frame, x_column, y_column)
                label = path.stem if table.sheet is None else f"{path.stem}_{table.sheet}"

                figure_path = ""
                if origin is not None:
                    figure_path = str(origin.plot_xy(table.frame, x_column, y_column, output_dir / f"{label}.png"))

                summaries.append(
                    {
                        "file": str(path),
                        "sheet": table.sheet or "",
                        "x": x_column,
                        "y": y_column,
                        "points": result.points,
                        "model": "linear",
                        "slope": result.slope,
                        "intercept": result.intercept,
                        "r2": result.r2,
                        "figure": figure_path,
                    }
                )
    finally:
        if origin is not None:
            origin.__exit__(None, None, None)

    summary_path = output_dir / "fit_summary.csv"
    pd.DataFrame(summaries).to_csv(summary_path, index=False)
    print(f"Wrote {summary_path}")
    return 0
