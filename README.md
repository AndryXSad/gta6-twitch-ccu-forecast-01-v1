# GTA VI launch-day Twitch CCU forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/AndryXSad/gta6-twitch-ccu-forecast-01-v1/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/AndryXSad/gta6-twitch-ccu-forecast-01-v1/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A make.fun `gta6-twitch-ccu-forecast-01` entry. It forecasts, for each of
hours 2–24 of Grand Theft Auto VI's release day (2026-11-19 UTC), five
quantiles (5%, 25%, 50%, 75%, 95%) of the concurrent Twitch viewers in the
"Grand Theft Auto VI" category, from the first hour's print and the
launch-day curves of past big game launches shipped inside each case.

## How it works

`main.py` (Python 3.13, standard library only, no network) blends two views
of the same curve 50/50 in log space:

1. **Local OLS** — per hour, least squares of log viewers on log hour-1
   viewers and log mean pre-release viewership, over the comparable launches
   whose size is within 2.5 log units of the target's, with residual spread
   shrunk by 0.8.
2. **Shape factor** — each launch's log-ratio curve is fit as level +
   amplitude × the library's median log-ratio curve; level and amplitude are
   regressed on launch size, and per-hour residual spread is taken around the
   launches' own one-factor fits.

Full reasoning, the numbers behind every choice, and what was tried and
dropped: [DESIGN.md](DESIGN.md).

## Local results (practice cases, scored with the exact pinball loss from RULES.txt)

| case | launch | loss |
| ---- | ------ | ---- |
| p00 | Marvel's Wolverine (2026-09-15) | 0.122 |
| p01 | Red Dead Redemption 2 (2018-10-26) | 0.200 |
| p02 | God of War Ragnarök (2022-11-09) | 0.123 |
| p03 | Marvel's Spider-Man 2 (2023-10-20) | 0.173 |
| **overall** | | **0.154** |

For reference: the house baseline scores 0.387 on the same cases, and the
live top-10 bar at the time of building was 0.145–0.157. Leave-one-out over
the 38 comparables: 0.428 (dominated by small launches, which are far
wilder than a mega-launch like GTA VI).

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=<kit input dir> MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` in the input directory, writes `<id>.out` next to it.
Deterministic (byte-identical across runs), ~0.3 s for four cases.

## License

MIT — see [LICENSE](LICENSE).
