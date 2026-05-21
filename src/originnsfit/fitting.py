from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


@dataclass(frozen=True)
class SNCurveFitResult:
    coefficient_a: float
    coefficient_b: float
    r2: float
    rmse: float
    points: int
    life_min: float
    life_max: float
    response_min: float
    response_max: float
    formula: str


@dataclass(frozen=True)
class SNCurveFit:
    result: SNCurveFitResult
    data: pd.DataFrame
    curve: pd.DataFrame


def sn_exponential_model(life: np.ndarray, coefficient_a: float, coefficient_b: float) -> np.ndarray:
    return coefficient_a * np.exp(coefficient_b * np.log10(life))


def fit_sn_exponential(
    frame: pd.DataFrame,
    life_column: str,
    response_column: str,
    fit_points: int = 300,
) -> SNCurveFit:
    data = frame[[life_column, response_column]].copy()
    data[life_column] = pd.to_numeric(data[life_column], errors="coerce")
    data[response_column] = pd.to_numeric(data[response_column], errors="coerce")
    data = data.dropna()
    data = data[(data[life_column] > 0) & (data[response_column] > 0)]
    data = data.sort_values(life_column).reset_index(drop=True)

    if len(data) < 2:
        raise ValueError("At least two positive S-N points are required for exponential fitting.")

    life = data[life_column].to_numpy(dtype=float)
    response = data[response_column].to_numpy(dtype=float)
    log_life = np.log10(life)

    slope, intercept = np.polyfit(log_life, np.log(response), deg=1)
    initial_a = float(np.exp(intercept))
    initial_b = float(slope)

    coefficients, _ = curve_fit(
        lambda x, coefficient_a, coefficient_b: coefficient_a * np.exp(coefficient_b * x),
        log_life,
        response,
        p0=(initial_a, initial_b),
        maxfev=10000,
    )
    coefficient_a = float(coefficients[0])
    coefficient_b = float(coefficients[1])

    predicted = sn_exponential_model(life, coefficient_a, coefficient_b)
    residual_sum = float(np.sum((response - predicted) ** 2))
    total_sum = float(np.sum((response - np.mean(response)) ** 2))
    r2 = 1.0 if total_sum == 0 else 1.0 - residual_sum / total_sum
    rmse = float(np.sqrt(np.mean((response - predicted) ** 2)))

    life_fit = np.logspace(np.log10(life.min()), np.log10(life.max()), fit_points)
    response_fit = sn_exponential_model(life_fit, coefficient_a, coefficient_b)
    formula = f"{response_column} = {coefficient_a:.6g} * exp({coefficient_b:.6g} * log10({life_column}))"

    curve = pd.DataFrame(
        {
            life_column: life_fit,
            response_column: response_fit,
        }
    )
    result = SNCurveFitResult(
        coefficient_a=coefficient_a,
        coefficient_b=coefficient_b,
        r2=float(r2),
        rmse=rmse,
        points=int(len(data)),
        life_min=float(life.min()),
        life_max=float(life.max()),
        response_min=float(response.min()),
        response_max=float(response.max()),
        formula=formula,
    )
    return SNCurveFit(result=result, data=data, curve=curve)
