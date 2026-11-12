# AC209a: Predicting Low-Carbon Hours for Data-Center Computing

Canvas project group 100: Allen Garcia, Amy Chen, Clara Cheng, Luke Tan, Sunny Li.

Each person's work lives in their own folder.

| Folder | Contents |
|---|---|
| [`amy/`](amy/) | EIA-930 balance + interchange data for all 69 balancing authorities, cleaned and summed into EIA's 13 regions (PJM = `MIDA`, ERCOT = `TEX`), saved as `data/regions_hourly_clean.csv.gz`, and the Milestone 2 EDA notebook `Amy_milestone2_EDA.ipynb` (full timeline, then 2023 onward). See [`amy/README.md`](amy/README.md). |
| [`luke/`](luke/) | Data pipeline (EIA-930 + NOAA → hourly PJM table with carbon intensity), the Milestone 2 notebook `ms2_data.ipynb`, the EDA notebook `eda.ipynb` and figures. See [`luke/README.md`](luke/README.md). |
| [`sunny/`](sunny/) | Independent EDA of PJM from EIA's single per-BA workbook (`pjm_carbon_eda.ipynb`): units check against EIA's own CO₂ columns, interchange handling, data quality, diurnal/seasonal structure, within-day headroom, persistence baselines. Handoff notes in [`sunny/README.md`](sunny/README.md). |
