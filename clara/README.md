# Clara: ERCOT's own fuel-mix data (Texas)

This folder uses **ERCOT's own published generation-by-fuel data** to study when the Texas grid is cleanest. It is a second source next to the team's EIA-930 data (Amy's `TEX` region).

## What's here

| File / folder | Contents |
|---|---|
| `209a.ipynb` | EDA notebook: loads ERCOT's 15-minute data, turns it into an hourly table, calculates carbon intensity, and makes the charts below |
| `raw/` | ERCOT Fuel Mix Report files as downloaded: `IntGenbyFuel2024.xlsx`, `IntGenbyFuel2025.xlsx`, `IntGenbyFuel2026.xlsx` |
| `clean/` | Output: `ercot_hourly_clean_2026.csv` (hourly table) and saved figures |

## Data source

| | |
|---|---|
| **Source** | ERCOT Fuel Mix Report: https://www.ercot.com/gridinfo/generation |
| **Format** | One Excel file per year, one sheet per month. One row = one day × one fuel; one column per 15-minute interval (MWh) |
| **Fuels** | Biomass, Coal, Gas, Gas-CC (combined cycle), Hydro, Nuclear, Other, Solar, Wind, WSL (battery charging, negative) |
| **Time** | Local Central time; interval columns mark the **end** of each 15 minutes |

## How the hourly table is built

1. Read all 12 monthly sheets and stack them.
2. Reshape so each row is one 15-minute interval for one fuel, then add the four intervals in each hour.
3. Result: one row per hour (Jan – Oct 2026: 7,295 hours), one column per fuel, in MWh.
4. **Carbon intensity** (kg CO₂/MWh) = Σ(generation × emission factor) ÷ total generation. WSL (charging) is left out.

**Emission factors (kg CO₂/MWh):** coal 1,021; Gas-CC 398; Gas 557; all others 0. ERCOT's data separates efficient combined-cycle gas plants from other gas plants, which EIA-930 cannot do.

## Columns in the hourly table

| Column | Units | Meaning |
|---|---|---|
| index (`hour`) | local time | Start of the hour, Central time |
| `Biomass` … `Wind` | MWh | Generation by fuel in that hour |
| `total_gen` | MWh | Sum of all fuels (WSL excluded) |
| `co2_kg` | kg CO₂ | CO₂ emitted in that hour |
| `carbon_intensity` | kg CO₂/MWh | CO₂ per unit of electricity |

## First findings (Jan – Oct 2026)

- **Average carbon intensity:** 292 kg CO₂/MWh.
- **Midday is cleanest.** The average is lowest at 11 a.m. (212) and highest around 9–10 p.m. (~343), because of solar.
- **Seasons matter.** March was cleanest (224) and September dirtiest (334).
- **The cleanest hour of the day** was 10 or 11 a.m. on 147 of 304 days, and between 9 a.m. and 3 p.m. on 268 days.
- **Scheduling prize.** For a flexible job, running at a random time gives 292 kg/MWh on average, always at 10 a.m. gives 217 (**26% cleaner**), and always at the day's best hour gives 201 (**31% cleaner**).

## Notes and next steps

- The notebook currently analyses **2026 only**; the 2024 and 2025 files are in `raw/` and will be added to match the team's focus period (2023 – Oct 2026).
- File paths in the notebook point to my computer and need to be changed to `raw/` and `clean/` to run elsewhere.
- The spring daylight-saving day has one missing hour (40 empty 15-minute values).
- **To join with Amy's EIA-930 table:** convert the hour to UTC end-of-hour (`utc_end`), and map fuels to `coal / gas / nuclear / hydro / solar / wind / other` (Gas + Gas-CC → gas; Biomass + Other → other).
