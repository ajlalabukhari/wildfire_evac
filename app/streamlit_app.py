"""Dashboard. Run: streamlit run app/streamlit_app.py"""
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
import folium
import geopandas as gpd
from streamlit_folium import st_folium

from wildfire.config import ROOT, load_config

load_dotenv()
cfg = load_config()
COUNTY_NAMES = {"007": "Butte", "013": "Contra Costa"}



@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / cfg["paths"]["gold"] / "tract_metrics.parquet")
    df["county"] = df["GEOID"].str[2:5].map(COUNTY_NAMES)
    return df


df = load_data()

@st.cache_resource
def load_layers():
    silver = ROOT / cfg["paths"]["silver"]
    tracts = gpd.read_parquet(silver / "tracts.parquet")
    fires = gpd.read_parquet(silver / "fire_perimeters.parquet")
    fhsz = gpd.read_parquet(silver / "fhsz.parquet")
    fhsz = fhsz[fhsz["is_high"]]
    roads = gpd.read_parquet(silver / "roads.parquet")
    roads = roads[roads["MTFCC"].isin(["S1100", "S1200"])]  # highways + main roads
    out = []
    for g in (tracts, fires, fhsz, roads):
        g = g.copy()
        g["geometry"] = g.geometry.simplify(50)  # smooth to ~50 m so the map loads fast
        out.append(g.to_crs(4326))               # web maps need lat/lon
    return out

st.title("Wildfire Evacuation Route Vulnerability")
county = st.sidebar.selectbox("County", ["All"] + sorted(df["county"].dropna().unique()))
view = df if county == "All" else df[df["county"] == county]

tab1, tab_map, tab2 = st.tabs(["Explore", "Map", "Ask the data"])

with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("Tracts", len(view))
    c2.metric("Burned since 2015", int(view["burned"].sum()))
    c3.metric("Avg % high hazard", f"{view['pct_high_hazard'].mean():.1f}%")

    fig, ax = plt.subplots()
    ax.scatter(view["exit_crossings"], view["pct_high_hazard"],
               s=view["pct_65_plus"].fillna(0) * 3, c=view["burned"], cmap="coolwarm", alpha=0.6)
    ax.set_xlabel("Major-road exits from tract")
    ax.set_ylabel("% of tract in High/Very High hazard")
    ax.set_title("Few exits + high hazard = most vulnerable\n(dot size = % age 65+, red = burned)")
    st.pyplot(fig)

    st.dataframe(view.sort_values("pct_high_hazard", ascending=False), use_container_width=True)
   
with tab_map:
       tracts, fires, fhsz, roads = load_layers()
       labels = {
           "pct_high_hazard": "% in High/Very High hazard",
           "pct_65_plus": "% aged 65+",
           "pct_no_vehicle": "% households without a car",
           "exit_crossings": "Road exits",
       }
       metric = st.selectbox("Color tracts by", list(labels), format_func=labels.get)

       tv = tracts[["GEOID", "geometry"]].merge(view, on="GEOID")
       minx, miny, maxx, maxy = tv.total_bounds
       m = folium.Map(
       tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
       attr="Esri, HERE, Garmin, OpenStreetMap contributors",
       name="Light gray basemap",
)
       m.fit_bounds([[miny, minx], [maxy, maxx]])

       folium.Choropleth(
           geo_data=tv[["GEOID", "geometry"]].to_json(), data=tv, columns=["GEOID", metric],
           key_on="feature.properties.GEOID", fill_color="YlOrRd", fill_opacity=0.6,
           line_opacity=0.3, legend_name=labels[metric], name="Tracts",
       ).add_to(m)

       tip_cols = ["GEOID", "population", "pct_high_hazard", "exit_crossings",
                   "pct_65_plus", "pct_no_vehicle", "last_fire_year"]
       folium.GeoJson(
           tv[tip_cols + ["geometry"]].round(1),
           style_function=lambda f: {"fillOpacity": 0, "weight": 0},
           tooltip=folium.GeoJsonTooltip(fields=tip_cols),
           name="Tract details",
       ).add_to(m)

       folium.GeoJson(
           fires, name="Fires since 2015",
           style_function=lambda f: {"color": "#d62728", "weight": 1.5, "fillOpacity": 0.15},
           tooltip=folium.GeoJsonTooltip(fields=["fire_year"]),
       ).add_to(m)

       folium.GeoJson(
           fhsz, name="High/Very High hazard zones", show=False,
           style_function=lambda f: {"color": "#ff7f0e", "weight": 0, "fillOpacity": 0.3},
       ).add_to(m)

       folium.GeoJson(
           roads, name="Major roads",
           style_function=lambda f: {"color": "#333333", "weight": 1.5},
       ).add_to(m)

       folium.LayerControl(collapsed=True, position="bottomright").add_to(m)
       st_folium(m, height=600, use_container_width=True, returned_objects=[])

with tab2:
    q = st.text_input("Ask a question about these tracts")
    if q:
        client = Anthropic()  # reads ANTHROPIC_API_KEY from .env
        with st.spinner("Thinking..."):
            resp = client.messages.create(
                model=cfg["llm"]["model"],
                max_tokens=1000,
                system=(
                    "You analyze wildfire evacuation risk by census tract. Answer only from the CSV below. "
                    "Cite tract GEOIDs. If the data can't answer, say so.\n\n"
                    + view.round(2).to_csv(index=False)
                ),
                messages=[{"role": "user", "content": q}],
            )
        st.write(resp.content[0].text)