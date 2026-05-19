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
    seasonal_period = int(seasonal_period or 0)
    seasonal_candidates = []
    if seasonal_period > 1:
        if seasonal_period > 72:
            seasonal_candidates = [
                ((1, 1, 1), (1, 0, 0, seasonal_period)),
            ]
        else:
            seasonal_candidates = [
                ((1, 1, 1), (1, 0, 0, seasonal_period)),
                ((2, 1, 2), (1, 0, 1, seasonal_period)),
                ((1, 1, 1), (1, 1, 0, seasonal_period)),
                ((1, 1, 1), (1, 1, 1, seasonal_period)),
            ]
    nonseasonal_candidates = (
        [((1, 1, 1), (0, 0, 0, 0))]
        if seasonal_period > 72
        else [
            ((2, 1, 2), (0, 0, 0, 0)),
            ((1, 1, 1), (0, 0, 0, 0)),
            ((1, 0, 1), (0, 0, 0, 0)),
        ]
    )
    candidates = seasonal_candidates + nonseasonal_candidates

    best = None
    best_score = None
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
            maxiter = 45 if seasonal_order[3] and seasonal_order[3] > 72 else 80
            fitted = model.fit(disp=False, maxiter=maxiter)
            if hasattr(fitted, "mle_retvals") and isinstance(fitted.mle_retvals, dict):
                # Mark non-converged runs but still allow fallback by trying next candidate.
                if not fitted.mle_retvals.get("converged", True):
                    raise RuntimeError("SARIMA did not converge")
            aic = getattr(fitted, "aic", None)
            try:
                score = float(aic)
            except (TypeError, ValueError):
                score = float("inf")
            if best is None or score < best_score:
                best = (fitted, order, seasonal_order)
                best_score = score
        except Exception as exc:
            last_exc = exc
            continue
    if best is not None:
        return best
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
