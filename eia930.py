"""EIA-930 helpers for Amy's Milestone 2 EDA (all U.S. balancing authorities, summed to EIA's 13 regions).

Pipeline
  download()            fetch the six-month BALANCE / INTERCHANGE bulk files
  scan_balance()        one pass over every BALANCE file: column profile, BA <-> region table,
                        impossible raw values, and a tidy hourly table per BA (8 harmonized fuels)
  build_regions()       clean each BA, then add BAs up into one row per region x hour, with carbon intensity
  scan_interchange()    one pass over every INTERCHANGE file: column profile and region-to-region flows

Raw columns are read exactly as published (pandas infers the types); nothing is declared up front.
"""
import glob
import os
import re
import urllib.request

import numpy as np
import pandas as pd

BASE_URL = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
FUELS = ["coal", "gas", "nuclear", "oil", "hydro", "solar", "wind", "other"]

REGION_NAME = {"CAL": "California", "CAR": "Carolinas", "CENT": "Central", "FLA": "Florida",
               "MIDA": "Mid-Atlantic", "MIDW": "Midwest", "NE": "New England", "NW": "Northwest",
               "NY": "New York", "SE": "Southeast", "SW": "Southwest", "TEN": "Tennessee", "TEX": "Texas"}
# one clock per region for "local hour". Regions that span two zones use the zone most of their load is in.
REGION_TZ = {"CAL": "America/Los_Angeles", "CAR": "America/New_York", "CENT": "America/Chicago",
             "FLA": "America/New_York", "MIDA": "America/New_York", "MIDW": "America/Chicago",
             "NE": "America/New_York", "NW": "America/Los_Angeles", "NY": "America/New_York",
             "SE": "America/Chicago", "SW": "America/Phoenix", "TEN": "America/Chicago", "TEX": "America/Chicago"}
SEASON = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
          6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall"}


# ----------------------------------------------------------------------------- download
def download(raw_dir, kind="BALANCE", years=range(2019, 2027)):
    """Fetch the six-month bulk files (kind = BALANCE or INTERCHANGE) that are not on disk yet."""
    os.makedirs(raw_dir, exist_ok=True)
    for y in years:
        for half in ("Jan_Jun", "Jul_Dec"):
            name = f"EIA930_{kind}_{y}_{half}.csv"
            path = os.path.join(raw_dir, name)
            if not os.path.exists(path):
                try:
                    urllib.request.urlretrieve(BASE_URL + name, path)
                    print("downloaded", name)
                except Exception as e:  # future half-years are not published yet
                    print("not available:", name, e)
    return sorted(glob.glob(os.path.join(raw_dir, f"EIA930_{kind}_*.csv")))


def _num(s):
    """Numbers as float32. Handles text like "12,345" in case a file ever has it."""
    if s.dtype == object:
        s = pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")
    return s.astype("float32")


def _time(s):
    try:
        return pd.to_datetime(s, format="%m/%d/%Y %I:%M:%S %p")
    except (ValueError, TypeError):
        return pd.to_datetime(s, format="mixed")


def _profile(d, fname):
    """Per-column facts for one file: dtype pandas inferred, rows, non-empty rows, first non-empty value."""
    rows = []
    for c in d.columns:
        nn = d[c].notna()
        rows.append({"column": c, "file": fname, "dtype": str(d[c].dtype), "rows": len(d),
                     "filled": int(nn.sum()), "example": d.loc[nn, c].iloc[0] if nn.any() else None})
    return rows


def summarize_profile(rows):
    p = pd.DataFrame(rows)
    order = list(dict.fromkeys(p.column))           # first-seen order, like the files
    out = p.groupby("column").agg(
        dtype=("dtype", lambda s: ", ".join(sorted(set(s)))),
        files_with_column=("file", "nunique"),
        rows_in_those_files=("rows", "sum"),
        filled=("filled", "sum"),
        example=("example", lambda s: next((v for v in s if v is not None), None)))
    out["% filled (where present)"] = (out.filled / out.rows_in_those_files * 100).round(1)
    return out.loc[order, ["dtype", "files_with_column", "% filled (where present)", "example"]]


# ----------------------------------------------------------------------------- fuels
def _fuel_name(c):
    """'Net Generation (MW) from Solar witho Integrated Battery Storage (Adjusted)' -> 'Solar with Integrated Battery Storage'"""
    n = c.split(" from ", 1)[1].replace("(Adjusted)", "")
    return re.sub(r"\s+", " ", n).replace("witho ", "with ").strip()


DIRECT = {"Coal": "coal", "Natural Gas": "gas", "Nuclear": "nuclear", "All Petroleum Products": "oil"}
OLD_NEW = {"hydro": ("Hydropower and Pumped Storage", ["Hydropower Excluding Pumped Storage", "Pumped Storage"]),
           "solar": ("Solar", ["Solar without Integrated Battery Storage", "Solar with Integrated Battery Storage"]),
           "wind": ("Wind", ["Wind without Integrated Battery Storage", "Wind with Integrated Battery Storage"])}
OTHER = ["Other Fuel Sources", "Unknown Fuel Sources", "Geothermal"]      # until Jul 2024 geothermal was inside "Other"
STORAGE = ["Battery Storage", "Other Energy Storage", "Unknown Energy Storage"]   # charging < 0 is consumption -> 0


def harmonize_fuels(d):
    """Map one file's (Adjusted) fuel columns onto 8 fuels that mean the same thing in every year."""
    cols = {_fuel_name(c): c for c in d.columns if c.startswith("Net Generation (MW) from") and c.endswith("(Adjusted)")}
    get = lambda n: _num(d[cols[n]]) if n in cols else pd.Series(np.nan, index=d.index, dtype="float32")
    total = lambda names: pd.concat([get(n) for n in names], axis=1).sum(axis=1, min_count=1)
    out = {f: get(n) for n, f in DIRECT.items()}
    for f, (old, new) in OLD_NEW.items():
        out[f] = get(old).combine_first(total(new))
    out["other"] = pd.concat([get(n) for n in OTHER] + [get(n).clip(lower=0) for n in STORAGE], axis=1).sum(axis=1, min_count=1)
    return pd.DataFrame(out).astype("float32")


# ----------------------------------------------------------------------------- BALANCE
def scan_balance(files):
    """One pass over every BALANCE file (all BAs). Returns a dict with
       profile   one row per raw column: dtype, files, % filled, example
       ba_year   hours reported per BA x region x year
       ba_info   per BA: region, first and last hour reported
       bad_raw   raw MW values above 1,000,000 (impossible for any U.S. grid)
       tidy      one row per BA x hour: demand, forecast, net generation, interchange, 8 fuels (Adjusted series)
    """
    prof, years, bad, tidy = [], [], [], []
    for f in files:
        name = os.path.basename(f)
        d = pd.read_csv(f, low_memory=False)
        prof += _profile(d, name)
        utc = _time(d["UTC Time at End of Hour"])
        years.append(d.assign(year=utc.dt.year).groupby(["Balancing Authority", "Region", "year"]).size().rename("hours"))
        for c in [c for c in d.columns if "(MW)" in c]:
            m = _num(d[c]).abs() > 1e6
            if m.any():
                bad.append(pd.DataFrame({"ba": d.loc[m, "Balancing Authority"], "column": c,
                                         "utc_end": utc[m], "value": d.loc[m, c]}))
        t = pd.DataFrame({"ba": d["Balancing Authority"], "region": d["Region"], "utc_end": utc,
                          "demand": _num(d["Demand (MW) (Adjusted)"]), "demand_fcst": _num(d["Demand Forecast (MW)"]),
                          "netgen": _num(d["Net Generation (MW) (Adjusted)"]),
                          "interchange": _num(d["Total Interchange (MW) (Adjusted)"])})
        tidy.append(pd.concat([t, harmonize_fuels(d)], axis=1))
    ba_year = pd.concat(years).reset_index()
    tidy = pd.concat(tidy, ignore_index=True)
    ba_info = tidy.groupby("ba").agg(region=("region", "first"), first_hour=("utc_end", "min"), last_hour=("utc_end", "max"))
    return {"profile": summarize_profile(prof), "ba_year": ba_year, "ba_info": ba_info,
            "bad_raw": pd.concat(bad, ignore_index=True) if bad else pd.DataFrame(), "tidy": tidy}


# ----------------------------------------------------------------------------- cleaning (per BA)
def clean(A, k=10):
    """Flag one-hour spikes and impossible values -> NaN -> fill gaps of <= 3 h by time interpolation."""
    A = A.copy()
    cols = FUELS + ["demand", "demand_fcst"]
    flags = pd.DataFrame(False, index=A.index, columns=cols)
    for c in cols:
        x = A[c].astype(float)
        if x.notna().sum() < 48:
            continue
        # a spike: far from the average of its two neighbours, which agree with each other
        spike = x - (x.shift(1) + x.shift(-1)) / 2
        mad = (spike - spike.median()).abs().median()
        flags[c] = (spike.abs() > k * mad + 200) & ((x.shift(1) - x.shift(-1)).abs() < spike.abs() / 2)
        if c in ("coal", "gas", "nuclear", "demand", "demand_fcst"):
            # values far outside this BA's own normal range are errors (e.g. PJM nuclear 46 GW, demand 224 GW)
            hi, lo = x.quantile(.995), x.quantile(.005)
            flags.loc[x > 1.25 * hi + 500, c] = True
            if lo > 2000:
                flags.loc[x < 0.1 * lo, c] = True
        if c in ("demand", "demand_fcst"):
            flags.loc[x < 0, c] = True          # demand can't be negative
    for c in cols:
        A.loc[flags[c], c] = np.nan
    A[cols] = A[cols].astype(float).interpolate(method="time", limit=3, limit_area="inside")
    return A, flags


# ----------------------------------------------------------------------------- emission factors
# EIA CO2 coefficients, kg CO2 per MMBtu of fuel: https://www.eia.gov/environment/emissions/co2_vol_mass.php
CO2_KG_PER_MMBTU = {"coal": 95.99, "gas": 52.91, "oil": 74.14}
# EIA Electric Power Annual Table 8.1, national average heat rate, Btu per kWh:
# https://www.eia.gov/electricity/annual/html/epa_08_01.html
HEAT_RATE_BTU_PER_KWH = {
    2019: {"coal": 10551, "oil": 11205, "gas": 7725},
    2020: {"coal": 10655, "oil": 11259, "gas": 7725},
    2021: {"coal": 10583, "oil": 11224, "gas": 7689},
    2022: {"coal": 10689, "oil": 11166, "gas": 7740},
    2023: {"coal": 10745, "oil": 11465, "gas": 7721},
    2024: {"coal": 10777, "oil": 11200, "gas": 7754},
}


def ef_table(years=range(2019, 2027)):
    """kg CO2/MWh (= g/kWh) by year and fuel: kg/MMBtu x Btu/kWh / 1000. Later years reuse 2024."""
    rows = []
    for y in years:
        hr = HEAT_RATE_BTU_PER_KWH[min(y, max(HEAT_RATE_BTU_PER_KWH))]
        rows.append({"year": y, **{f: CO2_KG_PER_MMBTU[f] * hr[f] / 1000 for f in CO2_KG_PER_MMBTU}})
    return pd.DataFrame(rows).set_index("year")


# ----------------------------------------------------------------------------- regions
def build_regions(tidy, start, end):
    """Clean each BA, add BAs up to one row per region x hour, compute carbon intensity.

    Returns (R, cleaned): R = region-hour table; cleaned = values replaced per BA and column.
    """
    cols = ["demand", "demand_fcst", "netgen", "interchange", *FUELS]
    parts, counts = [], {}
    for ba, g in tidy.groupby("ba"):
        A = g.drop_duplicates("utc_end", keep="last").set_index("utc_end").sort_index()
        A, flags = clean(A)
        counts[ba] = flags.sum()
        parts.append(A.reset_index())
    T = pd.concat(parts, ignore_index=True)
    grp = T.groupby(["region", "utc_end"])
    R = grp[cols].sum(min_count=1)
    R["n_ba"] = grp["ba"].nunique()
    R = R.reset_index()

    # local calendar: hour *beginning*, on each region's own clock
    start_local = R.utc_end - pd.Timedelta(hours=1)
    local = pd.Series(pd.NaT, index=R.index, dtype="datetime64[ns]")
    for reg, tz in REGION_TZ.items():
        m = R.region == reg
        local[m] = start_local[m].dt.tz_localize("UTC").dt.tz_convert(tz).dt.tz_localize(None)
    R["date"], R["hour"] = local.dt.normalize(), local.dt.hour
    R = R[(R.date >= start) & (R.date <= end)].copy()
    R["year"], R["month"], R["dow"] = R.date.dt.year, R.date.dt.month, R.date.dt.dayofweek
    R["season"] = R.month.map(SEASON)

    # carbon intensity, production-based: emissions of the region's own generation / that generation
    ef = ef_table()
    gen = R[FUELS].clip(lower=0)
    emis = sum(gen[f].fillna(0) * R.year.map(ef[f]).values for f in ef.columns)
    total = gen.fillna(0).sum(axis=1)
    R["co2_t"] = emis / 1000                          # MW x kg/MWh over one hour = kg -> tonnes
    R["ci"] = emis / total
    # the fuel breakdown must cover >= 85% of reported net generation, otherwise part of the mix is missing
    R["mix_ratio"] = gen.sum(axis=1, min_count=1) / R.netgen
    # an hour where "other" suddenly carries most of the mix is a misreport (e.g. NYISO put all 12.6 GW under
    # "other" at 2026-05-04 18:00 UTC, which would make carbon intensity 0)
    other_share = gen.other / total
    usual = other_share.groupby(R.region).transform("median")
    bad = (total <= 0) | (R.mix_ratio < .85) | ((other_share > .5) & (other_share > 5 * usual))
    R.loc[bad, ["co2_t", "ci"]] = np.nan
    order = ["region", "utc_end", "date", "hour", "year", "month", "dow", "season", "n_ba",
             "demand", "demand_fcst", "netgen", "interchange", *FUELS, "co2_t", "ci", "mix_ratio"]
    R = R[order].sort_values(["region", "utc_end"]).reset_index(drop=True)
    for c in R.select_dtypes("float64"):
        R[c] = R[c].astype("float32")
    return R, pd.DataFrame(counts).T


# ----------------------------------------------------------------------------- INTERCHANGE
def scan_interchange(files):
    """One pass over every INTERCHANGE file. Returns (profile, flows).

    flows: one row per region x neighbouring region x hour, MW summed over the BA pairs between them.
    > 0 = the first region exports to the second. Flows inside a region are dropped. Neighbouring
    regions include Canada (CAN) and Mexico (MEX).
    """
    prof, flows = [], []
    for f in files:
        d = pd.read_csv(f, low_memory=False)
        prof += _profile(d, os.path.basename(f))
        d = d[d["Region"] != d["DIBA_Region"]]
        g = pd.DataFrame({"region": d["Region"], "to_region": d["DIBA_Region"],
                          "utc_end": _time(d["UTC Time at End of Hour"]), "mw": _num(d["Interchange (MW)"])})
        flows.append(g.groupby(["region", "to_region", "utc_end"]).mw.sum(min_count=1).reset_index())
    flows = pd.concat(flows, ignore_index=True).drop_duplicates(["region", "to_region", "utc_end"], keep="last")
    return summarize_profile(prof), flows
