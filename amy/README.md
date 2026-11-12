# Amy: EIA-930 balance + interchange EDA, all 13 U.S. regions

| File | What it is |
|---|---|
| `Amy_milestone2_EDA.ipynb` | Milestone 2 notebook: data source and size, every raw column, regions and balancing authorities over time, cleaning, data-quality checks, EDA over the full timeline (2019 – Oct 2026) and the focus period (2023 – Oct 2026), findings, and notes for joining with other ERCOT data |
| `eia930.py` | Download, scan every raw file (all columns as published), harmonize fuels, clean each BA, sum BAs into regions, carbon intensity |
| `style.py` | Presentation plot style (palette, type, line weights) |
| `data/regions_hourly_clean.csv.gz` | **Cleaned table**: one row = region × hour, 892,620 rows × 24 columns. `pd.read_csv` opens it directly |
| `data/region_flows_hourly.csv.gz` | One row = region × neighbouring region × hour (MW, > 0 = export) |
| `data/balancing_authorities.csv` | One row = balancing authority: region, first/last hour reported, hours per year |
| `figures/` | Presentation figures (PNG, 300 dpi) |

PJM = region `MIDA`, ERCOT = region `TEX` (each is the only balancing authority in its region).

## Run it

```bash
cd amy
jupyter notebook Amy_milestone2_EDA.ipynb   # run all (~3 min); first run downloads ~2.3 GB into data/raw/ (gitignored)
```

The notebook also writes an uncompressed `data/regions_hourly_clean.csv` (136 MB) for Excel. It is gitignored because it is over GitHub's 100 MB file limit.

To use the cleaned data without running anything:

```python
import pandas as pd
R = pd.read_csv("amy/data/regions_hourly_clean.csv.gz", parse_dates=["utc_end", "date"])
ercot = R[R.region == "TEX"]
```

Join key: `utc_end` (end of the hour, UTC). Column definitions are in Section 3 of the notebook.
