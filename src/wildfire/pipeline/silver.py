"""SILVER: clean, clip to counties, reproject to one CRS, validate, write GeoParquet."""
import geopandas as gpd
import pandas as pd
import pandera.pandas as pa
import shapely

from wildfire.config import ROOT, load_config
from wildfire.pipeline.bronze import AGE_65_PLUS

ACS_SCHEMA = pa.DataFrameSchema({
    "GEOID": pa.Column(str, pa.Check.str_length(11, 11), unique=True),
    "population": pa.Column(float, pa.Check.ge(0)),
    "pct_65_plus": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
    "pct_no_vehicle": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
})


def clean_acs(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    num_cols = [c for c in df.columns if c.startswith("B")]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    df[num_cols] = df[num_cols].where(df[num_cols] >= 0)  # Census uses negatives as "no data"
    df["GEOID"] = df["state"].str.zfill(2) + df["county"].str.zfill(3) + df["tract"].str.zfill(6)
    df["population"] = df["B01003_001E"].astype(float)
    pop = df["population"].where(df["population"] > 0)
    hh = df["B08201_001E"].where(df["B08201_001E"] > 0)
    df["pct_65_plus"] = 100 * df[AGE_65_PLUS].sum(axis=1) / pop
    df["pct_no_vehicle"] = 100 * df["B08201_002E"] / hh
    df["median_income"] = df["B19013_001E"]
    out = df[["GEOID", "population", "pct_65_plus", "pct_no_vehicle", "median_income"]]
    return ACS_SCHEMA.validate(out)


def clean_geoms(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop 3D/measure values and repair broken shapes so spatial joins don't fail."""
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf.geometry = shapely.make_valid(shapely.force_2d(gdf.geometry.values))
    return gdf


def main() -> None:
    cfg = load_config()
    bronze, silver = ROOT / cfg["paths"]["bronze"], ROOT / cfg["paths"]["silver"]
    silver.mkdir(parents=True, exist_ok=True)
    crs = cfg["crs"]

    # Tracts: keep only the counties in config
    tracts = gpd.read_file(next((bronze / "tiger_tracts").glob("*.shp")))
    tracts = tracts[tracts["COUNTYFP"].isin(cfg["county_fips"])].to_crs(crs)
    tracts[["GEOID", "COUNTYFP", "ALAND", "geometry"]].to_parquet(silver / "tracts.parquet")
    counties = tracts.dissolve()

    # Roads: one file per county -> combine
    road_files = sorted((bronze / "tiger_roads").rglob("*.shp"))
    roads = gpd.GeoDataFrame(pd.concat([gpd.read_file(p) for p in road_files], ignore_index=True))
    roads = clean_geoms(roads.to_crs(crs))
    roads[["LINEARID", "FULLNAME", "MTFCC", "geometry"]].to_parquet(silver / "roads.parquet")

    # Demographics
    acs = clean_acs(pd.read_csv(bronze / "acs" / "acs_tracts.csv", dtype=str))
    acs.to_parquet(silver / "acs.parquet")

    cf = cfg["calfire"]

    # Fire hazard zones: combine all files listed in config
    frames = [
        gpd.read_file(ROOT / f["path"], layer=f["layer"]).to_crs(crs)
        for f in cf["fhsz_files"] if (ROOT / f["path"]).exists()
    ]
    if frames:
        fhsz = clean_geoms(gpd.GeoDataFrame(pd.concat(frames, ignore_index=True)))
        fhsz = gpd.clip(fhsz, counties)
        fhsz = fhsz.rename(columns={cf["fhsz_class_col"]: "hazard_class"})
        fhsz["is_high"] = fhsz["hazard_class"].isin(cf["high_hazard_values"])
        fhsz[["hazard_class", "is_high", "geometry"]].to_parquet(silver / "fhsz.parquet")
        print(f"hazard zones: {len(fhsz)} polygons")
    else:
        print("no hazard zone files found - skipping")

    # Wildfire perimeters
    per_path = ROOT / cf["perimeters_file"]
    if per_path.exists():
        per = gpd.read_file(per_path, layer=cf["perimeters_layer"]).to_crs(crs)
        per = clean_geoms(per)
        per["fire_year"] = pd.to_numeric(per[cf["perimeters_year_col"]], errors="coerce")
        per = per[per["fire_year"] >= cf["perimeters_min_year"]]
        per = gpd.clip(per, counties)
        per[["fire_year", "geometry"]].to_parquet(silver / "fire_perimeters.parquet")
        print(f"fire perimeters: {len(per)} fires since {cf['perimeters_min_year']}")
    else:
        print(f"missing {per_path} - skipping fire perimeters")

    print("silver done.")


if __name__ == "__main__":
    main()