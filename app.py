import math
import requests
import streamlit as st
import folium
import polyline

MAPBOX_TOKEN = st.secrets["mapbox"]["token"]

st.title("Minimal Dig Site Directions")

# --- Geometry helpers ---
def mercator_xy(lon, lat):
    R = 6378137.0
    return math.radians(lon) * R, math.log(math.tan(math.pi/4 + math.radians(lat)/2)) * R

def segment_projection(a_lon, a_lat, b_lon, b_lat, p_lon, p_lat):
    ax, ay = mercator_xy(a_lon, a_lat)
    bx, by = mercator_xy(b_lon, b_lat)
    px, py = mercator_xy(p_lon, p_lat)
    vx, vy = (bx - ax, by - ay)
    seg_len2 = vx*vx + vy*vy
    if seg_len2 == 0:
        return 0.0, ax, ay, ax, ay, bx, by
    t = ((px - ax)*vx + (py - ay)*vy) / seg_len2
    t = max(0.0, min(1.0, t))
    projx, projy = ax + t*vx, ay + t*vy
    return t, projx, projy, ax, ay, bx, by

def nearest_segment_with_projection(route_latlon, dig_lat, dig_lon):
    best, best_d2 = None, float("inf")
    px, py = mercator_xy(dig_lon, dig_lat)
    for i in range(len(route_latlon) - 1):
        (alat, alon) = route_latlon[i]
        (blat, blon) = route_latlon[i+1]
        t, projx, projy, ax, ay, bx, by = segment_projection(alon, alat, blon, blat, dig_lon, dig_lat)
        dx, dy = px - projx, py - projy
        d2 = dx*dx + dy*dy
        if d2 < best_d2:
            best_d2 = d2
            best = ((alon, alat), (blon, blat), (projx, projy))
    return best

def side_from_local_tangent(a_ll, b_ll, proj_xy, dig_lon, dig_lat):
    ax, ay = mercator_xy(a_ll[0], a_ll[1])
    bx, by = mercator_xy(b_ll[0], b_ll[1])
    projx, projy = proj_xy
    tx, ty = (bx - ax, by - ay)
    px, py = mercator_xy(dig_lon, dig_lat)
    wx, wy = (px - projx, py - projy)
    cross = tx*wy - ty*wx
    return "left" if cross > 0 else "right"

def side_relative_to_route(route_latlon, dig_lat, dig_lon):
    nearest = nearest_segment_with_projection(route_latlon, dig_lat, dig_lon)
    if not nearest:
        return "right"
    a_ll, b_ll, proj_xy = nearest
    return side_from_local_tangent(a_ll, b_ll, proj_xy, dig_lon, dig_lat)

# --- Input form ---
with st.form("dig_form", clear_on_submit=False):
    lat = st.number_input("Latitude", value=39.432544, format="%.6f")
    lon = st.number_input("Longitude", value=-94.275491, format="%.6f")
    submitted = st.form_submit_button("Get directions")

if submitted:
    try:
        # Directions from nearest town center (simplified: just reverse geocode place)
        town_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json?types=place&access_token={MAPBOX_TOKEN}"
        town_resp = requests.get(town_url).json()
        town_feat = town_resp["features"][0]
        town_name = town_feat["text"]
        town_center = town_feat["center"]

        dir_url = (
            f"https://api.mapbox.com/directions/v5/mapbox/driving/"
            f"{town_center[0]},{town_center[1]};{lon},{lat}"
            f"?steps=true&geometries=polyline&overview=full&language=en&access_token={MAPBOX_TOKEN}"
        )
        dir_resp = requests.get(dir_url).json()
        route = dir_resp["routes"][0]
        steps = route["legs"][0]["steps"]
        route_coords = polyline.decode(route["geometry"])

        narrative = [f"From {town_name}, travel as follows:"]
        for i, step in enumerate(steps):
            if i == len(steps) - 1:
                side = side_relative_to_route(route_coords, lat, lon)
                narrative.append(f"- The dig site will be located on your {side}.")
            else:
                dist_mi = step["distance"] / 1609.34
                instr = step["maneuver"]["instruction"]
                road = step.get("name", "")
                if road:
                    narrative.append(f"- {instr} on {road} for {dist_mi:.2f} miles")
                else:
                    narrative.append(f"- {instr} for {dist_mi:.2f} miles")

        # Map
        m = folium.Map(location=[lat, lon], zoom_start=14)
        folium.Marker([lat, lon], tooltip="Dig Site", icon=folium.Icon(color="red")).add_to(m)
        folium.Marker([town_center[1], town_center[0]], tooltip="Town Start").add_to(m)
        folium.PolyLine(route_coords, color="blue", weight=3).add_to(m)

        st.subheader("Turn‑by‑Turn Directions")
        st.write("\n".join(narrative))
        st.components.v1.html(m._repr_html_(), height=520)

    except Exception as e:
        st.error(f"Error: {e}")
