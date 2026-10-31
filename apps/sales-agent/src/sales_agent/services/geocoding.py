from __future__ import annotations

import math

import requests
import structlog

GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x"


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two geographic coordinates using Haversine formula.

    Args:
        lat1: Latitude of first point in degrees
        lon1: Longitude of first point in degrees
        lat2: Latitude of second point in degrees
        lon2: Longitude of second point in degrees

    Returns:
        Distance in meters
    """
    r = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    cos_lat1 = math.cos(math.radians(lat1))
    cos_lat2 = math.cos(math.radians(lat2))
    sin_dlon_half_sq = math.sin(dlon / 2) ** 2
    a = math.sin(dlat / 2) ** 2 + cos_lat1 * cos_lat2 * sin_dlon_half_sq
    return 2 * r * math.asin(math.sqrt(a))


def geocode_address(address: str, api_key: str) -> tuple[float, float]:
    """Convert address string to geographic coordinates using Yandex Geocoder API.

    Args:
        address: Full address string to geocode
        api_key: Yandex Geocoder API key

    Returns:
        Tuple of (latitude, longitude) in degrees

    Raises:
        ValueError: If address not found
        requests.HTTPError: If API request fails
    """
    params = {
        "apikey": api_key,
        "geocode": address,
        "format": "json",
        "lang": "ru_RU",
        "results": 1,
    }
    log = structlog.get_logger()
    log.debug(
        "geocode.request",
        params={k: v for k, v in params.items() if k != "apikey"},
    )
    r = requests.get(GEOCODER_URL, params=params, timeout=10)
    r.raise_for_status()
    members = r.json()["response"]["GeoObjectCollection"]["featureMember"]
    if not members:
        raise ValueError("Address not found")
    lon_str, lat_str = members[0]["GeoObject"]["Point"]["pos"].split()
    return float(lat_str), float(lon_str)


def nearest_metro(lat: float, lon: float, api_key: str) -> tuple[str, float, float]:
    """Find nearest metro station to given coordinates using Yandex Geocoder API.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        api_key: Yandex Geocoder API key

    Returns:
        Tuple of (station_name, latitude, longitude)

    Raises:
        ValueError: If no metro station found nearby
        requests.HTTPError: If API request fails
    """
    params = {
        "apikey": api_key,
        "geocode": f"{lon},{lat}",
        "kind": "metro",
        "format": "json",
        "lang": "ru_RU",
        "results": 1,
    }
    log = structlog.get_logger()
    log.debug(
        "geocode.metro",
        params={k: v for k, v in params.items() if k != "apikey"},
    )
    r = requests.get(GEOCODER_URL, params=params, timeout=10)
    r.raise_for_status()
    members = r.json()["response"]["GeoObjectCollection"]["featureMember"]
    if not members:
        raise ValueError("No metro found nearby")
    obj = members[0]["GeoObject"]
    name = obj["name"]
    lon_str, lat_str = obj["Point"]["pos"].split()
    return name, float(lat_str), float(lon_str)


def get_nearest_metro_distance(address: str, api_key: str) -> tuple[str, float] | None:
    """Find nearest metro station and distance from given address.

    High-level function that composes geocoding, metro search, and distance calculation.
    Handles all errors gracefully by returning None.

    Args:
        address: Full address string to search from
        api_key: Yandex Geocoder API key

    Returns:
        Tuple of (station_name, distance_in_meters) or None if any error occurs
    """
    try:
        lat, lon = geocode_address(address, api_key)
        name, mlat, mlon = nearest_metro(lat, lon, api_key)
        dist = haversine_meters(lat, lon, mlat, mlon)
        return name, dist
    except Exception:
        return None


def distance_from_spb_kad_km(lat: float, lon: float) -> float:
    """Approximate distance from Saint Petersburg KAD ring in kilometers.

    Uses a simple circular approximation of KAD to avoid external datasets.
    Returns 0 if inside the ring, otherwise the distance beyond the ring.

    Note: This is a coarse heuristic sufficient for threshold checks (e.g., >3 km).
    """
    # Approximate city center near Nevsky Prospekt
    SPB_CENTER_LAT = 59.9386
    SPB_CENTER_LON = 30.3141
    # Approximate KAD radius in km (coarse average)
    KAD_RADIUS_KM = 22.0

    # Compute radial distance from city center
    center_distance_m = haversine_meters(lat, lon, SPB_CENTER_LAT, SPB_CENTER_LON)
    center_distance_km = center_distance_m / 1000.0
    # If far away from SPB entirely (>100 km), treat as not applicable
    if center_distance_km > 100.0:
        return -1.0

    return max(0.0, center_distance_km - KAD_RADIUS_KM)
