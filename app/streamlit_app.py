"""Dashboard. Run: streamlit run app/streamlit_app.py"""
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

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

st.title("Wildfire Evacuation Route Vulnerability")
county = st.sidebar.selectbox("County", ["All"] + sorted(df["county"].dropna().unique()))
view = df if county == "All" else df[df["county"] == county]

tab1, tab2 = st.tabs(["Explore", "Ask the data"])

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