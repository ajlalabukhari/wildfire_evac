"""GOLD: spatial joins in Sedona + aggregations in Spark SQL -> one tract-level table."""
from pathlib import Path

from wildfire.config import ROOT, load_config
from wildfire.spark_session import get_spark


def register(spark, silver: Path, name: str, geo: bool = True) -> bool:
    path = silver / f"{name}.parquet"
    if not path.exists():
        return False
    fmt = "geoparquet" if geo else "parquet"
    spark.read.format(fmt).load(str(path)).createOrReplaceTempView(name)
    return True


def main() -> None:
    cfg = load_config()
    silver, gold = ROOT / cfg["paths"]["silver"], ROOT / cfg["paths"]["gold"]
    gold.mkdir(parents=True, exist_ok=True)
    spark = get_spark()
    register(spark, silver, "tracts")
    register(spark, silver, "roads")
    register(spark, silver, "acs", geo=False)
    has_fhsz = register(spark, silver, "fhsz")
    has_fires = register(spark, silver, "fire_perimeters")

    # Road length per tract, and "exit" crossings: road segments that cross the tract edge.
    spark.sql("""
        SELECT t.GEOID,
               SUM(ST_Length(ST_Intersection(r.geometry, t.geometry))) / 1000 AS road_km,
               SUM(CASE WHEN ST_Intersects(r.geometry, ST_Boundary(t.geometry))
                         AND r.MTFCC IN ('S1100','S1200','S1400') THEN 1 ELSE 0 END) AS exit_crossings
        FROM tracts t JOIN roads r ON ST_Intersects(t.geometry, r.geometry)
        GROUP BY t.GEOID
    """).createOrReplaceTempView("road_metrics")

    if has_fhsz:
        spark.sql("""
            SELECT t.GEOID,
                   SUM(ST_Area(ST_Intersection(t.geometry, z.geometry))) / MAX(ST_Area(t.geometry)) * 100
                       AS pct_high_hazard
            FROM tracts t JOIN fhsz z ON ST_Intersects(t.geometry, z.geometry)
            WHERE z.is_high
            GROUP BY t.GEOID
        """).createOrReplaceTempView("hazard_metrics")
    else:
        spark.sql("SELECT GEOID, CAST(NULL AS DOUBLE) AS pct_high_hazard FROM tracts") \
             .createOrReplaceTempView("hazard_metrics")

    if has_fires:
        spark.sql("""
            SELECT t.GEOID, 1 AS burned, MAX(f.fire_year) AS last_fire_year
            FROM tracts t JOIN fire_perimeters f ON ST_Intersects(t.geometry, f.geometry)
            GROUP BY t.GEOID
        """).createOrReplaceTempView("fire_metrics")
    else:
        spark.sql("SELECT GEOID, 0 AS burned, CAST(NULL AS INT) AS last_fire_year FROM tracts") \
             .createOrReplaceTempView("fire_metrics")

    result = spark.sql("""
        SELECT t.GEOID, a.population, a.pct_65_plus, a.pct_no_vehicle, a.median_income,
               COALESCE(r.road_km, 0) AS road_km,
               COALESCE(r.road_km, 0) / (ST_Area(t.geometry) / 1e6) AS road_km_per_sqkm,
               COALESCE(r.exit_crossings, 0) AS exit_crossings,
               COALESCE(h.pct_high_hazard, 0) AS pct_high_hazard,
               COALESCE(f.burned, 0) AS burned, f.last_fire_year
        FROM tracts t
        LEFT JOIN acs a ON t.GEOID = a.GEOID
        LEFT JOIN road_metrics r ON t.GEOID = r.GEOID
        LEFT JOIN hazard_metrics h ON t.GEOID = h.GEOID
        LEFT JOIN fire_metrics f ON t.GEOID = f.GEOID
    """)
    result.toPandas().to_parquet(gold / "tract_metrics.parquet", index=False)
    print(f"gold done: {result.count()} tracts")
    spark.stop()


if __name__ == "__main__":
    main()
