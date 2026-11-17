"""GTA VI launch-day Twitch CCU forecaster (make.fun gta6-twitch-ccu-forecast-01).

Forecasts, for each of hours 2..24 of the release day (UTC), five quantiles
(5%, 25%, 50%, 75%, 95%) of the concurrent Twitch viewers in the game's
category, from the case's first-hour print and the launch-day curves of past
big game launches shipped inside the case (`comparables`).

Design (see DESIGN.md for the full reasoning record, the numbers behind every
choice, and what was tried and dropped):

  The release-day curve of a big console launch has a shape that is largely
  determined by how big the launch is. Hour 1 (00:00 UTC, before most of the
  world has unlocked the game) is a weak anchor on its own: across past
  launches, the log of an hour's viewers regresses on the log of the hour-1
  print with a slope that collapses from ~1 at hour 2 to ~0.06 at the evening
  peak -- the peak is nearly the same size whatever hour 1 was, because the
  peak is capped by how many people watch Twitch at that hour at all. A
  second anchor, the mean pre-release viewership over the 7 days before
  release (lnPREM), carries the game's overall hype and tightens the fit.

  Two independent views of the same curve are built and blended 50/50 in log
  space (a blend of the two beat either view alone on the practice cases,
  0.154 vs 0.161 / 0.174):

  1. LOCAL OLS. For each hour h, ordinary least squares of ln(viewers_h) on
     [lnV1, lnPREM] over the comparable launches whose lnV1 lies within 2.5
     of the target's (a size-matched reference class; at least 10 launches,
     else the whole library). Predictive quantiles are the fitted median plus
     the standard normal's quantiles times the residual spread, shrunk by 0.8
     (the practice launches' bands were over-wide at spread 1.0).

  2. SHAPE FACTOR. The library's median log-ratio curve m_h = median of
     ln(V_h / V_1) is one factor: each launch's own curve is fit as
     ln(V_h / V_1) = c + s * m_h, and the launch's level c and amplitude s
     are regressed on [lnV1, lnPREM]. The target's curve is its predicted
     (c, s) applied to m_h, with per-hour residual spread around the
     launches' own one-factor fits.

  Both views use only the case file: no network, no stored tables, no model
  calls. The program is deterministic (sorted iteration, no randomness, no
  clock), standard library only, and runs in well under the 8-second limit.

Entry contract (RULES.txt): read every <id>.in in $MAKEFUN_INPUT_DIR (else
/input), write <id>.out to $MAKEFUN_OUTPUT_DIR (else /output) as
{"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]}, ...]} for h = 2..24,
each quantile a finite number in (0, 1e9], non-decreasing, rounded to 2
decimals half-up.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is one file; the line is
# kept so the layout stays valid if a helper is ever added.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]

# Local reference class: comparables within this many log units of the
# target's hour-1 size. Tuned on the practice cases + leave-one-out over the
# comparables (see DESIGN.md); the result is flat across 2.0-3.0.
LOCAL_HALF_WIDTH = 2.5
MIN_LOCAL = 10
# Spread shrink for the OLS view (practice bands were over-wide at 1.0).
OLS_SPREAD = 0.8
# Blend weight of the shape view (0.5 = equal geometric mean of the two).
SHAPE_WEIGHT = 0.5


def round2(x):
    """Round to 2 decimals, half up; whole numbers come back as ints."""
    scaled = x * 100.0
    whole = math.floor(scaled + 0.5)
    value = whole / 100.0
    return int(value) if value == int(value) else value


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def launch_features(hourly, day_start):
    """Features of one launch from its hourly points.

    hourly: {ISO start -> (viewers, channels)}; day_start: ISO release day.
    Returns {"lnV1", "lnPREM"} where lnV1 is log viewers in the release
    day's hour 1 (00:00-01:00 UTC) and lnPREM is log of the mean viewers
    over the 7 days before the release day. Either may be None when the
    points to compute it are absent (sparse sampling).
    """
    day = _parse(day_start)
    day_s = day_start[:10]
    v1 = None
    pre7 = []
    for frm in sorted(hourly):
        viewers = hourly[frm][0]
        if not viewers:
            continue
        t = _parse(frm)
        if frm[:10] == day_s and t.hour == 0:
            v1 = viewers
        if day - timedelta(days=7) <= t < day and viewers:
            pre7.append(viewers)
    return {
        "lnV1": math.log(max(1.0, v1)) if v1 else None,
        "lnPREM": math.log(max(1.0, statistics.mean(pre7))) if pre7 else None,
    }


def build_library(case):
    """The reference class from the case's comparables.

    Each entry: {"feat": {"lnV1", "lnPREM"}, "curve": {hour: viewers}} for
    the comparable's release day (UTC), hours 1..24. Launches without an
    hour-1 print carry no usable curve and are dropped. The Grand Theft Auto
    VI category's own pre-release history (tier target-history) has no
    release day, so it drops out here by itself.
    """
    lib = []
    for comp in case.get("comparables", []):
        hourly = {}
        for row in comp.get("hourly", []):
            if row.get("viewers"):
                hourly[row["from"]] = (row["viewers"], row.get("channels"))
        day_s = comp["day_start"][:10]
        curve = {}
        for frm, (viewers, _ch) in hourly.items():
            if frm[:10] == day_s:
                curve[int(frm[11:13]) + 1] = float(viewers)
        if 1 not in curve:
            continue
        feat = launch_features(hourly, comp["day_start"])
        lib.append({"feat": feat, "curve": curve})
    return lib


def target_features(case):
    """Features of the target launch: its own history + hour-1 print."""
    hourly = {}
    for row in case.get("history_hourly", []):
        if row.get("viewers"):
            hourly[row["from"]] = (row["viewers"], row.get("channels"))
    feat = launch_features(hourly, case["day_start"])
    known = next((k for k in case.get("known", []) if k["hour"] == 1), None)
    if known is not None and known.get("viewers"):
        feat["lnV1"] = math.log(max(1.0, known["viewers"]))
    return feat


def _solve(matrix, vec):
    """Solve a small dense linear system by Gaussian elimination."""
    n = len(vec)
    rows = [row[:] + [vec[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[piv] = rows[piv], rows[col]
        if abs(rows[col][col]) < 1e-12:
            return None
        for r in range(col + 1, n):
            factor = rows[r][col] / rows[col][col]
            for c in range(col, n + 1):
                rows[r][c] -= factor * rows[col][c]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (rows[i][n] - sum(rows[i][j] * out[j] for j in range(i + 1, n))) / rows[i][i]
    return out


def ols(points, keys):
    """Least squares of y on [1] + features. points: [(feat, y)]."""
    k = len(keys) + 1
    normal = [[0.0] * k for _ in range(k)]
    rhs = [0.0] * k
    for feat, y in points:
        row = [1.0] + [feat[key] for key in keys]
        for i in range(k):
            rhs[i] += row[i] * y
            for j in range(k):
                normal[i][j] += row[i] * row[j]
    return _solve(normal, rhs)


def _local_library(lib, target_ln_v1):
    """Size-matched reference class; the whole library when too few match."""
    near = [r for r in lib
            if r["feat"].get("lnV1") is not None
            and abs(r["feat"]["lnV1"] - target_ln_v1) <= LOCAL_HALF_WIDTH]
    return near if len(near) >= MIN_LOCAL else lib


def _baseline_quantiles(p1, hour):
    """House-baseline shape: persistence with a widening random-walk spread."""
    return [p1 * math.exp(z * 0.15 * math.sqrt(hour - 1)) for z in Z]


def ols_view(target, lib):
    """View 1: per-hour local OLS of ln(viewers) on [lnV1, lnPREM]."""
    keys = ["lnV1", "lnPREM"]
    if target.get("lnPREM") is None:
        keys = ["lnV1"]
    rows = _local_library(lib, target["lnV1"])
    out = {}
    for hour in range(2, 25):
        pts = [(r["feat"], math.log(r["curve"][hour])) for r in rows
               if hour in r["curve"] and all(r["feat"].get(k) is not None for k in keys)]
        coef = ols(pts, keys) if len(pts) >= 6 else None
        if coef is None:
            out[hour] = _baseline_quantiles(math.exp(target["lnV1"]), hour)
            continue
        x = [target[k] for k in keys]
        center = coef[0] + sum(c * v for c, v in zip(coef[1:], x))
        resid = []
        for feat, y in pts:
            pred = coef[0] + sum(c * feat[k] for c, k in zip(coef[1:], keys))
            resid.append(y - pred)
        center += statistics.median(resid)
        sd = statistics.pstdev(resid) * OLS_SPREAD if len(resid) > 1 else 0.5
        out[hour] = [math.exp(center + z * sd) for z in Z]
    return out


def shape_view(target, lib):
    """View 2: one-factor shape model on the median log-ratio curve."""
    keys = ["lnV1", "lnPREM"]
    if target.get("lnPREM") is None:
        keys = ["lnV1"]
    rows = _local_library(lib, target["lnV1"])
    median_curve = {}
    for hour in range(2, 25):
        ratios = [math.log(r["curve"][hour]) - math.log(r["curve"][1])
                  for r in rows if hour in r["curve"] and 1 in r["curve"]]
        median_curve[hour] = statistics.median(ratios) if ratios else 0.0
    # Each launch's own (level c, amplitude s) on the median curve.
    fits = []
    for r in rows:
        xs, ys = [], []
        for hour in range(2, 25):
            if hour in r["curve"] and 1 in r["curve"]:
                xs.append(median_curve[hour])
                ys.append(math.log(r["curve"][hour]) - math.log(r["curve"][1]))
        if len(xs) < 10:
            continue
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx) if sxx > 0 else 1.0
        fits.append((r, my - slope * mx, slope))
    if len(fits) < 6:
        return None
    x_target = [target[k] for k in keys]
    predicted = []
    for which in (1, 2):  # 1 = level c, 2 = amplitude s
        pts = [(r["feat"], c if which == 1 else s) for r, c, s in fits
               if all(r["feat"].get(k) is not None for k in keys)]
        coef = ols(pts, keys) if len(pts) >= 6 else None
        if coef is None:
            predicted.append(0.0 if which == 1 else 1.0)
        else:
            predicted.append(coef[0] + sum(c * v for c, v in zip(coef[1:], x_target)))
    level, amplitude = predicted[0], min(2.0, max(0.0, predicted[1]))
    out = {}
    for hour in range(2, 25):
        resid = []
        for r, c_i, s_i in fits:
            if hour in r["curve"] and 1 in r["curve"]:
                actual = math.log(r["curve"][hour]) - math.log(r["curve"][1])
                resid.append(actual - (c_i + s_i * median_curve[hour]))
        sd = statistics.pstdev(resid) if len(resid) > 1 else 0.5
        center = target["lnV1"] + level + amplitude * median_curve[hour]
        out[hour] = [math.exp(center + z * sd) for z in Z]
    return out


def forecast_case(case):
    """Blend the two views 50/50 in log space; validate and round."""
    target = target_features(case)
    if target.get("lnV1") is None:
        raise ValueError("case has no hour-1 print")
    lib = build_library(case)
    if not lib:
        view_a = view_b = None
    else:
        view_a = ols_view(target, lib)
        view_b = shape_view(target, lib)
    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        if view_a is not None and view_b is not None:
            qs = [math.exp(SHAPE_WEIGHT * math.log(max(1.0, b))
                            + (1.0 - SHAPE_WEIGHT) * math.log(max(1.0, a)))
                  for a, b in zip(view_a[hour], view_b[hour])]
        elif view_a is not None:
            qs = view_a[hour]
        else:
            qs = _baseline_quantiles(math.exp(target["lnV1"]), hour)
        qs = [min(1e9, max(1.0, q)) for q in qs]
        qs = [round2(q) for q in qs]
        for j in range(1, 5):
            qs[j] = max(qs[j], qs[j - 1])
        hours.append({"hour": hour, "q": qs})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
