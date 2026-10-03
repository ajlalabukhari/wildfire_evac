"""BRONZE: download raw data exactly as published. Safe to rerun (skips existing files)."""
import io
import os
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from wildfire.config import ROOT, load_config

AGE_65_PLUS = [f"B01001_{i:03d}E" for i in list(range(20, 26)) + list(range(44, 50))]
ACS_VARS = [
    "B01003_001E",  # total population
    "B08201_001E",  # total households
    "B08201_002E",  # households with no vehicle
    "B19013_001E",  # median household income
] + AGE_65_PLUS


def fetch_zip(url: str, dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        print(f"skip (exists): {dest}")
        return
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(dest)


def fetch_acs(cfg: dict, dest: Path) -> None:
    if dest.exists():
        print(f"skip (exists): {dest}")
        return
    counties = ",".join(cfg["county_fips"])
    params = {
        "get": ",".join(["NAME"] + ACS_VARS),
        "for": "tract:*",
        "in": f"state:{cfg['state_fips']} county:{counties}",
    }
    if key := os.getenv("CENSUS_API_KEY"):
        params["key"] = key
    url = f"https://api.census.gov/data/{cfg['acs_year']}/acs/acs5"
    print(f"downloading ACS for counties {counties}")
    r = requests.get(url, params=params, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Census API error {r.status_code}: {r.text[:300]}")
    rows = r.json()
    dest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows[1:], columns=rows[0]).to_csv(dest, index=False)
    print(f"ACS: {len(rows) - 1} tracts")


def main() -> None:
    load_dotenv()
    cfg = load_config()
    bronze = ROOT / cfg["paths"]["bronze"]
    st, yr = cfg["state_fips"], cfg["tiger_year"]
    base = f"https://www2.census.gov/geo/tiger/TIGER{yr}"

    # Roads are published one file per county -> one subfolder per county
    for co in cfg["county_fips"]:
        fetch_zip(f"{base}/ROADS/tl_{yr}_{st}{co}_roads.zip", bronze / "tiger_roads" / co)

    # Tracts are published one file per state
    fetch_zip(f"{base}/TRACT/tl_{yr}_{st}_tract.zip", bronze / "tiger_tracts")

    fetch_acs(cfg, bronze / "acs" / "acs_tracts.csv")
    print("bronze done. Reminder: CAL FIRE files go in data/bronze/manual/ (see config).")


if __name__ == "__main__":
    main()