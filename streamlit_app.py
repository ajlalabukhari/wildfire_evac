"""Starter dashboard. Run: streamlit run app/streamlit_app.py"""
import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

from wildfire.config import ROOT, load_config

load_dotenv()
cfg = load_config()
df = pd.read_parquet(ROOT / cfg["paths"]["gold"] / "tract_metrics.parquet")

st.title("Wildfire Evacuation Route Vulnerability")
tab1, tab2 = st.tabs(["Explore", "Ask the data"])

with tab1:
    st.dataframe(df.sort_values("pct_high_hazard", ascending=False), use_container_width=True)
    fig, ax = plt.subplots()
    ax.scatter(df["exit_crossings"], df["pct_high_hazard"], s=df["pct_65_plus"].fillna(0) * 3, alpha=0.6)
    ax.set_xlabel("Major-road exits from tract")
    ax.set_ylabel("% of tract in High/Very High hazard")
    ax.set_title("Few exits + high hazard = most vulnerable (dot size = % age 65+)")
    st.pyplot(fig)

with tab2:
    q = st.text_input("Ask a question about the tracts")
    if q:
        # v1: send the table as context. Next step: tool calling with guarded SQL.
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        context = df.round(2).to_csv(index=False)
        resp = client.chat.completions.create(
            model=cfg["llm"]["model"],
            messages=[
                {"role": "system", "content": "Answer only from the CSV provided. Cite tract GEOIDs. "
                 "If the data can't answer, say so.\n\n" + context},
                {"role": "user", "content": q},
            ],
        )
        st.write(resp.choices[0].message.content)
