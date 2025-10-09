import math
import re
import requests
import streamlit as st
import folium
import polyline

# =========================
# Config
# =========================
MAPBOX_TOKEN = st.secrets["mapbox"]["token"]

st.title("Dig Site Directions Generator")

# Persisted outputs
if "narrative" not in st.session_state:
    st.session_state.narrative = None
if "map_html" not in st.session_state:
    st.session_state.map_html = None

# =========================
# Geometry helpers (Web Mercator)
# =========================
def mercator_xy(lon, lat):
    R = 6378137.0
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi/4 + math.radians(lat)/2)) * R
    return x, y

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
    best = None
    best_d2 = float("inf")
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
    tx, ty = (bx - ax, by - ay)            # tangent along segment
    px, py = mercator_xy(dig_lon, dig_lat)
    wx, wy = (px - projx, py - projy)      # offset from road to dig point
    cross = tx*wy - ty*wx
    return "left" if cross > 0 else "right"

def side_relative_to_route(route_latlon, dig_lat, dig_lon):
    nearest = nearest_segment_with_projection(route_latlon, dig_lat, dig_lon)
    if not nearest:
        return "right"
    a_ll, b_ll, proj_xy = nearest
    return side_from_local_tangent(a_ll, b_ll, proj_xy, dig_lon, dig_lat)

# =========================
# Helpers: town, intersection, and phrasing
# =========================
def bearing_to_cardinal(bearing):
    dirs = ["North","Northeast","East","Southeast","South","Southwest","West","Northwest"]
    return dirs[round((bearing % 360)/45) % 8]

def extract_town_state(feature):
    town, state = "", ""
    for c in feature.get("context", []):
        cid = c.get("id", "")
        if cid.startswith("place."): town = c.get("text", "")
        if cid.startswith("region."): state = c.get("text", "")
    if not town:
        town = feature.get("text", "")
    return town, state

# Normalize a street name to its base (strip N/S/E/W and common suffixes)
def normalize_street_base(name):
    if not name:
        return ""
    s = name.strip()
    # Remove directional prefix (N, S, E, W) at start
    s = re.sub(r"^(N|S|E|W)\s+", "", s, flags=re.IGNORECASE)
    # Remove common suffix tokens at end
    s = re.sub(r"\b(Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Terrace|Ter\.?|Court|Ct\.?)\b\.?", "", s, flags=re.IGNORECASE).strip()
    # Collapse multiple spaces
    s = re.sub(r"\s{2,}", " ", s)
    return s

def pick_distinct_intersection_label(lon, lat):
    """
    Tilequery around the start location, choose two distinct street names that actually cross:
    - Prefer Washington + Jefferson when available (distinct bases).
    - Otherwise pick two different base names (never Washington + Washington).
    """
    tile_url = (
        f"https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/"
        f"{lon},{lat}.json?layers=road&radius=300&limit=50&access_token={MAPBOX_TOKEN}"
    )
    r = requests.get(tile_url).json()
    # Collect name and class; dedupe exact names while preserving order
    seen = set()
    roads = []
    for f in r.get("features", []):
        props = f.get("properties", {})
        name = props.get("name")
        cls = props.get("class", "")
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        roads.append((name, cls, normalize_street_base(name)))

    if not roads:
        return "Unknown Intersection"

    # Prefer pairing Washington with Jefferson (distinct bases)
    base_names = [b for _, _, b in roads]
    has_wash = any("Washington" in b for b in base_names)
    has_jeff = any("Jefferson" in b for b in base_names)
    if has_wash and has_jeff:
        # Pick first encountered variant of each (keeps directional prefixes like E/N as-is)
        w_name = next(n for n, _, b in roads if "Washington" in b)
        j_name = next(n for n, _, b in roads if "Jefferson" in b)
        return f"{w_name} & {j_name}"

    # Otherwise, pick two distinct bases, preferring higher-class roads
    def class_rank(c):
        order = ["motorway","trunk","primary","secondary","tertiary","street","service","track"]
        return order.index(c) if c in order else len(order)

    # Sort by class then original order, then choose two with different bases
    roads_sorted = sorted(roads, key=lambda x: (class_rank(x[1])))
    chosen = []
    used_bases = set()
    for n, c, b in roads_sorted:
        if b and b not in used_bases:
            chosen.append(n)
            used_bases.add(b)
        if len(chosen) == 2:
            break

    if len(chosen) == 2:
        return f"{chosen[0]} & {chosen[1]}"
    elif len(chosen) == 1:
        return chosen[0]
    return "Unknown Intersection"

def format_step_with_cardinal(step, dist_mi):
    man = step.get("maneuver", {})
    instr = man.get("instruction", "").rstrip(".")  # remove trailing period to avoid duplication
    cardinal = bearing_to_cardinal(man.get("bearing_after", 0))
    return f"- {instr} and continue traveling {cardinal} for {dist_mi:.2f} miles"

# =========================
# Input form (prevents intermediate reruns)
# =========================
with st.form("dig_form", clear_on_submit=False):
    lat = st.number_input("Latitude", value=39.432544, format="%.6f")
    lon = st.number_input("Longitude", value=-94.275491, format="%.6f")
    submitted = st.form_submit_button("Get directions")

# =========================
# Compute once on submit
# =========================
if submitted:
    try:
        # 1) Nearest town (name and center)
        town_url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
            f"{lon},{lat}.json?types=place&language=en&access_token={MAPBOX_TOKEN}"
        )
        town_resp = requests.get(town_url).json()
        if not town_resp.get("features"):
            st.error("No nearby town found.")
            st.stop()
        town_feat = town_resp["features"][0]
        town_name, town_state = extract_town_state(town_feat)
        town_center = town_feat["center"]  # [lon, lat]

        # 2) Seed directions to get the route’s first maneuver location
        dir_seed_url = (
            f"https://api.mapbox.com/directions/v5/mapbox/driving/"
            f"{town_center[0]},{town_center[1]};{lon},{lat}"
            f"?steps=true&geometries=polyline&overview=full&language=en&access_token={MAPBOX_TOKEN}"
        )
        dir_seed = requests.get(dir_seed_url).json()
        if not dir_seed.get("routes"):
            st.error("No route found from town.")
            st.stop()

        seed_route = dir_seed["routes"][0]
        seed_steps = seed_route["legs"][0]["steps"]
        first_step = seed_steps[0]
        start_location = first_step["maneuver"]["location"]  # [lon, lat]

        # 3) Label intersection near the true start location with distinct streets
        intersection_label = pick_distinct_intersection_label(start_location[0], start_location[1])

        # 4) Final directions from the aligned start location to the dig site
        dir_url = (
            f"https://api.mapbox.com/directions/v5/mapbox/driving/"
            f"{start_location[0]},{start_location[1]};{lon},{lat}"
            f"?steps=true&geometries=polyline&overview=full&language=en&access_token={MAPBOX_TOKEN}"
        )
        dir_resp = requests.get(dir_url).json()
        if not dir_resp.get("routes"):
            st.error("No route found.")
            st.stop()

        route = dir_resp["routes"][0]
        steps = route["legs"][0]["steps"]
        route_coords = polyline.decode(route["geometry"])  # list of (lat, lon)

        # 5) Narrative: intersection phrasing + per-step instruction with cardinal + final left/right
        narrative = [f"From the intersection of {intersection_label} in {town_name}, {town_state}, travel as follows:"]
        for i, step in enumerate(steps):
            if i == len(steps) - 1:
                side = side_relative_to_route(route_coords, lat, lon)
                narrative.append(f"- The dig site will be located on your {side}.")
            else:
                dist_mi = step["distance"] / 1609.34
                narrative.append(format_step_with_cardinal(step, dist_mi))

        # 6) Map
        m = folium.Map(location=[lat, lon], zoom_start=14)
        folium.Marker([lat, lon], tooltip="Dig Site", icon=folium.Icon(color="red")).add_to(m)
        folium.Marker([start_location[1], start_location[0]], tooltip="Start Intersection").add_to(m)
        folium.PolyLine(route_coords, color="blue", weight=3).add_to(m)

        st.session_state.narrative = narrative
        st.session_state.map_html = m._repr_html_()

    except Exception as e:
        st.error(f"Error: {e}")

# =========================
# Persisted display
# =========================
if st.session_state.narrative:
    st.subheader("Turn‑by‑Turn Directions")
    st.write("\n".join(st.session_state.narrative))

if st.session_state.map_html:
    st.components.v1.html(st.session_state.map_html, height=520)

# Manual reset
if st.button("Clear results"):
    st.session_state.narrative = None
    st.session_state.map_html = None
