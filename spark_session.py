"""Local Spark + Sedona session. Sized for a 2-core / 8 GB Codespace."""
from sedona.spark import SedonaContext

SEDONA_PACKAGES = ",".join([
    "org.apache.sedona:sedona-spark-shaded-3.5_2.12:1.7.1",
    "org.datasyslab:geotools-wrapper:1.7.1-28.5",
])

def get_spark(app_name: str = "wildfire-evac"):
    builder = (
        SedonaContext.builder()
        .appName(app_name)
        .master("local[*]")
        .config("spark.jars.packages", SEDONA_PACKAGES)
        .config("spark.driver.memory", "4g")
        .config("spark.sql.shuffle.partitions", "8")  # small data -> few partitions
    )
    return SedonaContext.create(builder.getOrCreate())
