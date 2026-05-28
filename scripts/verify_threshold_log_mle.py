from __future__ import annotations

from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
from scipy import stats

from originnsfit.cli import main
from originnsfit.e739 import (
    fit_e739,
    inverse_threshold_log_mle_response,
    predict_threshold_log_mle_life,
)


def _synthetic_data(with_runout: bool) -> pd.DataFrame:
    rng = np.random.default_rng(20260528)
    intercept = 5.2
    slope = -2.1
    threshold = 0.0012
    sigma = 0.06
    response = np.linspace(0.002, 0.008, 36)
    log_life = intercept + slope * np.log10(response - threshold)
    observed_life = np.power(10.0, log_life + rng.normal(0.0, sigma, len(response)))
    frame = pd.DataFrame({"S": response, "N": observed_life, "status": "failure"})
    if with_runout:
        runout = np.arange(len(frame)) % 5 == 0
        frame.loc[runout, "N"] *= 0.55
        frame.loc[runout, "status"] = "runout"
    return frame


def _check_log_likelihood_uses_logsf(fit) -> None:
    result = fit.result
    is_failure = fit.data["e739_is_failure"].to_numpy(dtype=bool)
    observed = fit.data["e739_y_log10_life"].to_numpy(dtype=float)
    fitted = fit.data["e739_yhat_log10_life"].to_numpy(dtype=float)
    log_likelihood = float(
        np.sum(stats.norm.logpdf(observed[is_failure], loc=fitted[is_failure], scale=result.sigma))
    )
    z_runout = (observed[~is_failure] - fitted[~is_failure]) / result.sigma
    log_likelihood += float(np.sum(stats.norm.logsf(z_runout)))
    assert abs(log_likelihood - result.log_likelihood) < 1e-8


def main_verify() -> None:
    failure_only = _synthetic_data(with_runout=False)
    default_fit = fit_e739(failure_only, "N", "S")
    standard_fit = fit_e739(failure_only, "N", "S", model="standard")
    assert default_fit.result.coefficient_a == standard_fit.result.coefficient_a
    assert default_fit.result.coefficient_b == standard_fit.result.coefficient_b

    mle_failure_only = fit_e739(
        failure_only,
        "N",
        "S",
        model="threshold_log_mle",
        status_column="status",
    )
    assert mle_failure_only.result.n_runout == 0
    assert mle_failure_only.result.coefficient_c < failure_only["S"].min()
    assert mle_failure_only.result.sigma > 0.0
    assert mle_failure_only.result.coefficient_b < 0.0

    censored = _synthetic_data(with_runout=True)
    mle_censored = fit_e739(
        censored,
        "N",
        "S",
        model="threshold_log_mle",
        status_column="status",
    )
    assert mle_censored.result.n_runout == int((censored["status"] == "runout").sum())
    assert mle_censored.result.n_failure == int((censored["status"] == "failure").sum())
    _check_log_likelihood_uses_logsf(mle_censored)

    numeric_status = censored.copy()
    numeric_status["status"] = (numeric_status["status"] == "failure").astype(int)
    numeric_fit = fit_e739(
        numeric_status,
        "N",
        "S",
        model="threshold_log_mle",
        status_column="status",
    )
    assert numeric_fit.result.n_runout == mle_censored.result.n_runout

    threshold = float(mle_censored.result.coefficient_c)
    life = predict_threshold_log_mle_life(mle_censored.result, threshold + 0.003)
    response = inverse_threshold_log_mle_response(mle_censored.result, life)
    assert np.isfinite(life)
    assert np.isfinite(response)
    try:
        predict_threshold_log_mle_life(mle_censored.result, threshold)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected a clear domain error for S <= C.")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input"
        output_dir = temp_path / "output"
        input_dir.mkdir()
        censored.to_csv(input_dir / "threshold.csv", index=False, encoding="utf-8-sig")
        exit_code = main(
            [
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--pattern",
                "*.csv",
                "--life",
                "N",
                "--response",
                "S",
                "--status",
                "status",
                "--e739-model",
                "threshold_log_mle",
                "--dry-run",
            ]
        )
        assert exit_code == 0
        summary = pd.read_csv(output_dir / "e739_summary.csv", encoding="utf-8-sig")
        for column in ("coefficient_a", "coefficient_b", "coefficient_c", "sigma"):
            assert column in summary.columns
        assert summary.loc[0, "model"] == "threshold_log_mle"
        assert int(summary.loc[0, "n_runout"]) == mle_censored.result.n_runout

    print("threshold_log_mle verification passed")


if __name__ == "__main__":
    main_verify()
