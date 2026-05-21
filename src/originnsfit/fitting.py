from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LinearFitResult:
    slope: float
    intercept: float
    r2: float
    points: int


def linear_fit(frame: pd.DataFrame, x_column: str, y_column: str) -> LinearFitResult:
    data = frame[[x_column, y_column]].dropna()
    if len(data) < 2:
        raise ValueError("At least two valid points are required for linear fitting.")

    x = data[x_column].to_numpy(dtype=float)
    y = data[y_column].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    residual_sum = float(np.sum((y - y_hat) ** 2))
    total_sum = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 if total_sum == 0 else 1.0 - residual_sum / total_sum
    return LinearFitResult(float(slope), float(intercept), float(r2), int(len(data)))
