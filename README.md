# Wildfire Evacuation Route Vulnerability

Which neighborhoods sit in high fire-hazard zones, have few ways out, and have many residents who may struggle to evacuate?

## Stack
- **Pipeline:** Python, GeoPandas (silver), Apache Sedona on Spark + Spark SQL (gold)
- **Storage:** GeoParquet in bronze / silver / gold layers
- **Quality:** Pandera schema checks, pytest
- **App:** Streamlit + Matplotlib + LLM (Groq)

## Data sources
| Data | Source |
|---|---|
| Roads, census tracts | Census TIGER/Line (downloaded automatically) |
| Demographics | Census ACS 5-year API (downloaded automatically) |
| Fire hazard zones, fire perimeters | CAL FIRE FRAP (manual download, see config) |

## Run
```bash
cp .env.example .env        # add GROQ_API_KEY
python -m wildfire.run_pipeline
pytest
streamlit run app/streamlit_app.py
```

## Roadmap
- [ ] Tool-calling LLM with read-only SQL + eval set
- [ ] ML: predict `burned` from hazard, roads, demographics
- [ ] Prefect orchestration
