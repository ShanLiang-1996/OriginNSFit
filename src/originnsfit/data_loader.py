from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".xls", ".xlsx"}


@dataclass(frozen=True)
class DataTable:
    source: Path
    frame: pd.DataFrame
    sheet: str | None = None


def discover_files(input_dir: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(input_dir.rglob(pattern))
    return sorted(
        {
            path
            for path in files
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        }
    )


def read_table(path: Path) -> list[DataTable]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return [DataTable(path, pd.read_csv(path))]
    if suffix == ".tsv":
        return [DataTable(path, pd.read_csv(path, sep="\t"))]
    if suffix == ".txt":
        return [DataTable(path, pd.read_csv(path, sep=None, engine="python"))]
    if suffix in {".xls", ".xlsx"}:
        sheets = pd.read_excel(path, sheet_name=None)
        return [DataTable(path, frame, sheet=name) for name, frame in sheets.items()]
    raise ValueError(f"Unsupported file type: {path}")


def numeric_xy_columns(frame: pd.DataFrame, x: str | None, y: str | None) -> tuple[str, str]:
    if x and y:
        return x, y

    numeric_columns = list(frame.select_dtypes(include="number").columns)
    if x:
        candidates = [column for column in numeric_columns if column != x]
        if not candidates:
            raise ValueError("Need at least one numeric Y column.")
        return x, y or candidates[0]
    if y:
        candidates = [column for column in numeric_columns if column != y]
        if not candidates:
            raise ValueError("Need at least one numeric X column.")
        return candidates[0], y
    if len(numeric_columns) < 2:
        raise ValueError("Need at least two numeric columns for X/Y fitting.")
    return numeric_columns[0], numeric_columns[1]
