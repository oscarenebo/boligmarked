from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st


st.set_page_config(page_title="Median sqm heatmap", layout="wide")

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "raw" / "merged" / "merged.csv"
CACHE_PATH = ROOT / "data" / "processed" / "sqm_heatmap_monthly_grid.pkl"

GRID_SIZE_DEGREES = 0.01
MAX_SQM_PRICE = 120000


@st.cache_data(show_spinner=False)
def load_or_build_heatmap_data() -> pd.DataFrame:
    if CACHE_PATH.exists():
        cached = pd.read_pickle(CACHE_PATH)
        required_cols = {"period", "lat_bin", "lon_bin", "median_sqm", "sales"}
        if required_cols.issubset(cached.columns):
            cached["period"] = pd.to_datetime(cached["period"], errors="coerce")
            return cached.dropna(subset=["period", "lat_bin", "lon_bin", "median_sqm", "sales"])

    usecols = ["latitude", "longitude", "soldDate", "sqmPrice"]
    df = pd.read_csv(CSV_PATH, usecols=lambda col: col in usecols)

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce", downcast="float")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce", downcast="float")
    df["sqmPrice"] = pd.to_numeric(df["sqmPrice"], errors="coerce", downcast="float")
    df["soldDate"] = pd.to_datetime(df["soldDate"], errors="coerce")

    df = df.dropna(subset=["latitude", "longitude", "sqmPrice", "soldDate"])
    df = df[(df["sqmPrice"] > 0) & (df["sqmPrice"] <= MAX_SQM_PRICE)]

    df["period"] = df["soldDate"].dt.to_period("M").dt.to_timestamp()
    df["lat_bin"] = np.floor(df["latitude"] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES + (GRID_SIZE_DEGREES / 2)
    df["lon_bin"] = np.floor(df["longitude"] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES + (GRID_SIZE_DEGREES / 2)

    grouped = (
        df.groupby(["period", "lat_bin", "lon_bin"], as_index=False)
        .agg(median_sqm=("sqmPrice", "median"), sales=("sqmPrice", "size"))
    )

    grouped.to_pickle(CACHE_PATH)
    return grouped


def add_color_scale(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        frame["color"] = [[] for _ in range(len(frame))]
        return frame

    q_low, q_high = frame["median_sqm"].quantile([0.05, 0.95])
    spread = max(float(q_high - q_low), 1.0)

    normalized = ((frame["median_sqm"] - q_low) / spread).clip(0, 1).to_numpy()
    red = (255 * normalized).astype(np.int16)
    blue = (255 * (1.0 - normalized)).astype(np.int16)
    green = (80 + 120 * (1.0 - np.abs(normalized - 0.5) * 2.0)).astype(np.int16)
    alpha = np.full_like(red, 180)

    colors = np.stack([red, green, blue, alpha], axis=1)
    colored = frame.copy()
    colored["color"] = colors.tolist()
    return colored


st.title("🔥 Median sqm price heatmap")
st.caption("Monthly median DKK/m² across Denmark using pre-aggregated spatial bins for fast interaction.")

if not CSV_PATH.exists():
    st.error("Data file not found. Expected: data/raw/merged/merged.csv")
    st.stop()

with st.spinner("Preparing aggregated heatmap data (first run can take some time)..."):
    heatmap_df = load_or_build_heatmap_data()

if heatmap_df.empty:
    st.error("No data available after cleaning and aggregation.")
    st.stop()

months = sorted(pd.to_datetime(heatmap_df["period"].unique()))

col_filters, col_stats = st.columns([2, 1])
with col_filters:
    selected_month = st.select_slider(
        "Month",
        options=months,
        value=months[-1],
        format_func=lambda value: pd.Timestamp(value).strftime("%Y-%m"),
    )
    min_sales = st.slider("Minimum sales per grid cell", min_value=1, max_value=30, value=4, step=1)

selected_month = pd.Timestamp(selected_month)
filtered = heatmap_df[(heatmap_df["period"] == selected_month) & (heatmap_df["sales"] >= min_sales)].copy()
filtered = add_color_scale(filtered)

with col_stats:
    st.metric("Selected month", selected_month.strftime("%Y-%m"))
    st.metric("Grid cells shown", f"{len(filtered):,}")
    st.metric("Median of medians", f"{filtered['median_sqm'].median():,.0f} DKK/m²" if not filtered.empty else "N/A")

if filtered.empty:
    st.warning("No cells match this month + minimum-sales setting. Try lowering the threshold.")
    st.stop()

view_state = pdk.ViewState(
    latitude=float(filtered["lat_bin"].mean()),
    longitude=float(filtered["lon_bin"].mean()),
    zoom=7,
    pitch=0,
)

layer = pdk.Layer(
    "ScatterplotLayer",
    data=filtered,
    get_position="[lon_bin, lat_bin]",
    get_fill_color="color",
    get_radius=650,
    opacity=0.65,
    pickable=True,
)

tooltip = {
    "html": "<b>Median:</b> {median_sqm} DKK/m²<br/><b>Sales:</b> {sales}",
    "style": {"color": "white"},
}

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="light",
    )
)

st.caption(
    "Performance approach: monthly + spatial pre-aggregation cached to disk at data/processed/sqm_heatmap_monthly_grid.pkl"
)