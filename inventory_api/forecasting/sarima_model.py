from __future__ import annotations


def _require_deps():
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Baseline forecast dependencies are missing. Install statsmodels."
        ) from exc
    return SARIMAX


def fit_sarima(series, seasonal_period: int):
    SARIMAX = _require_deps()
    candidates = [
        ((1, 1, 1), (1, 0, 0, seasonal_period)),
        ((1, 1, 1), (0, 0, 0, 0)),
    ]
    last_exc = None
    for order, seasonal_order in candidates:
        try:
            # Skip heavy seasonal configs for very short series.
            if seasonal_order[3] and len(series) < (seasonal_order[3] * 2 + 24):
                continue
            model = SARIMAX(
                series.astype(float),
                order=order,
                seasonal_order=seasonal_order,
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            fitted = model.fit(disp=False, maxiter=60)
            if hasattr(fitted, "mle_retvals") and isinstance(fitted.mle_retvals, dict):
                # Mark non-converged runs but still allow fallback by trying next candidate.
                if not fitted.mle_retvals.get("converged", True):
                    raise RuntimeError("SARIMA did not converge")
            return fitted, order, seasonal_order
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise RuntimeError("Could not fit SARIMA model for this series")


def forecast_with_intervals(fitted_model, *, steps: int, alpha: float = 0.2):
    pred = fitted_model.get_forecast(steps=steps)
    mean = pred.predicted_mean
    conf = pred.conf_int(alpha=alpha)
    if conf.shape[1] >= 2:
        lower = conf.iloc[:, 0]
        upper = conf.iloc[:, 1]
    else:
        # Fallback for rare edge cases.
        lower = mean.copy()
        upper = mean.copy()
    return mean, lower, upper
