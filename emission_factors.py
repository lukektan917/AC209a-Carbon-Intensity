"""CO2 emission factors for EIA-930 fuel categories, in kg CO2 per MWh of electricity.

Why this file exists
--------------------
EIA's CO2 coefficients are per unit of *fuel energy burned* (kg CO2 / MMBtu),
not per unit of *electricity generated*. EIA-930 reports electricity (MW).
To combine them we multiply by the average heat rate, i.e. how much fuel
energy a plant burns per kWh of electricity it produces (Btu / kWh):

    kg CO2 / MWh  =  (kg CO2 / MMBtu) * (Btu / kWh) / 1000

    Units check: (kg / 1e6 Btu) * (Btu / kWh) = kg / 1e6 kWh = kg / 1000 MWh

Example (2025): natural gas 52.91 kg/MMBtu * 7,781 Btu/kWh / 1000 ≈ 412 kg/MWh.

Heat rates change a little each year, so factors are computed per year.

Sources (retrieved 2026-11-11)
------------------------------
- CO2 coefficients: EIA, "Carbon Dioxide Emissions Coefficients",
  https://www.eia.gov/environment/emissions/co2_vol_mass.php
- Heat rates: EIA, Electric Power Annual, Table 8.1 "Average Operating Heat
  Rate for Selected Energy Sources", https://www.eia.gov/electricity/annual/html/epa_08_01.html

Assumptions to state in the writeup
-----------------------------------
- Coal uses EIA's "Coal (All types)" coefficient. PJM burns mostly bituminous
  (93.24 kg/MMBtu); using it instead lowers coal's factor by ~3%.
- "All Petroleum Products" uses distillate fuel oil. Most of PJM's oil-fired
  capacity is distillate-burning peakers.
- Nuclear, hydro (incl. pumped storage), solar and wind are 0 (no combustion).
- Battery/other storage (reported separately from Jul 2024) is 0. Storage
  discharges energy that was generated earlier, so this slightly understates
  the intensity of hours when batteries discharge. Charging (negative values)
  is excluded from generation.
- "Geothermal" (new in Jul 2024; ~none in PJM) is folded into "Other".
- "Other Fuel Sources" in PJM is mostly biomass, landfill gas, waste and
  batteries. Default is 0 (biogenic CO2 treated as carbon-neutral); change it
  with --other-factor to test sensitivity.
- "Unknown Fuel Sources" is empty for PJM in the files checked; if it shows up,
  it is treated like natural gas (the usual marginal fossil fuel).
- These are direct (stack) emissions only, not lifecycle emissions.
"""

import pandas as pd

# kg CO2 per MMBtu of fuel (EIA coefficients page)
CO2_KG_PER_MMBTU = {
    "coal": 95.99,  # Coal (All types)
    "gas": 52.91,   # Natural Gas
    "oil": 74.14,   # Distillate Fuel Oil
}

# Btu of fuel per kWh of electricity (EIA Electric Power Annual Table 8.1)
HEAT_RATE_BTU_PER_KWH = {
    #       coal   petroleum  natural gas
    2015: (10495, 10687, 7869),
    2016: (10493, 10811, 7863),
    2017: (10465, 10834, 7803),
    2018: (10481, 11095, 7811),
    2019: (10551, 11205, 7725),
    2020: (10655, 11259, 7725),
    2021: (10583, 11224, 7689),
    2022: (10689, 11166, 7740),
    2023: (10745, 11465, 7721),
    2024: (10777, 11200, 7754),
    2025: (10647, 10969, 7781),
}

FUELS = ["coal", "gas", "nuclear", "oil", "hydro", "solar", "wind", "storage", "other", "unknown"]


def factors_for_year(year: int, other_factor: float = 0.0) -> dict:
    """Return {fuel: kg CO2 per MWh} for one year.

    Years after the last published heat-rate year reuse the latest year.
    """
    known = sorted(HEAT_RATE_BTU_PER_KWH)
    hr_year = min(max(year, known[0]), known[-1])
    hr_coal, hr_oil, hr_gas = HEAT_RATE_BTU_PER_KWH[hr_year]
    f = {fuel: 0.0 for fuel in FUELS}
    f["coal"] = CO2_KG_PER_MMBTU["coal"] * hr_coal / 1000
    f["gas"] = CO2_KG_PER_MMBTU["gas"] * hr_gas / 1000
    f["oil"] = CO2_KG_PER_MMBTU["oil"] * hr_oil / 1000
    f["other"] = other_factor
    f["unknown"] = f["gas"]
    return f


def factor_table(years, other_factor: float = 0.0) -> pd.DataFrame:
    """One row per year, one column per fuel, values in kg CO2 / MWh."""
    rows = []
    for y in years:
        known = sorted(HEAT_RATE_BTU_PER_KWH)
        row = {"year": y, "heat_rate_year": min(max(y, known[0]), known[-1])}
        row.update(factors_for_year(y, other_factor))
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(factor_table(range(2019, 2027)).round(1).to_string(index=False))
