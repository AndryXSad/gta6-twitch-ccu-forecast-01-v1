# Design record — gta6-twitch-ccu-forecast-01-v1

Reasoning record for the entry in `main.py`. Written by the agent session
that built it, from the kit's practice cases and the comparables shipped in
them. No top-entry code was copied: the design below comes from the data
(the leaderboard titles only named the families — rolling-midnight
comparables, log-ratio regression, quantile fans — that the analysis below
then tested independently).

## The task, restated

One case = one launch day. Input: hour 1's Twitch print (viewers,
channels), the target's hourly history up to the checkpoint, and 38 past
launches' hourly curves (`comparables`, 14 days before to 3 days after each
release). Output: for hours 2–24, five quantiles of that hour's viewers.
Score: mean pinball loss on the log scale over 23 hours × 5 levels; lower is
better. A forecast whose five quantiles are equal scores its mean absolute
log error, so median accuracy and honest spread are scored on one scale.
For a well-calibrated normal predictive distribution with log-sd σ, the
expected loss is ≈ 0.5σ.

Practice ground truth used here: the four practice cases' answers were read
from SullyGnome.com's "Average viewers" series (the same source the kit's
NOTICE.txt names), one targeted request per launch; the hour-1 values match
the cases' `known` prints exactly. The local scorer implements the RULES.txt
pinball formula exactly and reproduces the house baseline's stated practice
loss (0.387097 vs "about 0.387"), which validates the whole local pipeline.

## What the data says

- The median log-ratio curve ln(V_h / V_1) dips to ≈ −0.3 at hours 3–5
  (deep night), then ramps from hour 5 (US East unlock) to a peak of ≈
  +0.87 at hour 19, and falls to ≈ +0.71 at hour 24. Classic diurnal shape
  of a rolling-midnight console launch.
- The spread of that curve across launches is enormous (sd 0.30 at hour 2,
  ≈ 2.17 at hours 17–22) — because the library mixes launches of wildly
  different sizes: a small launch grows 9× from a tiny hour 1, a huge one
  barely grows at all.
- The size effect is the dominant signal. Regressing ln(V_h) on ln(V_1) per
  hour, the slope collapses from ≈ 1 at hour 2 to ≈ 0.06 at the evening
  peak: the peak is nearly the same size whatever hour 1 was, because the
  peak is capped by how many people watch Twitch at that hour at all.
  Conditioning on ln(V_1) cuts the residual sd from ≈ 2.17 to ≈ 0.75–1.0.
- Restricting to big launches (lnV1 ≥ 10, n = 26) cuts it further to
  ≈ 0.45. The practice launches are all big (lnV1 10.06–12.50), and GTA VI
  will be bigger still — so the reference class must be size-matched, not
  the whole library.
- A second anchor helps: lnPREM, the log mean viewers over the 7 days
  before release (the game's overall hype), tightens the fit a little on
  top of lnV1. Log channels at hour 1 (lnCH1) helps marginally. A "year"
  (era) predictor hurts badly (0.18–0.21 vs 0.16) — with ~20 points in the
  local window it fits noise — and was dropped. Slope shrinkage toward the
  pooled slope also hurts badly (0.33–0.40) and was dropped.

## What was tried (practice loss / leave-one-out over the 38 comparables)

| model | practice | LOO |
| ----- | -------- | --- |
| house baseline (starter) | 0.387 | — |
| global OLS on lnV1 | 0.255 | 0.446 |
| + clean library (tier comparable, not simultaneous) | 0.244 | 0.453 |
| + lnPREM | 0.220 | 0.421 |
| local window ±2.5 on lnV1 | 0.186 | 0.382 |
| local ±2.5 + lnPREM | 0.175 | 0.357 |
| local ±2.5 + lnPREM, spread 0.8 | 0.165 | 0.366 |
| kernel-weighted (Epanechnikov 2.5) + lnPREM, spread 0.75 | 0.161 | 0.480 |
| k-nearest-neighbour quantile fan (k = 8) | 0.204 | 0.439 |
| log-ratio fan, local ±2.5 | 0.254 | 0.576 |
| one-factor shape model, local ±2.5 | 0.161 | 0.539 |
| **blend 50/50 OLS + shape (chosen)** | **0.154** | **0.428** |

The blend is a flat plateau, not a sharp optimum: blend weights 0.4–0.6 and
spreads 0.8–1.0 all land at 0.154–0.158, so the chosen point (weight 0.5,
OLS spread 0.8, shape spread 1.0) is robust rather than tuned to noise.
Per-case practice losses of the chosen entry: p00 0.122, p01 0.200, p02
0.123, p03 0.173. The two most representative cases for GTA VI (p02/p03:
big recent Sony exclusives) average 0.148.

Why the blend works: the OLS view is best when the launch behaves like the
local average for its size; the shape view is best when the launch's curve
is a scaled copy of the median curve (it nails the small Wolverine launch,
0.103, where the OLS struggles). Their errors are partly independent, so
the geometric mean of the two quantile sets beats both.

Why LOO is much worse (0.43): it is dominated by the library's small
launches, whose relative swings are wild. GTA VI is a mega-launch; the
practice cases (all big) are the relevant yardstick, and the final case's
library is bigger still (42 comparables, including the four practice
launches).

## The chosen entry (locked)

- **View 1 — local OLS.** Per hour, OLS of ln(viewers) on [lnV1, lnPREM]
  over comparables with |lnV1 − target| ≤ 2.5 (≥ 10 launches, else the whole
  library). Median = fitted value + median residual; quantiles = median +
  z_τ × residual sd × 0.8.
- **View 2 — shape factor.** Median log-ratio curve m_h over the same
  local window. Each launch fit as ln(V_h/V_1) = c + s·m_h; (c, s)
  regressed on [lnV1, lnPREM]; target curve = its predicted (c, s) on m_h;
  per-hour residual sd around launches' own one-factor fits; s clamped to
  [0, 2].
- **Blend.** Geometric mean (log-space 50/50 average) of the two views'
  quantiles, rounded to 2 decimals half-up, clamped to (0, 1e9],
  non-decreasing.
- **Fallbacks.** A per-hour OLS that cannot be fit (< 6 points) falls back
  to the house-baseline shape for that hour; if the library is empty, the
  whole forecast is the baseline; if the target has no pre-release history,
  both views use lnV1 alone.

## Revisi v1.1 (17 Nov 2026) — extrapolation guard

Change to `main.py` (in-place edit, surviving lines added): a new helper
`_clamp_ln_v1(target, rows)` plus one call line at the top of each view
(`ols_view`, `shape_view`), and a paragraph in the module docstring. The
helper clamps the target's lnV1 to the local reference class's observed
[min, max] before either view's regressions use it. Inside the range it is
a no-op; beyond the range the forecast stays at the biggest observed
launch's level instead of following the lnV1 slope past the data.

Why: v1 extrapolates linearly in lnV1 past the library max (ELDEN RING,
lnV1 13.68). GTA VI's hour-1 print will likely sit at or above that max.
At hour 2 the OLS slope on lnV1 is ~1, so an extreme hour-1 print would
be carried almost 1:1 into the hour-2 forecast, and the evening peak —
capped in reality by how many people watch Twitch at all — would be
pushed up with it. The clamp is the defensive shape for that tail.

Candidates tried and REJECTED (all measured with the exact local scorer,
practice + leave-one-out over the 38 comparables):

| candidate | practice | LOO all | LOO lnV1>=12 |
| --------- | -------- | ------- | ------------ |
| v1 (baseline) | 0.154426 | 0.4283 | 0.1885 |
| + lnCH1 as 3rd predictor | 0.152863 | 0.4439 | 0.1899 |
| + OLS spread 0.8 -> 0.7 | 0.153786 | 0.4355 | 0.1910 |
| + shape weight 0.5 -> 0.55 | 0.154062 | 0.4377 | 0.1886 |
| + lnCH1 + spread 0.7 + weight 0.55 | 0.152031 | 0.4620 | 0.1943 |
| + guard only (SHIPPED) | 0.154426 | 0.4315 | 0.1885 |

Every practice gain came with a worse LOO — including on the 26 big
launches (lnV1 >= 10) and on the 7 biggest (lnV1 >= 12), the reference
class closest to GTA VI — so the practice gains are 4-case noise fits,
not genuine improvements. They were not shipped. The guard is the only
change whose practice loss is unchanged and whose cost is ~zero: LOO all
moves only because ELDEN RING's own LOO case is clamped by 0.02 log units
(0.0646 -> 0.0647); the lnV1>=12 mean is identical (0.1885).

Verification of the shipped guard: synthetic target with hour-1 print
3,000,000 viewers (lnV1 14.91, far above the library max) — v1 forecasts
hour-2 median 2,973,004 and hour-19 q95 2,398,910; v1.1 forecasts hour-2
median 806,420 and hour-19 q95 1,209,383, against ELDEN RING's true
hour-2 801,446 / hour-19 833,065. Practice loss before/after:
0.154426 -> 0.154426 (p00 0.122227, p01 0.199600, p02 0.123243,
p03 0.172636 — byte-identical outputs, sha256 p00 162935983d44,
p01 b9c915af6cd0, same as v1). Determinism (2 runs byte-identical),
format (23 rows, hours 2-24, 5 finite quantiles in (0, 1e9],
non-decreasing) and stdlib-only imports re-verified after the edit.

## Checks run on the submitted code

- Practice loss 0.154426 (reproduces the experiment's 0.1544 exactly).
- Typical miss / 90% coverage: p00 17.0% / 1.000, p01 40.6% / 0.913,
  p02 23.7% / 1.000, p03 32.6% / 0.870 (overall coverage 0.946 — bands a
  touch wide, accepted: the pinball loss, not coverage, ranks).
- Determinism: two runs byte-identical (sha256 recorded in the build log).
- Runtime ≈ 0.3 s for four cases (limit 8 s per case).
- Output format validated: exactly 23 rows, hours 2–24, five finite
  quantiles in (0, 1e9], non-decreasing, files ≈ 1.5 KB (limit 65,536).
- Imports checked against `sys.stdlib_module_names`: json, math, os,
  statistics, sys, datetime, pathlib — stdlib only, no network.

## Limits, stated honestly

- The practice loss is measured on four launches; the final is one launch
  (GTA VI) whose hour-1 print will likely sit beyond the largest comparable
  (lnV1 ≈ 13.7), so both views extrapolate linearly in lnV1. The local
  window still holds 15+ launches there, but an extreme hour-1 print is the
  main extrapolation risk.
- p01 (RDR2, 2018) is the weak case (0.200): the model under-predicts its
  mid-day by up to +0.6 log units. Its 2018 era is the likely cause, and
  the era predictor that would fix it fits noise elsewhere, so it was left
  out. GTA VI is a 2026 launch, so this weakness should matter less for
  the final than for the practice mean.
- No entry can beat the house model forecast on the final by construction
  of the practice numbers alone; the practice board only says this entry
  would sit around 5th–6th (bar 0.145–0.157) if the final behaved like the
  practice.
