from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy import optimize, stats


E739Transform = Literal["log", "linear"]
E739Model = Literal["standard", "shifted-log"]

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
    life_column: str
    response_column: str
    model: E739Model
    confidence: float
    x_transform: E739Transform
    parameter_count: int
    points: int
    degrees_of_freedom: int
    coefficient_a: float
    coefficient_b: float
    coefficient_c: float | None
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
    standard_error_c: float | None
    t_critical: float
    f_band_critical: float
    simultaneous_band_factor: float
    coefficient_a_lower: float
    coefficient_a_upper: float
    coefficient_b_lower: float
    coefficient_b_upper: float
    coefficient_c_lower: float | None
    coefficient_c_upper: float | None
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
    model: E739Model = "standard",
    x_transform: E739Transform = "log",
    confidence: float = 0.95,
    fit_points: int = 300,
    status_column: str | None = None,
    level_column: str | None = None,
    replicate_decimals: int = 8,
) -> E739Fit:
    """Fit an ASTM E739-style linearized S-N/epsilon-N relation."""
    confidence = _normalize_confidence(confidence)
    if model not in ("standard", "shifted-log"):
        raise ValueError("model must be 'standard' or 'shifted-log'.")
    if x_transform not in ("log", "linear"):
        raise ValueError("x_transform must be 'log' or 'linear'.")
    if model == "shifted-log" and x_transform != "log":
        raise ValueError("The shifted-log model requires --e739-x-transform log.")
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

    parameter_count = 3 if model == "shifted-log" else 2
    if len(data) <= parameter_count:
        raise ValueError(
            f"At least {parameter_count + 1} valid failure points are required "
            f"for the {model} E739 analysis."
        )

    data["e739_y_log10_life"] = np.log10(data["e739_life"].to_numpy(dtype=float))

    response = data["e739_response"].to_numpy(dtype=float)
    y = data["e739_y_log10_life"].to_numpy(dtype=float)
    k = len(data)
    y_mean = float(np.mean(y))
    y_delta = y - y_mean
    total_sum_squares = float(np.sum(y_delta**2))

    if model == "shifted-log":
        fit_state = _fit_shifted_log_response(response, y)
        coefficient_a = fit_state["coefficient_a"]
        coefficient_b = fit_state["coefficient_b"]
        coefficient_c = fit_state["coefficient_c"]
        x = fit_state["x"]
        y_hat = fit_state["y_hat"]
        residual = fit_state["residual"]
        covariance = fit_state["covariance"]
        sxx = fit_state["sxx"]
        sxy = fit_state["sxy"]
        x_mean = fit_state["x_mean"]
        standard_error_a = fit_state["standard_error_a"]
        standard_error_b = fit_state["standard_error_b"]
        standard_error_c = fit_state["standard_error_c"]
    else:
        coefficient_c = None
        standard_error_c = None
        covariance = None
        if x_transform == "log":
            x = np.log10(response)
        else:
            x = response
        x_mean = float(np.mean(x))
        x_delta = x - x_mean
        sxx = float(np.sum(x_delta**2))
        if sxx <= 0:
            raise ValueError("The E739 independent variable has no variation.")
        sxy = float(np.sum(x_delta * y_delta))
        coefficient_b = sxy / sxx
        coefficient_a = y_mean - coefficient_b * x_mean
        y_hat = coefficient_a + coefficient_b * x
        residual = y - y_hat
        standard_error_a = None
        standard_error_b = None

    data["e739_x"] = x
    residual = y - y_hat
    residual_sum_squares = float(np.sum(residual**2))
    degrees_of_freedom = k - parameter_count
    sigma_squared = residual_sum_squares / degrees_of_freedom
    sigma = float(np.sqrt(sigma_squared))
    r2 = 1.0 if total_sum_squares == 0 else 1.0 - residual_sum_squares / total_sum_squares
    rmse_log_life = float(np.sqrt(np.mean(residual**2)))
    if model == "standard":
        standard_error_a = float(sigma * np.sqrt(1.0 / k + x_mean**2 / sxx))
        standard_error_b = float(sigma / np.sqrt(sxx))

    t_critical = float(stats.t.ppf((1.0 + confidence) / 2.0, degrees_of_freedom))
    f_band_critical = float(stats.f.ppf(confidence, parameter_count, degrees_of_freedom))
    simultaneous_band_factor = float(np.sqrt(parameter_count * f_band_critical))

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
        parameter_count,
    )
    levels = max(1, len(level_stats))
    replication_percent = float(100.0 * (1.0 - levels / k))

    x_grid = np.linspace(float(np.min(x)), float(np.max(x)), fit_points)
    y_grid = coefficient_a + coefficient_b * x_grid
    if model == "shifted-log":
        band_delta = _shifted_log_band_delta(
            x_grid,
            coefficient_b,
            covariance,
            simultaneous_band_factor,
        )
    else:
        band_delta = (
            simultaneous_band_factor
            * sigma
            * np.sqrt(1.0 / k + np.power(x_grid - x_mean, 2) / sxx)
        )
    if model == "shifted-log":
        response_grid = coefficient_c + np.power(10.0, x_grid)
    elif x_transform == "log":
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
        model,
        coefficient_c,
    )
    life_response_coefficient_a = float(np.power(10.0, coefficient_a))
    life_response_coefficient_b = float(coefficient_b)
    life_formula = _life_formula(
        life_column,
        response_column,
        coefficient_a,
        coefficient_b,
        x_transform,
        model,
        coefficient_c,
    )
    life_response_formula = _life_response_formula(
        life_column,
        response_column,
        life_response_coefficient_a,
        life_response_coefficient_b,
        x_transform,
        model,
        coefficient_c,
    )
    response_life_formula = _response_life_formula(
        life_column,
        response_column,
        coefficient_a,
        coefficient_b,
        x_transform,
        model,
        coefficient_c,
    )

    result = E739FitResult(
        life_column=life_column,
        response_column=response_column,
        model=model,
        confidence=confidence,
        x_transform=x_transform,
        parameter_count=parameter_count,
        points=k,
        degrees_of_freedom=degrees_of_freedom,
        coefficient_a=float(coefficient_a),
        coefficient_b=float(coefficient_b),
        coefficient_c=None if coefficient_c is None else float(coefficient_c),
        x_mean=x_mean,
        y_mean=y_mean,
        sxx=sxx,
        sxy=sxy,
        residual_sum_squares=residual_sum_squares,
        sigma_squared=float(sigma_squared),
        sigma=sigma,
        r2=float(r2),
        rmse_log_life=rmse_log_life,
        standard_error_a=float(standard_error_a),
        standard_error_b=float(standard_error_b),
        standard_error_c=None if standard_error_c is None else float(standard_error_c),
        t_critical=t_critical,
        f_band_critical=f_band_critical,
        simultaneous_band_factor=simultaneous_band_factor,
        coefficient_a_lower=float(coefficient_a - t_critical * standard_error_a),
        coefficient_a_upper=float(coefficient_a + t_critical * standard_error_a),
        coefficient_b_lower=float(coefficient_b - t_critical * standard_error_b),
        coefficient_b_upper=float(coefficient_b + t_critical * standard_error_b),
        coefficient_c_lower=(
            None
            if coefficient_c is None or standard_error_c is None
            else float(coefficient_c - t_critical * standard_error_c)
        ),
        coefficient_c_upper=(
            None
            if coefficient_c is None or standard_error_c is None
            else float(coefficient_c + t_critical * standard_error_c)
        ),
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


def _fit_shifted_log_response(response: np.ndarray, y: np.ndarray) -> dict[str, object]:
    response_min = float(np.min(response))
    response_max = float(np.max(response))
    response_span = response_max - response_min
    if response_span <= 0:
        raise ValueError("The E739 response column has no variation.")

    margin = max(abs(response_min), abs(response_span), 1.0) * 1e-10
    c_upper = response_min - margin
    c_lower = response_min - max(1000.0 * response_span, 1000.0 * abs(response_min), 1.0)
    if not c_lower < c_upper:
        raise ValueError("Could not create a valid search domain for C.")

    seeds: list[float] = [
        response_min - 0.05 * response_span,
        response_min - 0.25 * response_span,
        response_min - response_span,
        response_min - 5.0 * response_span,
        0.0,
    ]
    seeds = [min(max(seed, c_lower + margin), c_upper - margin) for seed in seeds]
    seeds = list(dict.fromkeys(round(seed, 15) for seed in seeds))

    best_result: optimize.OptimizeResult | None = None
    for c_initial in seeds:
        a_initial, b_initial = _linear_parameters_for_shift(response, y, c_initial)
        result = optimize.least_squares(
            _shifted_log_residual,
            x0=np.array([a_initial, b_initial, c_initial], dtype=float),
            args=(response, y),
            bounds=(
                np.array([-np.inf, -np.inf, c_lower], dtype=float),
                np.array([np.inf, np.inf, c_upper], dtype=float),
            ),
            x_scale=np.array([1.0, 1.0, max(abs(response_span), abs(response_min), 1.0)]),
            max_nfev=2000,
        )
        if not result.success:
            continue
        if best_result is None or result.cost < best_result.cost:
            best_result = result

    if best_result is None:
        raise ValueError("The shifted-log model did not converge.")

    coefficient_a, coefficient_b, coefficient_c = [float(value) for value in best_result.x]
    x = np.log10(response - coefficient_c)
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    x_delta = x - x_mean
    y_delta = y - y_mean
    sxx = float(np.sum(x_delta**2))
    if sxx <= 0:
        raise ValueError("The shifted-log independent variable has no variation.")
    sxy = float(np.sum(x_delta * y_delta))
    y_hat = coefficient_a + coefficient_b * x
    residual = y - y_hat
    residual_sum_squares = float(np.sum(residual**2))
    degrees_of_freedom = len(response) - 3
    sigma_squared = residual_sum_squares / degrees_of_freedom
    covariance = sigma_squared * np.linalg.pinv(best_result.jac.T @ best_result.jac)
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))

    return {
        "coefficient_a": coefficient_a,
        "coefficient_b": coefficient_b,
        "coefficient_c": coefficient_c,
        "x": x,
        "x_mean": x_mean,
        "sxx": sxx,
        "sxy": sxy,
        "y_hat": y_hat,
        "residual": residual,
        "covariance": covariance,
        "standard_error_a": float(standard_errors[0]),
        "standard_error_b": float(standard_errors[1]),
        "standard_error_c": float(standard_errors[2]),
    }


def _linear_parameters_for_shift(
    response: np.ndarray,
    y: np.ndarray,
    coefficient_c: float,
) -> tuple[float, float]:
    x = np.log10(response - coefficient_c)
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    sxx = float(np.sum(np.power(x - x_mean, 2)))
    if sxx <= 0:
        return y_mean, 0.0
    sxy = float(np.sum((x - x_mean) * (y - y_mean)))
    coefficient_b = sxy / sxx
    coefficient_a = y_mean - coefficient_b * x_mean
    return float(coefficient_a), float(coefficient_b)


def _shifted_log_residual(
    parameters: np.ndarray,
    response: np.ndarray,
    y: np.ndarray,
) -> np.ndarray:
    coefficient_a, coefficient_b, coefficient_c = parameters
    return coefficient_a + coefficient_b * np.log10(response - coefficient_c) - y


def _shifted_log_band_delta(
    x_grid: np.ndarray,
    coefficient_b: float,
    covariance: np.ndarray,
    simultaneous_band_factor: float,
) -> np.ndarray:
    shifted_response = np.power(10.0, x_grid)
    gradients = np.column_stack(
        (
            np.ones_like(x_grid),
            x_grid,
            -coefficient_b / (np.log(10.0) * shifted_response),
        )
    )
    variances = np.einsum("ij,jk,ik->i", gradients, covariance, gradients)
    return simultaneous_band_factor * np.sqrt(np.maximum(variances, 0.0))


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
    parameter_count: int,
) -> E739LinearityTest:
    k = len(data)
    levels = len(level_stats)
    lack_of_fit_df = levels - parameter_count
    pure_error_df = k - levels
    if lack_of_fit_df <= 0:
        return E739LinearityTest(
            available=False,
            reason=f"Need at least {parameter_count + 1} stress/strain levels.",
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


def _x_expression(
    response_column: str,
    x_transform: E739Transform,
    model: E739Model,
    coefficient_c: float | None,
) -> str:
    if model == "shifted-log":
        return f"log10({_shifted_response_expression(response_column, coefficient_c)})"
    if x_transform == "log":
        return f"log10({response_column})"
    return response_column


def _log_life_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
    model: E739Model,
    coefficient_c: float | None,
) -> str:
    x_expr = _x_expression(response_column, x_transform, model, coefficient_c)
    return f"log10({life_column}) = {coefficient_a:.6g} {_signed(coefficient_b)} * {x_expr}"


def _life_formula(
    life_column: str,
    response_column: str,
    coefficient_a: float,
    coefficient_b: float,
    x_transform: E739Transform,
    model: E739Model,
    coefficient_c: float | None,
) -> str:
    x_expr = _x_expression(response_column, x_transform, model, coefficient_c)
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
    model: E739Model,
    coefficient_c: float | None,
) -> str:
    if model == "shifted-log":
        return (
            f"{life_column} = {coefficient_a:.6g} * "
            f"({_shifted_response_expression(response_column, coefficient_c)})"
            f"^{coefficient_b:.6g}"
        )
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
    model: E739Model,
    coefficient_c: float | None,
) -> str:
    if abs(coefficient_b) < 1e-15:
        return "Response-life form is undefined because B is approximately zero."
    if model == "shifted-log":
        response_scale = float(np.power(10.0, -coefficient_a / coefficient_b))
        response_exponent = 1.0 / coefficient_b
        return (
            f"{response_column} = {coefficient_c:.6g} + "
            f"{response_scale:.6g} * {life_column}^{response_exponent:.6g}"
        )
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


def _shifted_response_expression(response_column: str, coefficient_c: float | None) -> str:
    if coefficient_c is None:
        return response_column
    if coefficient_c < 0:
        return f"{response_column} + {abs(coefficient_c):.6g}"
    return f"{response_column} - {coefficient_c:.6g}"
