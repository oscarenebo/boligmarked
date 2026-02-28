import streamlit as st
import pandas as pd
import folium
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as MplPath
from streamlit_folium import st_folium
from folium.plugins import Draw
from pathlib import Path


def point_in_polygon(lon, lat, polygon_coords):
    inside = False
    j = len(polygon_coords) - 1

    for i in range(len(polygon_coords)):
        xi, yi = polygon_coords[i]
        xj, yj = polygon_coords[j]

        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) + 1e-12) + xi
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def filter_points_in_polygon(df_points, polygon_coords):
    polygon_np = np.asarray(polygon_coords, dtype=np.float64)
    if polygon_np.shape[0] < 3:
        return df_points.iloc[0:0].copy()

    min_lon, min_lat = polygon_np.min(axis=0)
    max_lon, max_lat = polygon_np.max(axis=0)

    bbox_mask = (
        (df_points["longitude"] >= min_lon)
        & (df_points["longitude"] <= max_lon)
        & (df_points["latitude"] >= min_lat)
        & (df_points["latitude"] <= max_lat)
    )
    candidates = df_points.loc[bbox_mask]

    if candidates.empty:
        return candidates

    polygon_path = MplPath(polygon_np)
    candidate_points = candidates[["longitude", "latitude"]].to_numpy(dtype=np.float64)
    inside_mask = polygon_path.contains_points(candidate_points)
    return candidates.loc[inside_mask].copy()


def extract_polygon_coords(drawings):
    if not drawings:
        return None

    for drawing in reversed(drawings):
        geometry = drawing.get("geometry", {})
        if geometry.get("type") == "Polygon":
            rings = geometry.get("coordinates", [])
            if not rings:
                continue
            outer_ring = rings[0]
            if len(outer_ring) < 3:
                continue
            return outer_ring

    return None


def plot_sqm_price_evolution(df_in_area, min_sales_per_quarter):
    required_columns = {"soldDate", "sqmPrice"}
    if not required_columns.issubset(df_in_area.columns):
        st.warning("Could not plot trend: CSV must include 'soldDate' and 'sqmPrice' columns.")
        return

    trend_df = df_in_area.copy()
    trend_df["soldDate"] = pd.to_datetime(trend_df["soldDate"], errors="coerce")
    trend_df["sqmPrice"] = pd.to_numeric(trend_df["sqmPrice"], errors="coerce")
    trend_df = trend_df.dropna(subset=["soldDate", "sqmPrice"])

    if trend_df.empty:
        st.warning("No valid sold dates and sqm prices found inside the polygon.")
        return

    max_sqm_price = 50000
    trend_df = trend_df[trend_df["sqmPrice"] <= max_sqm_price]

    if trend_df.empty:
        st.warning("No data left after outlier filtering (sqmPrice <= 50000).")
        return

    quarterly = trend_df.set_index("soldDate")["sqmPrice"].resample("QE").agg(["median", "count"])
    quarterly = quarterly.dropna(subset=["median"])

    kept_quarters = quarterly[quarterly["count"] >= min_sales_per_quarter]
    dropped_quarters = len(quarterly) - len(kept_quarters)

    trend = kept_quarters["median"].dropna()

    if trend.empty:
        st.warning(
            f"No quarters with at least {min_sales_per_quarter} sales inside the polygon. "
            "Try lowering the minimum threshold."
        )
        return

    st.caption(
        f"Applied safeguard: kept {len(kept_quarters)} quarters with at least "
        f"{min_sales_per_quarter} sales, dropped {dropped_quarters} low-volume quarters."
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    trend.plot(ax=ax, linestyle="-", color="darkblue", marker="")
    ax.set_title("Price Evolution for Selected Polygon")
    ax.set_ylabel("Median Price per m² (DKK)")
    ax.grid(True)
    st.pyplot(fig)

# --- 1. DATA LOADING ---
@st.cache_data # This prevents reloading the CSV every time you click the map
def load_data():
    base_path = Path(__file__).resolve().parent
    csv_path = base_path / "data" / "raw" / "merged" / "merged.csv"
    usecols = ["latitude", "longitude", "soldDate", "sqmPrice", "zipcode", "propertyType"]
    df = pd.read_csv(csv_path, usecols=lambda col: col in usecols)
    
    # Ensure coordinates are numeric
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce', downcast='float')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce', downcast='float')
    
    return df.dropna(subset=['latitude', 'longitude'])

# Load the data
try:
    df = load_data()
    df_sample = df.head(3000000) # Keep sample smaller to reduce rerun redraw cost
except FileNotFoundError:
    st.error("CSV file not found! Check your 'data/raw/merged/' folder.")
    df_sample = pd.DataFrame()

# --- 2. MAP SETUP ---
st.title("🇩🇰 Property Data Alignment Check")

min_sales_per_quarter = st.number_input(
    "Minimum sales per quarter for trend",
    min_value=1,
    max_value=200,
    value=10,
    step=1,
    help="Quarters with fewer sales than this are excluded from the chart."
)

m = folium.Map(location=[56.2, 11.5], zoom_start=7, tiles="CartoDB positron")

# # Add the sample points to the map
# for idx, row in df_sample.iterrows():
#     folium.CircleMarker(
#         location=[row['latitude'], row['longitude']],
#         radius=3,
#         color="crimson",
#         fill=True,
#         popup=f"sqmPrice: {row.get('sqmPrice', 'N/A')} DKK"
#     ).add_to(m)

# Add Drawing Tools
Draw(draw_options={'polyline': False, 'circle': False}).add_to(m)

# Render
output = st_folium(
    m,
    width=1200,
    height=600,
    key="property_map",
    returned_objects=["all_drawings", "last_active_drawing"]
)

# --- 3. COORDINATE CHECK ---
if not df_sample.empty:
    drawings = output.get("all_drawings") if output else None
    polygon_coords = extract_polygon_coords(drawings)

    if polygon_coords is None:
        st.info("Draw a polygon on the map to find property sales inside it.")
        st.write(f"Loaded {len(df)} properties from CSV.")
        st.dataframe(df.head(5))
    else:
        filtered_df = filter_points_in_polygon(df, polygon_coords)

        st.success(f"Found {len(filtered_df)} property sales inside the polygon.")
        plot_sqm_price_evolution(filtered_df, min_sales_per_quarter)
        st.dataframe(filtered_df)