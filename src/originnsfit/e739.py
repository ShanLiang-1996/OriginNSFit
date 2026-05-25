from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats


E739Transform = Literal["log", "linear"]

FAILURE_STATUS_MARKERS = (
    "failure",
    "failed",
    "fail",
    "fracture",
    "broken",
    "yes",
    "true",
    "1",
)
NON_FAILURE_STATUS_MARKERS = (
    "runout",
    "run-out",
    "run out",
    "suspended",
    "suspension",
    "censored",
    "right-censored",
)


@dataclass(frozen=True)
class E739LinearityTest:
    available: bool
    reason: str
    levels: int
    specimens: int
    lack_of_fit_df: int | None
    pure_error_df: int | None
    lack_of_fit_ss: float | None
    pure_error_ss: float | None
    lack_of_fit_ms: float | None
    pure_error_ms: float | None
    f_statistic: float | None
    f_critical: float | None
    p_value: float | None
    reject_linear_model: bool | None


@dataclass(frozen=True)
class E739FitResult:
    confidence: float
    x_transform: E739Transform
    points: int
    degrees_of_freedom: int
    coefficient_a: float
    coefficient_b: float
    x_mean: float
    y_mean: float
    sxx: float
    sxy: float
    residual_sum_squares: float
    sigma_squared: float
    sigma: float
    r2: float
    rmse_log_life: float
    standard_error_a: float
    standard_error_b: float
    t_critical: float
    f_band_critical: float
    simultaneous_band_factor: float
    coefficient_a_lower: float
    coefficient_a_upper: float
    coefficient_b_lower: float
    coefficient_b_upper: float
    x_min: float
    x_max: float
    life_min: float
    life_max: float
    response_min: float
    response_max: float
    replication_percent: float
    life_response_coefficient_a: float
    life_response_coefficient_b: float
    log_life_formula: str
    life_formula: str
    life_response_formula: str
    response_life_formula: str
    warnings: tuple[str, ...]
    linearity_test: E739LinearityTest


@dataclass(frozen=True)
class E739Fit:
    result: E739FitResult
    data: pd.DataFrame
    curve: pd.DataFrame
    level_stats: pd.DataFrame


def fit_e739(
    frame: pd.DataFrame,
    life_column: str,
    response_column: str,
    *,
    x_transform: E739Transform = "log",
    confidence: float = 0.95,
    fit_points: int = 300,
    status_column: str | None = None,
    level_column: str | None = None,
    replicate_decimals: int = 8,
) -> E739Fit:
    """Fit an ASTM E739-style linearized S-N/epsilon-N relation."""
    confidence = _normalize_confidence(confidence)
    if x_transform not in ("log", "linear"):
        raise ValueError("x_transform must be 'log' or 'linear'.")
    if fit_points < 2:
        raise ValueError("fit_points must be at least 2.")
    _require_column(frame, life_column, "life")
    _require_column(frame, response_column, "response")
    if status_column:
        _require_column(frame, status_column, "status")
    if level_column:
        _require_column(frame, level_column, "level")

    warnings: list[str] = []
    source_columns = list(dict.fromkeys([response_column, life_column, status_column, level_column]))
    source_columns = [column for column in source_columns if column]
    data = frame[source_columns].copy()
    data["e739_life"] = pd.to_numeric(data[life_column], errors="coerce")
    data["e739_response"] = pd.to_numeric(data[response_column], errors="coerce")

    initial_rows = len(data)
    data = data.dropna(subset=["e739_life", "e739_response"]).copy()
    dropped_missing = initial_rows - len(data)
    if dropped_missing:
        warnings.append(f"Dropped {dropped_missing} row(s) with missing numeric life/response.")

    if status_column:
        status = data[status_column].map(_status_is_failure)
        excluded = int((~status).sum())
        data = data[status].copy()
        if excluded:
            warnings.append(
                "Excluded run-out/suspended row(s); E739 OLS applies only to failure data."
            )

    before_domain_rows = len(data)
    positive_mask = data["e739_life"] > 0
    if x_transform == "log":
        positive_mask &= data["e739_response"] > 0
    data = data[positive_mask].copy()
    dropped_nonpositive = before_domain_rows - len(data)
    if dropped_nonpositive:
        warnings.append(
            f"Dropped {dropped_nonpositive} row(s) outside the positive domain required by the model."
        )

    if len(data) < 3:
        raise ValueError("At least three valid failure points are required for E739 analysis.")

    if x_transform == "log":
        data["e739_x"] = np.log10(data["e739_response"].to_numpy(dtype=float))
    else:
        data["e739_x"] = data["e739_response"].astype(float)
    data["e739_y_log10_life"] = np.log10(data["e739_life"].to_numpy(dtype=float))

    x = data["e739_x"].to_numpy(dtype=float)
    y = data["e739_y_log10_life"].to_numpy(dtype=float)
    k = len(data)
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    x_delta = x - x_mean
    y_delta = y - y_mean
    sxx = float(np.sum(x_delta**2))
    if sxx <= 0:
        raise ValueError("The E739 independent variable has no variation.")
    sxy = float(np.sum(x_delta * y_delta))
    coefficient_b = sxy / sxx
    coefficient_a = y_mean - coefficient_b * x_mean

    y_hat = coefficient_a + coefficient_b * x
    residual = y - y_hat
    residual_sum_squares = float(np.sum(residual**2))
    degrees_of_freedom = k - 2
    sigma_squared = residual_sum_squares / degrees_of_freedom
    sigma = float(np.sqrt(sigma_squared))
    total_sum_squares = float(np.sum(y_delta**2))
    r2 = 1.0 if total_sum_squares == 0 else 1.0 - residual_sum_squares / total_sum_squares
    rmse_log_life = float(np.sqrt(np.mean(residual**2)))
    standard_error_a = float(sigma * np.sqrt(1.0 / k + x_mean**2 / sxx))
    standard_error_b = float(sigma / np.sqrt(sxx))

    t_critical = float(stats.t.ppf((1.0 + confidence) / 2.0, degrees_of_freedom))
    f_band_critical = float(stats.f.ppf(confidence, 2, degrees_of_freedom))
    simultaneous_band_factor = float(np.sqrt(2.0 * f_band_critical))

    data["e739_yhat_log10_life"] = y_hat
    data["e739_residual_log10_life"] = residual
    data["e739_life_fit"] = np.power(10.0, y_hat)
    data["e739_abs_residual_log10_life"] = np.abs(residual)
    data["e739_level"] = _level_values(data, level_column, replicate_decimals)

    level_stats = _level_statistics(data, coefficient_a, coefficient_b)
    linearity_test = _linearity_test(
        data,
        level_stats,
        confidence,
        coefficient_a,
        coefficient_b,
    )
    levels = max(1, len(level_stats))
    replication_percent = float(100.0 * (1.0 - levels / k))

    x_grid = np.linspace(float(np.min(x)), float(np.max(x)), fit_points)
    y_grid = coefficient_a + coefficient_b * x_grid
    band_delta = (
        simultaneous_band_factor
        * sigma
        * np.sqrt(1.0 / k + np.power(x_grid - x_mean, 2) / sxx)
    )
    if x_transform == "log":
        response_grid = np.power(10.0, x_grid)
    else:
        response_grid = x_grid
    curve = pd.DataFrame(
        {
            "e739_x": x_grid,
            "response": response_grid,
            "log10_life_fit": y_grid,
            "log10_life_lower_band": y_grid - band_delta,
            "log10_life_upper_band": y_grid + band_delta,
            "life_fit": np.power(10.0, y_grid),
            "life_lower_band": np.power(10.0, y_grid - band_delta),
            "life_upper_band": np.power(10.0, y_grid + band_delta),
        }
    )
    curve = curve.sort_values("life_fit").reset_index(drop=True)

    log_life_formula = _log_life_formula(
        life_column,
        response_column,
        coefficient_a,
        coefficient_b,
        x_transform,
    )
    life_response_coefficient_a = float(np.power(10.0, coefficient_a))
    life_response_coefficient_b = float(coefficient_b)
    life_formula = _life_formula(
        life_column,
        response_column,
        coefficient_a,
        coefficient_b,
        x_transform,
    )
    life_response_formula = _life_response_formula(
        life_column,
        response_column,
        life_response_coefficient_a,
        life_response_coefficient_b,
        x_transform,
    )
    response_life_formula = _response_life_formula(
        life_column,
        response_column,
        coefficient_a,
        coefficient_b,
        x_transform,
    )

    result = E739FitResult(
        confidence=confidence,
        x_transform=x_transform,
        points=k,
        degrees_of_freedom=degrees_of_freedom,
        coefficient_a=float(coefficient_a),
        coefficient_b=float(coefficient_b),
        x_mean=x_mean,
        y_mean=y_mean,
        sxx=sxx,
        sxy=sxy,
        residual_sum_squares=residual_sum_squares,
        sigma_squared=float(sigma_squared),
        sigma=sigma,
        r2=float(r2),
        rmse_log_life=rmse_log_life,
        standard_error_a=standard_error_a,
        standard_error_b=standard_error_b,
        t_critical=t_critical,
        f_band_critical=f_band_critical,
        simultaneous_band_factor=simultaneous_band_factor,
        coefficient_a_lower=float(coefficient_a - t_critical * standard_error_a),
        coefficient_a_upper=float(coefficient_a + t_critical * standard_error_a),
        coefficient_b_lower=float(coefficient_b - t_critical * standard_error_b),
        coefficient_b_upper=float(coefficient_b + t_critical * standard_error_b),
        x_min=float(np.min(x)),
        x_max=float(np.max(x)),
        life_min=float(data["e739_life"].min()),
        life_max=float(data["e739_life"].max()),
        response_min=float(data["e739_response"].min()),
        response_max=float(data["e739_response"].max()),
        replication_percent=replication_percent,
        life_response_coefficient_a=life_response_coefficient_a,
        life_response_coefficient_b=life_response_coefficient_b,
        log_life_formula=log_life_formula,
        life_formula=life_formula,
        life_response_formula=life_response_formula,
        response_life_formula=response_life_formula,
        warnings=tuple(warnings),
        linearity_test=linearity_test,
    )
    return E739Fit(result=result, data=data.reset_index(drop=True), curve=curve, level_stats=level_stats)


def _normalize_confidence(confidence: float) -> float:
    confidence = float(confidence)
    if confidence > 1.0 and confidence <= 100.0:
        confidence /= 100.0
    if confidence <= 0.0 or confidence >= 1.0:
        raise ValueError("confidence must be between 0 and 1, or between 0 and 100 percent.")
    return confidence


def _require_column(frame: pd.DataFrame, column: str, role: str) -> None:
    if column not in frame.columns:
        raise ValueError(f"E739 {role} column not found: {column}")


def _status_is_failure(value: object) -> bool:
    if pd.isna(value):
        return True
    text = str(value).strip().lower()
    if not text:
        return True
    if any(marker in text for marker in NON_FAILURE_STATUS_MARKERS):
        return False
    if any(marker in text for marker in FAILURE_STATUS_MARKERS):
        return True
    return True


def _level_values(
    data: pd.DataFrame,
    level_column: str | None,
    replicate_decimals: int,
) -> pd.Series:
    if level_column:
        return data[level_column].astype(str)
    return data["e739_x"].round(replicate_decimals).astype(str)


def _level_statistics(
    data: pd.DataFrame,
    coefficient_a: float,
    coefficient_b: float,
) -> pd.DataFrame:
    grouped = data.groupby("e739_level", sort=True, dropna=False)
    level_stats = grouped.agg(
        e739_level_x=("e739_x", "mean"),
        e739_level_y_mean=("e739_y_log10_life", "mean"),
        e739_level_count=("e739_y_log10_life", "size"),
        e739_level_y_std=("e739_y_log10_life", "std"),
    ).reset_index()
    level_stats["e739_level_yhat"] = (
        coefficient_a + coefficient_b * level_stats["e739_level_x"]
    )
    level_stats["e739_level_residual"] = (
        level_stats["e739_level_y_mean"] - level_stats["e739_level_yhat"]
    )
    return level_stats


def _linearity_test(
    data: pd.DataFrame,
    level_stats: pd.DataFrame,
    confidence: float,
    coefficient_a: float,
    coefficient_b: float,
) -> E739LinearityTest:
    k = len(data)
    levels = len(level_stats)
    lack_of_fit_df = levels - 2
    pure_error_df = k - levels
    if levels < 3:
        return E739LinearityTest(
            available=False,
            reason="Need at least three stress/strain levels.",
            levels=levels,
            specimens=k,
            lack_of_fit_df=None,
            pure_error_df=None,
            lack_of_fit_ss=None,
            pure_error_ss=None,
            lack_of_fit_ms=None,
            pure_error_ms=None,
            f_statistic=None,
            f_critical=None,
            p_value=None,
            reject_linear_model=None,
        )
    if pure_error_df <= 0:
        return E739LinearityTest(
            available=False,
            reason="Need replicated tests to estimate pure error.",
            levels=levels,
            specimens=k,
            lack_of_fit_df=lack_of_fit_df,
            pure_error_df=pure_error_df,
            lack_of_fit_ss=None,
            pure_error_ss=None,
            lack_of_fit_ms=None,
            pure_error_ms=None,
            f_statistic=None,
            f_critical=None,
            p_value=None,
            reject_linear_model=None,
        )

    y_mean_by_level = level_stats.set_index("e739_level")["e739_level_y_mean"]
    joined = data.join(y_mean_by_level, on="e739_level", rsuffix="_level")
    pure_error_ss = float(
        np.sum(
            np.power(
                joined["e739_y_log10_life"].to_numpy(dtype=float)
                - joined["e739_level_y_mean"].to_numpy(dtype=float),
                2,
            )
        )
    )
    yhat_level = coefficient_a + coefficient_b * level_stats["e739_level_x"].to_numpy(dtype=float)
    lack_of_fit_ss = float(
        np.sum(
            level_stats["e739_level_count"].to_numpy(dtype=float)
            * np.power(yhat_level - level_stats["e739_level_y_mean"].to_numpy(dtype=float), 2)
        )
    )
    lack_of_fit_ms = lack_of_fit_ss / lack_of_fit_df
    pure_error_ms = pure_error_ss / pure_error_df
    if pure_error_ms == 0.0:
        f_statistic = float("inf") if lack_of_fit_ms > 0.0 else 0.0
    else:
        f_statistic = float(lack_of_fit_ms / pure_error_ms)
    f_critical = float(stats.f.ppf(confidence, lack_of_fit_df, pure_error_df))
    p_value = float(stats.f.sf(f_statistic, lack_of_fit_df, pure_error_df))
    return E739LinearityTest(
        available=True,
        reason="",
        levels=levels,
        specimens=k,
        lack_of_fit_df=lack_of_fit_df,
        pure_error_df=pure_error_df,
        lack_of_fit_ss=lack_of_fit_ss,
        pure_error_ss=pure_error_ss,
        lack_of_fit_ms=float(lack_of_fit_ms),
        pure_error_ms=float(pure_error_ms),
        f_statistic=f_statistic,
        f_critical=f_critical,
        p_value=p_value,
        reject_linear_model=bool(f_statistic > f_critical),
    )


def _signed(value: float) -> str:
    if value < 0:
        return f"- {abs(value):.6g}"
    return f"+ {value:.6g}"


def _x_expression(response_column: str, x_transform: E739Transform) -> str:
    if x_transform == "log":
        return f"log10({response_column})"
    return response_column


def _log_life_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
) -> str:
    x_expr = _x_expression(response_column, x_transform)
    return f"log10({life_column}) = {coefficient_a:.6g} {_signed(coefficient_b)} * {x_expr}"


def _life_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
) -> str:
    x_expr = _x_expression(response_column, x_transform)
    return (
        f"{life_column} = 10^({coefficient_a:.6g} "
        f"{_signed(coefficient_b)} * {x_expr})"
    )


def _life_response_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
) -> str:
    if x_transform == "log":
        return f"{life_column} = {coefficient_a:.6g} * {response_column}^{coefficient_b:.6g}"
    return (
        f"{life_column} = 10^({np.log10(coefficient_a):.6g} "
        f"{_signed(coefficient_b)} * {response_column})"
    )


def _response_life_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
) -> str:
    if abs(coefficient_b) < 1e-15:
        return "Response-life form is undefined because B is approximately zero."
    if x_transform == "log":
        response_scale = float(np.power(10.0, -coefficient_a / coefficient_b))
        response_exponent = 1.0 / coefficient_b
        return (
            f"{response_column} = {response_scale:.6g} * "
            f"{life_column}^{response_exponent:.6g}"
        )
    return (
        f"{response_column} = (log10({life_column}) "
        f"{_signed(-coefficient_a)}) / {coefficient_b:.6g}"
    )
