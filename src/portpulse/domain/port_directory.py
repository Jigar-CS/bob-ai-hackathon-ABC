"""Global Port Directory & Spatial Haversine Distance Engine.

Provides country-wise port catalog (including comprehensive Indian ports)
and dynamic spatial distance computation for alternate port routing.
"""

from __future__ import annotations

import math
from typing import Any


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Calculate geodesic distance in km between two lat/lon coordinates."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c)


def calculate_sea_route_waypoints(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> list[tuple[float, float]]:
    """Determine maritime sea-lane waypoints avoiding land masses via global chokepoints."""
    WAYPOINT_MALACCA = (1.35, 103.55)
    WAYPOINT_SRI_LANKA = (5.92, 80.50)
    WAYPOINT_BAB_EL_MANDEB = (12.60, 43.30)
    WAYPOINT_SUEZ = (29.93, 32.55)
    WAYPOINT_GIBRALTAR = (35.95, -5.60)
    WAYPOINT_PANAMA = (9.00, -79.68)
    WAYPOINT_ENGLISH_CHANNEL = (50.00, -0.50)

    def _region(lat: float, lon: float) -> str:
        if 0 <= lat <= 45 and 100 <= lon <= 145:
            return "EAST_ASIA"
        if -10 <= lat <= 20 and 95 <= lon <= 115:
            return "SE_ASIA"
        if 5 <= lat <= 30 and 60 <= lon <= 90:
            return "INDIA"
        if 20 <= lat <= 30 and 45 <= lon <= 60:
            return "PERSIAN_GULF"
        if 40 <= lat <= 65 and -10 <= lon <= 30:
            return "NORTH_EUROPE"
        if 25 <= lat <= 50 and -130 <= lon <= -115:
            return "US_WEST"
        if 25 <= lat <= 45 and -95 <= lon <= -65:
            return "US_EAST"
        if -45 <= lat <= -10 and 110 <= lon <= 155:
            return "AUSTRALIA"
        return "GLOBAL"

    r1 = _region(lat1, lon1)
    r2 = _region(lat2, lon2)
    waypoints: list[tuple[float, float]] = [(lat1, lon1)]

    # East/SE Asia <-> India/Persian Gulf
    if (r1 in ("EAST_ASIA", "SE_ASIA") and r2 in ("INDIA", "PERSIAN_GULF")) or (
        r2 in ("EAST_ASIA", "SE_ASIA") and r1 in ("INDIA", "PERSIAN_GULF")
    ):
        if r1 in ("EAST_ASIA", "SE_ASIA"):
            waypoints.extend([WAYPOINT_MALACCA, WAYPOINT_SRI_LANKA])
        else:
            waypoints.extend([WAYPOINT_SRI_LANKA, WAYPOINT_MALACCA])

    # East Asia/India <-> North Europe
    elif (r1 in ("EAST_ASIA", "SE_ASIA", "INDIA", "PERSIAN_GULF") and r2 == "NORTH_EUROPE") or (
        r2 in ("EAST_ASIA", "SE_ASIA", "INDIA", "PERSIAN_GULF") and r1 == "NORTH_EUROPE"
    ):
        if r1 in ("EAST_ASIA", "SE_ASIA"):
            waypoints.extend(
                [
                    WAYPOINT_MALACCA,
                    WAYPOINT_SRI_LANKA,
                    WAYPOINT_BAB_EL_MANDEB,
                    WAYPOINT_SUEZ,
                    WAYPOINT_GIBRALTAR,
                    WAYPOINT_ENGLISH_CHANNEL,
                ]
            )
        elif r1 in ("INDIA", "PERSIAN_GULF"):
            waypoints.extend(
                [
                    WAYPOINT_BAB_EL_MANDEB,
                    WAYPOINT_SUEZ,
                    WAYPOINT_GIBRALTAR,
                    WAYPOINT_ENGLISH_CHANNEL,
                ]
            )
        elif r2 in ("EAST_ASIA", "SE_ASIA"):
            waypoints.extend(
                [
                    WAYPOINT_ENGLISH_CHANNEL,
                    WAYPOINT_GIBRALTAR,
                    WAYPOINT_SUEZ,
                    WAYPOINT_BAB_EL_MANDEB,
                    WAYPOINT_SRI_LANKA,
                    WAYPOINT_MALACCA,
                ]
            )
        else:
            waypoints.extend(
                [
                    WAYPOINT_ENGLISH_CHANNEL,
                    WAYPOINT_GIBRALTAR,
                    WAYPOINT_SUEZ,
                    WAYPOINT_BAB_EL_MANDEB,
                ]
            )

    # East Asia <-> US East Coast (via Panama)
    elif (r1 in ("EAST_ASIA", "SE_ASIA") and r2 == "US_EAST") or (
        r2 in ("EAST_ASIA", "SE_ASIA") and r1 == "US_EAST"
    ):
        waypoints.append(WAYPOINT_PANAMA)

    # India <-> US West Coast (via Malacca & Pacific)
    elif (r1 in ("INDIA", "PERSIAN_GULF") and r2 == "US_WEST") or (
        r2 in ("INDIA", "PERSIAN_GULF") and r1 == "US_WEST"
    ):
        if r1 in ("INDIA", "PERSIAN_GULF"):
            waypoints.extend([WAYPOINT_SRI_LANKA, WAYPOINT_MALACCA])
        else:
            waypoints.extend([WAYPOINT_MALACCA, WAYPOINT_SRI_LANKA])

    waypoints.append((lat2, lon2))
    return waypoints


def calculate_sea_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[int, int]:
    """Calculate actual maritime sea route distance in Nautical Miles (nmi) and Kilometers (km).

    Returns:
        tuple[int, int]: (distance_nmi, distance_km)
    """
    waypoints = calculate_sea_route_waypoints(lat1, lon1, lat2, lon2)
    total_km = 0.0
    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]
        dist = haversine_distance_km(p1[0], p1[1], p2[0], p2[1])
        total_km += dist

    if len(waypoints) > 2:
        total_km *= 1.05

    dist_km = round(total_km)
    dist_nmi = round(dist_km / 1.852)
    return dist_nmi, dist_km


PORT_DIRECTORY: dict[str, list[dict[str, Any]]] = {
    "India": [
        {
            "port": "JNPT / Nhava Sheva (Navi Mumbai)",
            "lat": 18.95,
            "lon": 72.95,
            "spare_capacity_teu": 15000,
        },
        {"port": "Mundra Port (Gujarat)", "lat": 22.74, "lon": 69.70, "spare_capacity_teu": 18000},
        {
            "port": "Deendayal Port / Kandla (Gujarat)",
            "lat": 23.00,
            "lon": 70.22,
            "spare_capacity_teu": 12000,
        },
        {
            "port": "Chennai Port (Tamil Nadu)",
            "lat": 13.08,
            "lon": 80.29,
            "spare_capacity_teu": 14000,
        },
        {
            "port": "V.O. Chidambaranar Port / Tuticorin",
            "lat": 8.75,
            "lon": 78.18,
            "spare_capacity_teu": 10000,
        },
        {
            "port": "Visakhapatnam Port (Andhra Pradesh)",
            "lat": 17.69,
            "lon": 83.29,
            "spare_capacity_teu": 13000,
        },
        {
            "port": "Cochin Port / Vallarpadam (Kerala)",
            "lat": 9.96,
            "lon": 76.26,
            "spare_capacity_teu": 11000,
        },
        {
            "port": "Kamarajar Port / Ennore (Tamil Nadu)",
            "lat": 13.26,
            "lon": 80.33,
            "spare_capacity_teu": 9000,
        },
        {"port": "Paradip Port (Odisha)", "lat": 20.26, "lon": 86.67, "spare_capacity_teu": 12500},
        {
            "port": "New Mangalore Port (Karnataka)",
            "lat": 12.92,
            "lon": 74.81,
            "spare_capacity_teu": 8500,
        },
        {"port": "Mormugao Port (Goa)", "lat": 15.41, "lon": 73.80, "spare_capacity_teu": 7500},
        {
            "port": "Kolkata / Haldia Port (West Bengal)",
            "lat": 22.54,
            "lon": 88.31,
            "spare_capacity_teu": 9500,
        },
    ],
    "United States": [
        {
            "port": "Port of LA / Long Beach",
            "lat": 33.73,
            "lon": -118.26,
            "spare_capacity_teu": 18000,
        },
        {"port": "Port of Oakland", "lat": 37.80, "lon": -122.27, "spare_capacity_teu": 12000},
        {
            "port": "Port of Seattle / Tacoma",
            "lat": 47.60,
            "lon": -122.33,
            "spare_capacity_teu": 15000,
        },
        {"port": "Port of NY & NJ", "lat": 40.66, "lon": -74.12, "spare_capacity_teu": 16000},
        {"port": "Port of Houston", "lat": 29.74, "lon": -95.14, "spare_capacity_teu": 11000},
        {"port": "Port of Savannah", "lat": 32.08, "lon": -81.09, "spare_capacity_teu": 14000},
        {"port": "Port of Ensenada", "lat": 31.85, "lon": -116.63, "spare_capacity_teu": 5000},
    ],
    "United Arab Emirates": [
        {"port": "Jebel Ali Port (Dubai)", "lat": 24.98, "lon": 55.06, "spare_capacity_teu": 20000},
        {
            "port": "Khalifa Port (Abu Dhabi)",
            "lat": 24.79,
            "lon": 54.62,
            "spare_capacity_teu": 14000,
        },
        {
            "port": "Port of Sharjah / Khor Fakkan",
            "lat": 25.36,
            "lon": 56.36,
            "spare_capacity_teu": 10000,
        },
    ],
    "Singapore": [
        {"port": "Port of Singapore", "lat": 1.27, "lon": 103.84, "spare_capacity_teu": 25000},
        {
            "port": "Port of Tanjung Pelepas (Malaysia)",
            "lat": 1.36,
            "lon": 103.54,
            "spare_capacity_teu": 16000,
        },
        {"port": "Port Klang (Malaysia)", "lat": 3.00, "lon": 101.40, "spare_capacity_teu": 18000},
    ],
    "Netherlands": [
        {"port": "Port of Rotterdam", "lat": 51.95, "lon": 4.14, "spare_capacity_teu": 22000},
        {
            "port": "Port of Antwerp (Belgium)",
            "lat": 51.27,
            "lon": 4.33,
            "spare_capacity_teu": 19000,
        },
        {"port": "Port of Amsterdam", "lat": 52.41, "lon": 4.81, "spare_capacity_teu": 9000},
    ],
    "Germany": [
        {"port": "Port of Hamburg", "lat": 53.54, "lon": 9.97, "spare_capacity_teu": 17000},
        {"port": "Bremerhaven Port", "lat": 53.55, "lon": 8.57, "spare_capacity_teu": 13000},
        {
            "port": "JadeWeserPort (Wilhelmshaven)",
            "lat": 53.59,
            "lon": 8.15,
            "spare_capacity_teu": 11000,
        },
    ],
    "China": [
        {"port": "Shanghai Port", "lat": 31.23, "lon": 121.47, "spare_capacity_teu": 30000},
        {"port": "Ningbo-Zhoushan Port", "lat": 29.87, "lon": 121.54, "spare_capacity_teu": 28000},
        {"port": "Shenzhen / Yantian", "lat": 22.57, "lon": 114.27, "spare_capacity_teu": 22000},
        {"port": "Qingdao Port", "lat": 36.06, "lon": 120.38, "spare_capacity_teu": 18000},
        {"port": "Guangzhou Port", "lat": 23.09, "lon": 113.48, "spare_capacity_teu": 20000},
    ],
    "Japan": [
        {"port": "Port of Yokohama", "lat": 35.44, "lon": 139.64, "spare_capacity_teu": 12000},
        {"port": "Port of Tokyo", "lat": 35.62, "lon": 139.77, "spare_capacity_teu": 11000},
        {"port": "Port of Kobe", "lat": 34.68, "lon": 135.23, "spare_capacity_teu": 10000},
        {"port": "Port of Nagoya", "lat": 35.08, "lon": 136.88, "spare_capacity_teu": 10500},
    ],
    "South Korea": [
        {"port": "Port of Busan", "lat": 35.10, "lon": 129.04, "spare_capacity_teu": 20000},
        {"port": "Incheon Port", "lat": 37.46, "lon": 126.62, "spare_capacity_teu": 12000},
        {"port": "Gwangyang Port", "lat": 34.90, "lon": 127.70, "spare_capacity_teu": 11000},
    ],
    "Australia": [
        {"port": "Port of Melbourne", "lat": -37.84, "lon": 144.93, "spare_capacity_teu": 10000},
        {"port": "Port Botany (Sydney)", "lat": -33.97, "lon": 151.23, "spare_capacity_teu": 11000},
        {"port": "Port of Brisbane", "lat": -27.38, "lon": 153.17, "spare_capacity_teu": 9000},
        {
            "port": "Fremantle Port (Perth)",
            "lat": -32.05,
            "lon": 115.74,
            "spare_capacity_teu": 8000,
        },
    ],
}


def get_dynamic_alternate_ports(
    home_lat: float | None = None,
    home_lon: float | None = None,
    max_count: int = 6,
) -> list[dict[str, Any]]:
    """Compute spatial distance to all global candidate ports and return nearest."""
    all_ports: list[dict[str, Any]] = []
    for country, ports in PORT_DIRECTORY.items():
        for p in ports:
            all_ports.append(
                {
                    "port": p["port"],
                    "country": country,
                    "lat": float(p["lat"]),
                    "lon": float(p["lon"]),
                    "spare_capacity_teu": int(p["spare_capacity_teu"]),
                }
            )

    if home_lat is None or home_lon is None:
        home_lat, home_lon = 33.73, -118.26

    candidates: list[dict[str, Any]] = []
    for p in all_ports:
        dist_nmi, dist_km = calculate_sea_distance(home_lat, home_lon, p["lat"], p["lon"])
        if dist_km < 5:
            continue
        candidates.append(
            {
                "port": p["port"],
                "distance_nmi": dist_nmi,
                "distance_km": dist_km,
                "spare_capacity_teu": p["spare_capacity_teu"],
            }
        )

    candidates.sort(key=lambda x: x["distance_nmi"])
    return candidates[:max_count]
