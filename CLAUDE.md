# AC 209A project — Predicting low-carbon hours on the PJM grid

Handoff notes for whoever (human or Claude Code) picks this up next. Read this first.

## Project in one paragraph

Data-center workloads like training jobs and batch processing can be shifted in time. The carbon intensity of
the grid (g CO2 per kWh) varies hour to hour because the generation mix changes. The question: **can the
lowest-carbon hours of the next day be predicted accurately enough to reduce emissions of a flexible
workload?** We forecast hourly carbon intensity one day ahead for the PJM balancing authority, use the forecast
to schedule a simulated job, and compare emissions against (a) running immediately and (b) a perfect-foresight
schedule. Owner: Sunny (AC 209A group project). The proposal text is not final.

## Where things are

```
ac209a_carbon/
├── CLAUDE.md                 ← this file
├── pjm_carbon_eda.ipynb      ← preliminary EDA, fully executed, all preprocessing shown in-notebook
├── requirements.txt
├── .gitignore                (ignores data/)
└── data/
    ├── PJM.xlsx              ← RAW input, 115 MB, EIA Grid Monitor per-BA download (not in git)
    └── pjm_hourly.csv        ← cache written by the notebook on first run (sheet "Published Hourly Data")
```

Raw data URL: `https://www.eia.gov/electricity/gridmonitor/knownissues/xls/PJM.xlsx` (EIA-930). Re-download
to refresh; delete `data/pjm_hourly.csv` afterwards so the notebook re-parses. Coverage: 2015-07-01 →
2026-11-11 hourly; **fuel mix and CO2 columns only from mid-2018**, so the analysis window is 2019-01-01 onward.

To run: `pip install -r requirements.txt` then open the notebook. First run takes ~30 s to parse the xlsx.

## What the EDA established (don't redo these — build on them)

Data facts
- One row per hour, complete UTC index, no duplicates, no gaps (99,649 rows). Use the `UTC time` column as
  the key and derive local hour from it; EIA's `Hour` column is hour-ending 1–24 (25 on DST fall-back) — avoid.
- Interchange sign convention: positive = PJM **exports**. Neighbours: CPLE, CPLW, DUK, LGEE, MISO, NYIS, OVEC, TVA.
- Fuel columns with data for PJM: COL, NG, NUC, OIL, WAT, SUN, WND, OTH. GEO/PS/SNB/WNB/BAT/OES/UES/UNK are all empty.
- `Demand forecast` is PJM's own day-ahead demand forecast (MAPE ≈ 3.6 %). It is legitimately available at
  prediction time → use it as a feature.

Units (this answers TA comment #1 — "check factors and generation use compatible units")
- The workbook's `CO2 Factor: {COL,NG,OIL}` columns are **lb CO2 per kWh** (coal ≈ 2.19, gas ≈ 0.86, oil ≈ 2.06),
  i.e. they already include a heat rate. Verified two ways: (1) `NG:fuel × Factor / Emissions:fuel = 2.20462` (lb/kg)
  exactly, so emissions columns are **metric tons**; (2) EIA's published fuel factors (kg CO2/MMBtu: coal 95.5,
  gas 53.1, resid oil 78.8) × typical heat rates (10.4 / 7.4 / 12 MMBtu/MWh) reproduce the factors within ~1–3 %.
- `CO2 Emissions Intensity for Generated/Consumed Electricity` are **lb CO2/kWh**. Multiply by 453.592 for g/kWh.
  PJM averages ~340 g/kWh (0.75 lb/kWh).
- We reproduce EIA's emissions, positive generation and intensity exactly from the raw columns (max rel. diff 0).
  Formula: E_gen = Σ_f NG_f × Factor_f / 2.20462 + CO2 Emissions: Other; I_gen = E_gen × 2.20462 / Σ_f max(NG_f,0).

Imports/exports (this answers TA comment #2 — "explain how exchanges are handled")
- PJM is a net exporter 97 % of hours; |net interchange| is ~4 % of demand (median), 8 % at the 95th pct.
- Production-based vs consumption-based intensity: correlation 0.9965, typical difference ±0.01 lb/kWh (~1–2 %).
  EIA values imports at the exporting BA's hourly generated intensity (one-step attribution, no network tracing).
- **Decision:** primary target = production-based intensity (`ci`, depends only on PJM's own generation);
  consumption-based (`ci_cons`) reported as a robustness check. State this explicitly in the report.

Data-quality decisions already applied in the notebook (section 6)
- 5 hours on 2022-10-01/02 have Positive Generation ≈ 300 MWh (fuel columns missing) → target set to NaN.
- Same hours have negative consumed electricity → `ci_cons` NaN.
- 6 hours over 5 days (2019-12-11, 2020-04-10, 2020-07-24, 2021-10-18/19) have demand forecasts off by >2× (some ~1e8 MWh) → forecast NaN.
- Rows are never deleted; the hourly index stays complete.

Target behaviour (2019–2026)
- Mean 341 g/kWh, sd 44. Strong seasonality (winter/summer high, spring/fall low), slow downward trend (coal retirements).
- Diurnal shape: trough ~3–4 am local, secondary dip ~2–4 pm in spring/fall/winter (solar), peak ~9 pm. Summer
  rises monotonically from night trough to evening peak. Weekends ~15–20 g/kWh lower.
- Within-day spread: a perfect-foresight 4-hour block beats the day-mean hour by ~6 % (median 5.7 %, IQR 4–8 %, max ~22 %).
  Argmin hour is bimodal (early morning / mid-afternoon), so a fixed window is not enough.

Baselines (evaluated 2024–2026, so any model must beat these on the same period)
| forecast | MAE g/kWh | MAPE | share of oracle gain captured (4-h job) |
|---|---|---|---|
| 24-h persistence | 16.2 | 5.1 % | 63 % |
| mean of 24-h and 7-day persistence | 18.7 | 5.8 % | 68 % |
| 7-day persistence | 28.8 | 8.8 % | 55 % |
| climatology (month×hour×weekend, 2019–23) | 34.7 | 11.3 % | 16 % |

## Modelling table

The notebook builds `m` (index = UTC, 2019-01-01 →, 68,683 rows) with: `ci` (lb/kWh), `ci_g` (g/kWh), `ci_cons`,
fuel shares `share_col/ng/nuc/wat/sun/wnd/oil/oth`, `share_renew`, `share_fossil`, `Demand`, `Demand forecast`,
`demand_fc_err`, `Total interchange`, neighbour columns, `hour/dow/month/year/date/is_weekend/season`, `local`.
If you factor the preprocessing out into a module, keep it identical to notebook sections 1–6.

## Next steps (suggested order)

1. **Feature engineering for day-ahead forecasting.** At prediction time (say 12:00 on day D for all 24 hours of
   D+1) you may use: everything through day D (lags 24 h, 48 h, 168 h of intensity and fuel shares), calendar
   features, and PJM's demand forecast for D+1. You may NOT use D+1 actual generation. Be strict about this.
2. **Weather.** Add NOAA ISD hourly data (temperature, wind speed, cloud/sky cover) for 3–5 stations across PJM
   (e.g. Chicago, Pittsburgh, Columbus, Philadelphia, Washington). Wind speed → `share_wnd`, sky cover → `share_sun`,
   temperature → demand. Ideally use *forecast* weather; if only observed is available, say so (it's an upper bound).
3. **Models.** Start with ridge/lasso and gradient boosting (course-standard), one model with hour as a feature vs
   24 per-hour models. Evaluate with rolling-origin / blocked time-series CV. Never random splits.
4. **Metrics.** MAE/MAPE of hourly intensity; within-day Spearman rank correlation; and the scheduling metric
   "share of oracle gain captured" for 1-h, 4-h and 8-h jobs (function `simulate` in notebook §10 — extend to
   contiguous blocks and deadlines).
5. **Non-stationarity.** Weight recent years more, or add a trend term; the 2024+ mix (less coal, more solar) differs from 2019.
6. **Generalise.** Repeat for one more BA (MISO or CAISO) using the same per-BA xlsx download pattern.

## Conventions

- Keep everything reproducible from `data/PJM.xlsx`; never commit `data/` (see .gitignore).
- Intensity unit in code: lb/kWh in `ci` (EIA's native), g/kWh in `ci_g` for plots and the report.
- Time zone: store UTC, compute hour-of-day in `America/New_York`.
- Course context: AC 209A (Data Science I). Expect to be graded on EDA clarity, correct validation, and honest
  comparison against baselines; the group has a 20 % coding assessment too, so keep code readable, not clever.
