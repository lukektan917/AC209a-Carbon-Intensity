# AC209a: Predicting Low-Carbon Hours for Data-Center Computing

Canvas project group 100: Allen Garcia, Amy Chen, Clara Cheng, Luke Tan, Sunny Li.

Each person's work lives in their own folder.

| Folder | Contents |
|---|---|
| [`amy/`](amy/) | EIA-930 balance + interchange data for all 69 balancing authorities, cleaned and summed into EIA's 13 regions (PJM = `MIDA`, ERCOT = `TEX`), saved as `data/regions_hourly_clean.csv.gz`, and the Milestone 2 EDA notebook `Amy_milestone2_EDA.ipynb` (full timeline, then 2023 onward). See [`amy/README.md`](amy/README.md). |
| [`luke/`](luke/) | Data pipeline (EIA-930 + NOAA → hourly PJM table with carbon intensity), the Milestone 2 notebook `ms2_data.ipynb`, the EDA notebook `eda.ipynb` and figures. See [`luke/README.md`](luke/README.md). |
| [`sunny/`](sunny/) | Independent EDA of PJM from EIA's single per-BA workbook (`pjm_carbon_eda.ipynb`): units check against EIA's own CO₂ columns, interchange handling, data quality, diurnal/seasonal structure, within-day headroom, persistence baselines. Handoff notes in [`sunny/README.md`](sunny/README.md). |
| [`clara/`](clara/) | ERCOT's own 15-minute generation-by-fuel data (ERCOT Fuel Mix Report, `raw/IntGenbyFuel2024–2026.xlsx`), turned into an hourly Texas table with carbon intensity. EDA notebook `209a.ipynb` (2026 so far): carbon intensity by hour of day and by month, generation by source and hour, the cleanest hour of each day, and how much cleaner a flexible job gets by running at 10 a.m. or the best hour instead of a random time. Cross-checks Amy's EIA-930 `TEX` region. See [`clara/README.md`](clara/README.md). |
