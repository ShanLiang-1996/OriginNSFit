from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd

from .data_loader import discover_files, read_table, sn_xy_columns
from .fitting import fit_sn_exponential
from .origin_client import OriginAutomationError, OriginClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origin-ns-fit",
        description="Batch read S-N data, fit exponential curves, and plot with Origin.",
    )
    parser.add_argument("--input", type=Path, default=Path("data"), help="Input data directory.")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="File glob pattern. Can be passed multiple times.",
    )
    parser.add_argument("--life", "--x", dest="life", help="Life/N column. Defaults to 寿命.")
    parser.add_argument(
        "--response",
        "--y",
        dest="response",
        help="Stress/strain response column. Defaults to 应变幅/应力幅.",
    )
    parser.add_argument("--fit-points", type=int, default=300, help="Number of fit curve points.")
    parser.add_argument("--symbol-kind", type=int, default=3, help="Origin symbol kind for data points.")
    parser.add_argument("--dry-run", action="store_true", help="Skip Origin automation.")
    parser.add_argument("--hidden-origin", action="store_true", help="Do not show Origin UI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_dir: Path = args.input
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"

    patterns = args.pattern or ["*.csv", "*.tsv", "*.txt", "*.xlsx", "*.xls"]
    files = discover_files(input_dir, patterns)
    if not files:
        print(f"No supported data files found in {input_dir}.")
        return 1

    summaries: list[dict[str, object]] = []
    curves: list[pd.DataFrame] = []
    plot_jobs: list[dict[str, object]] = []

    for path in files:
        for table in read_table(path):
            life_column, response_column = sn_xy_columns(table.frame, args.life, args.response)
            fit = fit_sn_exponential(
                table.frame,
                life_column,
                response_column,
                fit_points=args.fit_points,
            )
            label = _safe_name(table.label)

            curve = fit.curve.copy()
            curve.insert(0, "file", str(path))
            curve.insert(1, "sheet", table.sheet or "")
            curve.insert(2, "group", table.group or "")
            curves.append(curve)

            summary_index = len(summaries)
            summaries.append(
                {
                    "file": str(path),
                    "sheet": table.sheet or "",
                    "group": table.group or "",
                    "life_column": life_column,
                    "response_column": response_column,
                    "points": fit.result.points,
                    "model": "response = a * exp(b * log10(life))",
                    "coefficient_a": fit.result.coefficient_a,
                    "coefficient_b": fit.result.coefficient_b,
                    "r2": fit.result.r2,
                    "rmse": fit.result.rmse,
                    "life_min": fit.result.life_min,
                    "life_max": fit.result.life_max,
                    "response_min": fit.result.response_min,
                    "response_max": fit.result.response_max,
                    "formula": fit.result.formula,
                    "figure": "",
                }
            )
            plot_jobs.append(
                {
                    "summary_index": summary_index,
                    "fit": fit,
                    "life_column": life_column,
                    "response_column": response_column,
                    "output_path": figures_dir / f"{label}.png",
                    "title": table.group or table.sheet or path.stem,
                    "label": table.label,
                }
            )

    origin = None
    if not args.dry_run:
        try:
            origin = OriginClient(visible=not args.hidden_origin).__enter__()
            for job in plot_jobs:
                try:
                    figure_path = origin.plot_sn_curve(
                        job["fit"],
                        str(job["life_column"]),
                        str(job["response_column"]),
                        job["output_path"],
                        title=str(job["title"]),
                        symbol_kind=args.symbol_kind,
                    )
                    summaries[int(job["summary_index"])]["figure"] = str(figure_path)
                except Exception as exc:
                    print(f"Origin plotting failed for {job['label']}: {exc}")
        except OriginAutomationError as exc:
            print(f"Origin automation disabled: {exc}")
        finally:
            if origin is not None:
                origin.__exit__(None, None, None)

    summary_path = output_dir / "fit_summary.csv"
    pd.DataFrame(summaries).to_csv(summary_path, index=False, encoding="utf-8-sig")
    curves_path = output_dir / "fit_curves.csv"
    if curves:
        pd.concat(curves, ignore_index=True).to_csv(curves_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {summary_path}")
    if curves:
        print(f"Wrote {curves_path}")
    return 0


def _safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\s]+', "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "sn_curve"
