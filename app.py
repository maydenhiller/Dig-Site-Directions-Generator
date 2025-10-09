import streamlit as st
import requests
import polyline
import folium
from streamlit_folium import st_folium

MAPBOX_TOKEN = st.secrets["MAPBOX_TOKEN"]

st.title("Dig Site Navigator")

lat = st.number_input("Latitude", value=35.4676)
lon = st.number_input("Longitude", value=-97.5164)

if st.button("Get Directions"):
    # Reverse geocode to nearest intersection
    geocode_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json?types=address,poi,intersection&access_token={MAPBOX_TOKEN}"
    geo_resp = requests.get(geocode_url).json()
    start_coords = geo_resp["features"][0]["center"]  # [lon, lat]
    start_name = geo_resp["features"][0]["place_name"]

    # Directions request
    directions_url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{start_coords[0]},{start_coords[1]};{lon},{lat}?steps=true&geometries=polyline&access_token={MAPBOX_TOKEN}"
    dir_resp = requests.get(directions_url).json()
    steps = dir_resp["routes"][0]["legs"][0]["steps"]

    # Build narrative
    narrative = []
    narrative.append(f"From {start_name}, travel as follows:")
    for step in steps:
        dist_mi = step['distance'] / 1609.34
        instr = step['maneuver']['instruction']
        narrative.append(f"- {instr} for {dist_mi:.2f} miles")

    st.write("\n".join(narrative))

    # Map visualization
    coords = polyline.decode(dir_resp["routes"][0]["geometry"])
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.Marker([lat, lon], tooltip="Dig Site").add_to(m)
    folium.PolyLine(coords, color="blue", weight=3).add_to(m)
    st_folium(m, width=700, height=500)
