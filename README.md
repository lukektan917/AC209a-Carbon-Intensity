# Predicting Low-Carbon Hours for Data-Center Computing (PJM)

## Build the dataset

```bash
pip install -r requirements.txt
python build_dataset.py            # 2019 -> latest; ~2 GB of downloads, a few minutes
```

Options: `--start 2022 --end 2024`, `--no-weather`, `--other-factor 400` (sensitivity for "Other" fuels), `--keep-raw`.

Outputs:

- `data/pjm_hourly.csv`: one row per hour.
- `data/emission_factors_used.csv`: kg CO₂/MWh by fuel and year.

Downloads are cached in `data/interim/`. Delete that folder to rebuild from scratch.

## Running in Google Colab

Colab already has everything in `requirements.txt` installed. Each notebook starts with a setup cell (section 0) that gets the project files in one of two ways:

1. **Google Drive (default).** Put this project folder in Google Drive. If a teammate shared it, add a shortcut to it in My Drive. Open the notebook from Drive with **Open with → Google Colaboratory**. Set `DRIVE_PATH` in the setup cell, then run all cells.
2. **GitHub.** In Colab, go to **File → Open notebook → GitHub**, tick **Include private repos**, and pick the notebook. Add a GitHub personal access token as a Colab secret named `GITHUB_TOKEN`, set `SOURCE = "github"`, and run all cells. The cell clones the repo to `/content`. Colab doesn't keep files between sessions, so save changes with **File → Save a copy in GitHub**.

If `data/pjm_hourly.csv` is missing, the setup cell runs `build_dataset.py` first.

## EDA

`eda.ipynb` covers data quality, trend, daily patterns, generation mix, drivers, scheduling headroom and baselines, forecastability, weather, and the interchange sensitivity check. The summary of findings is at the end of the notebook. Figures are saved to `figures/` for the writeup.

## Sources

| Data | Where | Notes |
|---|---|---|
| Demand, day-ahead demand forecast, generation by fuel, interchange | [EIA-930 six-month files](https://www.eia.gov/electricity/gridmonitor/about) | Fuel mix starts Jul 2018. EIA's cleaned `(Adjusted)` values are used when present. |
| CO₂ per unit of fuel | [EIA CO₂ coefficients](https://www.eia.gov/environment/emissions/co2_vol_mass.php) | kg CO₂ / MMBtu |
| Heat rates | [EIA Electric Power Annual, Table 8.1](https://www.eia.gov/electricity/annual/html/epa_08_01.html) | Btu / kWh, by year |
| Weather | [NOAA GHCNh](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly) | 6 airports: PHL, ORD, IAD, BWI, PIT, CMH. GHCNh replaced NOAA's older ISD "Global Hourly" files, which stop partway through 2025 |

## Methods notes (responses to proposal feedback)

**Units.** EIA's CO₂ coefficients are per MMBtu of *fuel*. EIA-930 reports MWh of *electricity*. Each coefficient is converted with that year's average heat rate:

```
kg CO₂/MWh = (kg CO₂/MMBtu) × (Btu/kWh) / 1000
```

For 2025, this gives coal ≈ 1,022, natural gas ≈ 412 and oil ≈ 813 kg CO₂/MWh. Nuclear, hydro, wind, solar and storage are 0. See `emission_factors.py` for all the assumptions.

Hourly intensity = Σ(generation by fuel × factor) / Σ(generation by fuel). Negative values (pumped-storage pumping, battery charging) are treated as 0 because they are consumption, not generation.

Intensity is left blank when the fuel breakdown covers less than 80% of reported net generation. That happens when fuels are missing from the report. This leaves 610 hours blank:

- 564 are in **January 2020**, when every fuel is reported at about 77% of total net generation.
- A handful are scattered elsewhere. For example, on 1–2 Oct 2022 PJM reported about 300 MW by fuel against 75 GW total.

Drop these hours or interpolate them, and say which in the writeup.

**Interchange.** There are two versions:

- `ci_prod_kg_per_mwh` (**production-based**, the main target): emissions from power generated inside PJM, divided by that generation. Imports and exports are ignored. PJM is usually a net exporter.
- `ci_cons_kg_per_mwh` (**consumption-based**, sensitivity check): a first-order import adjustment.
  - Power PJM keeps (generation − exports) is counted at PJM's intensity.
  - Imports from each neighbor (MISO, NYISO, TVA, Duke, CPLE, CPLW, LG&E-KU) are counted at that neighbor's own production-based intensity, computed the same way from EIA-930.
  - It does not trace power that neighbors themselves imported.

Compare scheduling savings under both versions. If they barely differ, the interchange question is answered empirically.

## Columns in `pjm_hourly.csv`

| Column | Meaning |
|---|---|
| `datetime_utc` | **End** of the hour, UTC (EIA convention) |
| `datetime_local`, `date_local`, `hour_local`, `dow`, `month` | Eastern time. `hour_local` is the hour the interval *starts* (0 = midnight–1am). `dow` 0 = Monday |
| `demand_mw`, `demand_forecast_mw` | Actual demand; EIA's day-ahead demand forecast (known in advance, so it can be a feature) |
| `net_gen_mw`, `total_interchange_mw` | Reported totals. Interchange > 0 means net exports |
| `gen_<fuel>_mw` | coal, gas, nuclear, oil, hydro, solar, wind, storage, other, unknown |
| `fuel_sum_mw` | Sum of the fuel columns (negatives set to 0) |
| `co2_t` | Metric tons of CO₂ emitted by PJM generation that hour |
| `ci_prod_kg_per_mwh`, `ci_cons_kg_per_mwh` | Carbon intensity (see above) |
| `imports_mw`, `exports_mw`, `ic_<BA>_mw` | Flows with each neighbor. > 0 means PJM exports to it |
| `ci_<BA>_kg_per_mwh` | Each neighbor's production-based intensity |
| `temp_c`, `dewpoint_c`, `wind_ms`, `n_weather_stations` | **Observed** weather, averaged over the airports |
| `eia_imputed` | EIA filled at least one value in this hour |
| `qa_*`, `qa_any` | Quality flags (see below) |

### Quality flags

- `qa_missing_hour`: no EIA data for this hour.
- `qa_balance_mismatch`: demand differs from net generation − interchange by more than 2%. It is near 0% in 2021–24, but common in 2019–20 and again from May 2025 on, mostly in summer, with demand 1–3 GW below generation − interchange. This is in EIA's data. It affects the demand columns, **not** carbon intensity, which uses only the fuel mix.
- `qa_fuel_sum_mismatch`: the fuel breakdown differs from total net generation by more than 5%. A ±3% daily-cycle gap is normal for PJM.
- `qa_neighbor_ci_filled`: a neighbor's intensity was missing, so PJM's was used for its imports.
- `info_interchange_mismatch`: reported total interchange disagrees with the sum of the per-neighbor flows. This is very common and is EIA's own inconsistency, so it is **not** in `qa_any`.

## Things to watch for in modeling

- **Leakage:** for a day-ahead forecast, only use information available the day before. `demand_forecast_mw` is fine. Observed weather and observed generation for the target day are not; lag them by at least 24 h, or label results as "oracle weather".
- **Hour convention:** EIA timestamps mark the end of the hour. Use `hour_local` (start-of-hour) for anything people will read.
- **Category changes:** EIA split hydro, solar and wind into subcategories and added storage starting with the Jul–Dec 2024 files. The script sums the subcategories back together, so the columns are consistent across years.
- **Trend:** the grid gets cleaner over time, so split train/validation/test by time and check for drift.
