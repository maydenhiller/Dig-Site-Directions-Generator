import streamlit as st
import requests
import polyline
import folium
from streamlit_folium import st_folium

MAPBOX_TOKEN = st.secrets["mapbox"]["token"]

st.title("Dig Site Directions Generator")

lat = st.number_input("Latitude", value=35.4676, format="%.6f")
lon = st.number_input("Longitude", value=-97.5164, format="%.6f")

# Initialize session state
if "narrative" not in st.session_state:
    st.session_state.narrative = None
if "map_obj" not in st.session_state:
    st.session_state.map_obj = None

if st.button("Get Directions"):
    # --- Reverse geocode ---
    geocode_url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{lon},{lat}.json?types=address,poi&access_token={MAPBOX_TOKEN}"
    )
    geo_resp = requests.get(geocode_url).json()
    if "features" not in geo_resp or not geo_resp["features"]:
        st.error("No address found.")
        st.stop()

    start_coords = geo_resp["features"][0]["center"]
    start_name = geo_resp["features"][0]["place_name"]
    intersection_like = start_name.split(",")[0]

    # --- Directions ---
    directions_url = (
        f"https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{start_coords[0]},{start_coords[1]};{lon},{lat}"
        f"?steps=true&geometries=polyline&access_token={MAPBOX_TOKEN}"
    )
    dir_resp = requests.get(directions_url).json()
    steps = dir_resp["routes"][0]["legs"][0]["steps"]

    # Narrative
    narrative = [f"From {intersection_like}, travel as follows:"]
    for step in steps:
        dist_mi = step["distance"] / 1609.34
        instr = step["maneuver"]["instruction"]
        narrative.append(f"- {instr} for {dist_mi:.2f} miles")

    # Map
    coords = polyline.decode(dir_resp["routes"][0]["geometry"])
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.Marker([lat, lon], tooltip="Dig Site", icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([start_coords[1], start_coords[0]], tooltip="Start Point").add_to(m)
    folium.PolyLine(coords, color="blue", weight=3).add_to(m)

    # Save to session state
    st.session_state.narrative = narrative
    st.session_state.map_obj = m

# --- Display results if available ---
if st.session_state.narrative:
    st.subheader("Turn‑by‑Turn Directions")
    st.write("\n".join(st.session_state.narrative))

if st.session_state.map_obj:
    st_folium(st.session_state.map_obj, width=700, height=500)
