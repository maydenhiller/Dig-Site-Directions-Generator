import streamlit as st
import requests, polyline, folium

MAPBOX_TOKEN = st.secrets["mapbox"]["token"]

st.title("Dig Site Directions Generator")

lat = st.number_input("Latitude", value=35.4676, format="%.6f")
lon = st.number_input("Longitude", value=-97.5164, format="%.6f")

if "narrative" not in st.session_state:
    st.session_state.narrative = None
if "map_html" not in st.session_state:
    st.session_state.map_html = None

def bearing_to_cardinal(bearing):
    dirs = ["North","Northeast","East","Southeast","South","Southwest","West","Northwest"]
    return dirs[round(bearing/45) % 8]

if st.button("Get Directions"):
    # --- Step 1: nearest town ---
    town_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json?types=place&access_token={MAPBOX_TOKEN}"
    town_resp = requests.get(town_url).json()
    town_feature = town_resp["features"][0]
    town_name = town_feature["text"]
    state = next(c["text"] for c in town_feature["context"] if c["id"].startswith("region"))
    town_center = town_feature["center"]

    # --- Step 2: find intersection near town center ---
    tile_url = f"https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/{town_center[0]},{town_center[1]}.json?layers=road&radius=500&limit=5&access_token={MAPBOX_TOKEN}"
    tile_resp = requests.get(tile_url).json()
    roads = [f["properties"]["name"] for f in tile_resp["features"] if "name" in f["properties"]]
    roads = list(dict.fromkeys(roads))  # unique
    if len(roads) >= 2:
        intersection_label = f"{roads[0]} & {roads[1]}"
    else:
        intersection_label = roads[0] if roads else "Unknown Intersection"

    # Use town center as intersection coords
    start_coords = town_center

    # --- Step 3: directions ---
    dir_url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{start_coords[0]},{start_coords[1]};{lon},{lat}?steps=true&geometries=polyline&access_token={MAPBOX_TOKEN}"
    dir_resp = requests.get(dir_url).json()
    steps = dir_resp["routes"][0]["legs"][0]["steps"]

    narrative = [f"From the intersection of {intersection_label} in {town_name}, {state}, travel as follows:"]
    for i, step in enumerate(steps):
        dist_mi = step["distance"]/1609.34
        bearing = step["maneuver"].get("bearing_after",0)
        cardinal = bearing_to_cardinal(bearing)
        if i == len(steps)-1:
            side = "right" if 90 < bearing < 270 else "left"
            narrative.append(f"- The dig site will be located on your {side}.")
        else:
            narrative.append(f"- Drive {cardinal} for {dist_mi:.2f} miles")

    # --- Map ---
    coords = polyline.decode(dir_resp["routes"][0]["geometry"])
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.Marker([lat, lon], tooltip="Dig Site", icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([start_coords[1], start_coords[0]], tooltip="Start Intersection").add_to(m)
    folium.PolyLine(coords, color="blue", weight=3).add_to(m)

    st.session_state.narrative = narrative
    st.session_state.map_html = m._repr_html_()

# --- Display ---
if st.session_state.narrative:
    st.subheader("Turn‑by‑Turn Directions")
    st.write("\n".join(st.session_state.narrative))

if st.session_state.map_html:
    st.components.v1.html(st.session_state.map_html, height=500)
