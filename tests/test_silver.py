import pandas as pd
from wildfire.pipeline.bronze import AGE_65_PLUS
from wildfire.pipeline.silver import clean_acs


def test_clean_acs_percentages():
    row = {"NAME": "x", "state": "6", "county": "7", "tract": "100",
           "B01003_001E": "1000", "B08201_001E": "400", "B08201_002E": "40",
           "B19013_001E": "-666666666"}
    row.update({c: "10" for c in AGE_65_PLUS})
    out = clean_acs(pd.DataFrame([row], dtype=str))
    assert out.loc[0, "GEOID"] == "06007000100"
    assert out.loc[0, "pct_no_vehicle"] == 10.0
    assert out.loc[0, "pct_65_plus"] == 12.0
    assert pd.isna(out.loc[0, "median_income"])
