import streamlit as st
import requests
import polyline
import folium
from streamlit_folium import st_folium
import math

MAPBOX_TOKEN = st.secrets["mapbox"]["token"]

st.title("Dig Site Directions Generator")

lat = st.number_input("Latitude", value=35.4676, format="%.6f")
lon = st.number_input("Longitude", value=-97.5164, format="%.6f")

def bearing_to_cardinal(bearing):
    dirs = ["North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"]
    ix = round(bearing / 45) % 8
    return dirs[ix]

if st.button("Get Directions"):
    # --- Reverse geocode ---
    geocode_url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{lon},{lat}.json?types=address&access_token={MAPBOX_TOKEN}"
    )
    geo_resp = requests.get(geocode_url).json()
    if "features" not in geo_resp or not geo_resp["features"]:
        st.error("No address found.")
        st.stop()

    feature = geo_resp["features"][0]
    start_coords = feature["center"]
    # Extract street name(s)
    street = feature.get("text", "Unknown Street")
    # Extract town and state
    context = {c["id"].split(".")[0]: c["text"] for c in feature.get("context", [])}
    town = context.get("place", "Unknown Town")
    state = context.get("region", "")

    # --- Directions ---
    directions_url = (
        f"https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{start_coords[0]},{start_coords[1]};{lon},{lat}"
        f"?steps=true&geometries=polyline&access_token={MAPBOX_TOKEN}"
    )
    dir_resp = requests.get(directions_url).json()
    if "routes" not in dir_resp or not dir_resp["routes"]:
        st.error("No route found.")
        st.stop()

    steps = dir_resp["routes"][0]["legs"][0]["steps"]

    # --- Build narrative ---
    narrative = []
    # First line
    narrative.append(f"From the intersection of {street} in {town}, {state}, travel as follows:")

    for i, step in enumerate(steps):
        dist_mi = step["distance"] / 1609.34
        instr = step["maneuver"]["instruction"]

        # Convert bearing to cardinal
        bearing = step["maneuver"].get("bearing_after", 0)
        cardinal = bearing_to_cardinal(bearing)

        if i == len(steps) - 1:
            # Final step override
            # Simplified left/right: use bearing to decide
            side = "right" if 90 < bearing < 270 else "left"
            narrative.append(f"- The dig site will be located on your {side}.")
        else:
            narrative.append(f"- Drive {cardinal} for {dist_mi:.2f} miles, then {instr}")

    st.subheader("Turn‑by‑Turn Directions")
    st.write("\n".join(narrative))

    # --- Map visualization ---
    coords = polyline.decode(dir_resp["routes"][0]["geometry"])
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.Marker([lat, lon], tooltip="Dig Site", icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([start_coords[1], start_coords[0]], tooltip="Start Intersection").add_to(m)
    folium.PolyLine(coords, color="blue", weight=3).add_to(m)
    st_folium(m, width=700, height=500)
