"""Build one clean hourly table for PJM: demand, generation mix, interchange,
carbon intensity, and weather.

    python build_dataset.py                      # 2019 through the latest data
    python build_dataset.py --start 2022 --end 2024
    python build_dataset.py --no-weather

Output
------
data/pjm_hourly.csv            one row per hour (see README.md for columns)
data/emission_factors_used.csv kg CO2/MWh per fuel per year

Downloads are cached in data/interim/, so re-running is fast. The raw EIA files
are large (~40 MB balance + ~100 MB interchange per half-year), so they are
deleted after the PJM rows are extracted unless you pass --keep-raw.

Data sources
------------
EIA-930 six-month files: https://www.eia.gov/electricity/gridmonitor/about
NOAA GHCNh (Global Historical Climatology Network hourly, successor to ISD):
  https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from emission_factors import FUELS, factor_table

EIA_BASE = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
NOAA_BASE = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/"
BA = "PJM"
LOCAL_TZ = "America/New_York"

# Airports in PJM's large load centers (GHCN station ids)
WEATHER_STATIONS = {
    "USW00013739": "Philadelphia",
    "USW00094846": "Chicago O'Hare",
    "USW00093738": "Washington Dulles",
    "USW00093721": "Baltimore",
    "USW00094823": "Pittsburgh",
    "USW00014821": "Columbus",
}

# Our fuel name -> EIA-930 "Net Generation (MW) from ..." categories that make it up.
# EIA split several categories starting with the Jul-Dec 2024 files; older files
# use the combined name. Whichever columns exist are summed.
EIA_FUELS = {
    "coal": ["Coal"],
    "gas": ["Natural Gas"],
    "nuclear": ["Nuclear"],
    "oil": ["All Petroleum Products"],
    "hydro": ["Hydropower and Pumped Storage",
              "Hydropower Excluding Pumped Storage", "Pumped Storage"],
    "solar": ["Solar",
              "Solar without Integrated Battery Storage", "Solar with Integrated Battery Storage"],
    "wind": ["Wind",
             "Wind without Integrated Battery Storage", "Wind with Integrated Battery Storage"],
    "storage": ["Battery Storage", "Other Energy Storage", "Unknown Energy Storage"],
    "other": ["Other Fuel Sources", "Geothermal"],
    "unknown": ["Unknown Fuel Sources"],
}

DATA = Path(__file__).resolve().parent / "data"
RAW, INTERIM = DATA / "raw", DATA / "interim"


def log(msg):
    print(msg, flush=True)


def download(url, dest):
    """Stream a file to disk (skip if it already exists)."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    return dest


def to_num(s):
    """EIA files sometimes write numbers as "1,234"."""
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")


def parse_utc(s):
    return pd.to_datetime(s, format="%m/%d/%Y %I:%M:%S %p", utc=True)


# --------------------------------------------------------------------------- EIA

def available_halves(start, end):
    """Six-month periods EIA has published, e.g. [(2019, 'Jan_Jun'), ...]."""
    meta = pd.read_csv(EIA_BASE + "EIA930_File_List_Meta.csv")
    meta = meta[meta["DESCRIPTION"] == "BALANCE"]
    halves = sorted({(int(y), m) for y, m in zip(meta["YEAR"], meta["MONTHS"])},
                    key=lambda t: (t[0], t[1] != "Jan_Jun"))
    return [(y, m) for y, m in halves if start <= y <= end]


def interchange_half(year, months, keep_raw):
    """PJM's hourly flow to/from each neighbor. Positive = PJM exports."""
    out = INTERIM / f"interchange_{year}_{months}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    name = f"EIA930_INTERCHANGE_{year}_{months}.csv"
    raw = download(EIA_BASE + name, RAW / name)
    parts = []
    for chunk in pd.read_csv(raw, dtype=str, chunksize=500_000):
        parts.append(chunk[chunk["Balancing Authority"] == BA])
    d = pd.concat(parts)
    d = pd.DataFrame({
        "datetime_utc": parse_utc(d["UTC Time at End of Hour"]),
        "neighbor": d["Directly Interconnected Balancing Authority"],
        "mw": to_num(d["Interchange (MW)"]),
    })
    d = d.pivot_table(index="datetime_utc", columns="neighbor", values="mw", aggfunc="last")
    d.columns = [f"ic_{c}_mw" for c in d.columns]
    d = d.reset_index()
    INTERIM.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out, index=False)
    if not keep_raw:
        raw.unlink()
    return d


def balance_half(year, months, bas, keep_raw):
    """Demand, forecast, net generation, interchange and fuel mix for the given BAs."""
    out = INTERIM / f"balance_{year}_{months}.parquet"
    if out.exists():  # delete data/interim/ to force a rebuild
        return pd.read_parquet(out)
    name = f"EIA930_BALANCE_{year}_{months}.csv"
    raw = download(EIA_BASE + name, RAW / name)
    d = pd.read_csv(raw, dtype=str)
    d = d[d["Balancing Authority"].isin(bas)]

    def col(base):
        """Prefer EIA's cleaned '(Adjusted)' value, fall back to the reported one."""
        adj = f"{base} (Adjusted)"
        v = to_num(d[base])
        return to_num(d[adj]).fillna(v) if adj in d else v

    res = pd.DataFrame({
        "ba": d["Balancing Authority"].values,
        "datetime_utc": parse_utc(d["UTC Time at End of Hour"]).values,
        "demand_mw": col("Demand (MW)").values,
        "demand_forecast_mw": to_num(d["Demand Forecast (MW)"]).values,
        "net_gen_mw": col("Net Generation (MW)").values,
        "total_interchange_mw": col("Total Interchange (MW)").values,
        "eia_imputed": d.filter(like="(Imputed)").notna().any(axis=1).values,
    })
    for fuel, eia_names in EIA_FUELS.items():
        cols = [col(c) for c in (f"Net Generation (MW) from {n}" for n in eia_names) if c in d]
        res[f"gen_{fuel}_mw"] = (pd.concat(cols, axis=1).sum(axis=1, min_count=1).values
                                 if cols else np.nan)
    INTERIM.mkdir(parents=True, exist_ok=True)
    res.to_parquet(out, index=False)
    if not keep_raw:
        raw.unlink()
    return res


def carbon_intensity(df, year_col, other_factor):
    """Production-based carbon intensity (kg CO2/MWh) and CO2 (metric tons/hour).

    Negative fuel values (pumped-storage pumping, battery charging, station
    load) are set to 0: they are consumption, not generation.
    """
    gen = df[[f"gen_{f}_mw" for f in FUELS]].clip(lower=0).fillna(0)
    table = factor_table(sorted(df[year_col].unique()), other_factor).set_index("year")
    ef = table.loc[df[year_col].values].set_index(df.index)
    co2_kg = sum(gen[f"gen_{f}_mw"] * ef[f] for f in FUELS)  # MW * kg/MWh over 1 h = kg
    total = gen.sum(axis=1)
    # If the fuel breakdown covers < 80% of reported net generation, fuels are
    # missing from the report (e.g. PJM, 1-2 Oct 2022: 300 MW of 75 GW), and the
    # ratio would be meaningless. Leave intensity blank for those hours.
    complete = (total > 0) & ~(total < 0.8 * df["net_gen_mw"])
    ci = (co2_kg / total).where(complete)
    return ci, (co2_kg / 1000).where(complete), total


# ------------------------------------------------------------------------- NOAA

# GHCNh quality codes: blank / 0,1,4,5,9 = passed (legacy ISD codes); others = suspect or failed
GOOD_QC = {"", "0", "1", "4", "5", "9"}
VALID_RANGE = {"temperature": (-45, 50), "dew_point_temperature": (-50, 35), "wind_speed": (0, 60)}


def ghcnh_value(d, var):
    v = pd.to_numeric(d[var], errors="coerce")
    ok = d[f"{var}_Quality_Code"].fillna("").isin(GOOD_QC)
    lo, hi = VALID_RANGE[var]
    return v.where(ok & v.between(lo, hi))


def weather_station_year(station, year):
    out = INTERIM / f"weather_{station}_{year}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    try:
        raw = download(f"{NOAA_BASE}{year}/psv/GHCNh_{station}_{year}.psv",
                       RAW / f"ghcnh_{station}_{year}.psv")
    except requests.HTTPError:
        log(f"  no NOAA file for {station} {year}")
        return pd.DataFrame()
    cols = ["DATE"] + [f"{v}{s}" for v in VALID_RANGE for s in ("", "_Quality_Code")]
    d = pd.read_csv(raw, sep="|", dtype=str, usecols=cols)
    t = pd.to_datetime(d["DATE"], utc=True)  # GHCNh times are UTC
    res = pd.DataFrame({
        # An observation at 00:54 describes the hour ending 01:00, so round to nearest hour
        "datetime_utc": t.dt.round("h"),
        "temp_c": ghcnh_value(d, "temperature"),
        "dewpoint_c": ghcnh_value(d, "dew_point_temperature"),
        "wind_ms": ghcnh_value(d, "wind_speed"),
    }).groupby("datetime_utc").mean().reset_index()
    res["station"] = station
    INTERIM.mkdir(parents=True, exist_ok=True)
    res.to_parquet(out, index=False)
    raw.unlink()
    return res


def weather(years):
    frames = []
    for y in years:
        for st, name in WEATHER_STATIONS.items():
            log(f"  weather {y} {name}")
            frames.append(weather_station_year(st, y))
    w = pd.concat([f for f in frames if len(f)])
    agg = w.groupby("datetime_utc").agg(
        temp_c=("temp_c", "mean"),
        dewpoint_c=("dewpoint_c", "mean"),
        wind_ms=("wind_ms", "mean"),
        n_weather_stations=("temp_c", "count"),
    )
    return agg.reset_index()


# ------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2019, help="first year (fuel mix starts Jul 2018)")
    ap.add_argument("--end", type=int, default=2100, help="last year (default: latest available)")
    ap.add_argument("--other-factor", type=float, default=0.0,
                    help="kg CO2/MWh for 'Other' fuels (default 0; try ~400 for sensitivity)")
    ap.add_argument("--no-weather", action="store_true")
    ap.add_argument("--keep-raw", action="store_true", help="keep raw EIA/NOAA CSVs in data/raw")
    ap.add_argument("--out", default=str(DATA / "pjm_hourly.csv"))
    args = ap.parse_args()

    halves = available_halves(args.start, args.end)
    if not halves:
        sys.exit("No EIA-930 files in that year range.")
    log(f"EIA-930 periods: {halves[0]} .. {halves[-1]} ({len(halves)} files of each type)")

    # 1. Interchange: who PJM trades with, hour by hour
    ic = []
    for y, m in halves:
        log(f"interchange {y} {m}")
        ic.append(interchange_half(y, m, args.keep_raw))
    ic = pd.concat(ic).drop_duplicates("datetime_utc", keep="last")
    neighbors = sorted(c[3:-3] for c in ic.columns if c.startswith("ic_"))
    log(f"PJM neighbors: {neighbors}")

    # 2. Balance data for PJM and its neighbors (neighbors are needed for the
    #    consumption-based intensity)
    bal = []
    for y, m in halves:
        log(f"balance {y} {m}")
        bal.append(balance_half(y, m, [BA] + neighbors, args.keep_raw))
    bal = pd.concat(bal)
    bal["datetime_utc"] = pd.to_datetime(bal["datetime_utc"], utc=True)
    bal = bal.drop_duplicates(["ba", "datetime_utc"], keep="last")
    bal["year"] = bal["datetime_utc"].dt.tz_convert(LOCAL_TZ).dt.year
    bal["ci_kg_per_mwh"], bal["co2_t"], bal["fuel_sum_mw"] = carbon_intensity(bal, "year", args.other_factor)

    # 3. PJM table on a complete hourly index (missing hours become NaN rows)
    pjm = bal[bal["ba"] == BA].set_index("datetime_utc").sort_index()
    full = pd.date_range(pjm.index.min(), pjm.index.max(), freq="h", tz="UTC", name="datetime_utc")
    pjm = pjm.reindex(full)
    pjm["qa_missing_hour"] = pjm["demand_mw"].isna() & pjm["fuel_sum_mw"].isna()
    pjm["eia_imputed"] = pjm["eia_imputed"].fillna(False).astype(bool)
    pjm = pjm.drop(columns=["ba", "year"]).rename(columns={"ci_kg_per_mwh": "ci_prod_kg_per_mwh"})

    # Neighbor intensities, one column each
    nb = bal[bal["ba"].isin(neighbors)].pivot_table(
        index="datetime_utc", columns="ba", values="ci_kg_per_mwh", aggfunc="last")
    nb.columns = [f"ci_{c}_kg_per_mwh" for c in nb.columns]
    pjm = pjm.join(nb).join(ic.set_index("datetime_utc"))

    # 4. Consumption-based intensity (first-order import adjustment):
    #    power PJM keeps = own generation - exports, at PJM's intensity;
    #    plus imports from each neighbor, at that neighbor's intensity.
    #    Neighbor intensity missing -> use PJM's (flagged).
    flows = pjm[[f"ic_{n}_mw" for n in neighbors]].fillna(0)
    exports = flows.clip(lower=0).sum(axis=1)
    kept = (pjm["fuel_sum_mw"] - exports).clip(lower=0)
    num, imp_total = pjm["ci_prod_kg_per_mwh"] * kept, 0
    pjm["qa_neighbor_ci_filled"] = False
    for n in neighbors:
        imp = (-flows[f"ic_{n}_mw"]).clip(lower=0)
        ci_n = pjm.get(f"ci_{n}_kg_per_mwh", pd.Series(np.nan, index=pjm.index))
        pjm["qa_neighbor_ci_filled"] |= (imp > 0) & ci_n.isna()
        num = num + imp * ci_n.fillna(pjm["ci_prod_kg_per_mwh"])
        imp_total = imp_total + imp
    pjm["imports_mw"], pjm["exports_mw"] = imp_total, exports
    pjm["ci_cons_kg_per_mwh"] = (num / (kept + imp_total)).where(kept + imp_total > 0)

    # 5. Quality flags
    # Fuel-by-fuel generation routinely differs from reported total net generation
    # by ~±3% in a daily pattern (PJM reports them from different sources), so
    # only flag gaps over 5%.
    pjm["qa_fuel_sum_mismatch"] = (pjm["fuel_sum_mw"] - pjm["net_gen_mw"]).abs() > 0.05 * pjm["net_gen_mw"]
    # EIA's identity: demand = net generation - total interchange
    pjm["qa_balance_mismatch"] = (
        (pjm["demand_mw"] - (pjm["net_gen_mw"] - pjm["total_interchange_mw"])).abs() > 0.02 * pjm["demand_mw"])
    # PJM's reported total interchange vs. the sum of its per-neighbor flows.
    # EIA's own data disagrees here a lot (its "Sum(Valid DIBAs)" column shows the
    # same gap), so this is informational and NOT part of qa_any.
    pjm["info_interchange_mismatch"] = (
        (flows.sum(axis=1) - pjm["total_interchange_mw"]).abs() > 0.02 * pjm["demand_mw"])
    qa = [c for c in pjm.columns if c.startswith("qa_")]
    pjm["qa_any"] = pjm[qa].any(axis=1)
    qa.append("info_interchange_mismatch")

    # 6. Weather (observed; lag it before using as a day-ahead feature)
    years = sorted({y for y, _ in halves})
    if not args.no_weather:
        log("weather")
        pjm = pjm.join(weather(years).set_index("datetime_utc"))

    # 7. Time columns. EIA timestamps are the END of the hour; hour_local is the
    #    local hour the interval STARTS in (0 = midnight-1am).
    local_end = pjm.index.tz_convert(LOCAL_TZ)
    local_start = (pjm.index - pd.Timedelta(hours=1)).tz_convert(LOCAL_TZ)
    pjm.insert(0, "datetime_local", local_end)
    pjm.insert(1, "date_local", local_start.date)
    pjm.insert(2, "hour_local", local_start.hour)
    pjm.insert(3, "dow", local_start.dayofweek)
    pjm.insert(4, "month", local_start.month)

    order = (["datetime_local", "date_local", "hour_local", "dow", "month",
              "demand_mw", "demand_forecast_mw", "net_gen_mw", "total_interchange_mw", "fuel_sum_mw"]
             + [f"gen_{f}_mw" for f in FUELS]
             + ["co2_t", "ci_prod_kg_per_mwh", "ci_cons_kg_per_mwh", "imports_mw", "exports_mw"]
             + [f"ic_{n}_mw" for n in neighbors]
             + [c for c in pjm.columns if c.startswith("ci_") and c not in ("ci_prod_kg_per_mwh", "ci_cons_kg_per_mwh")]
             + [c for c in ["temp_c", "dewpoint_c", "wind_ms", "n_weather_stations"] if c in pjm]
             + ["eia_imputed"] + qa + ["qa_any"])
    pjm = pjm[order]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pjm.to_csv(out, index_label="datetime_utc")
    factor_table(years, args.other_factor).to_csv(DATA / "emission_factors_used.csv", index=False)

    log(f"\nWrote {out} ({len(pjm):,} hours, {pjm.index.min()} .. {pjm.index.max()})")
    log(f"Hours with any quality flag: {pjm['qa_any'].mean():.1%}")
    for c in qa:
        log(f"  {c}: {pjm[c].sum():,}")


if __name__ == "__main__":
    main()
