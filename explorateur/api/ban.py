"""Client BAN (Base Adresse Nationale) — géocodage d'adresse."""
import requests


_BAN_URL = "https://api-adresse.data.gouv.fr/search/"


def geocode(adresse: str, citycode: str | None = None) -> dict | None:
    """
    Retourne {"lat": float, "lon": float, "label": str, "score": float} ou None.
    """
    params = {"q": adresse, "limit": 1}
    if citycode:
        params["citycode"] = citycode
    resp = requests.get(_BAN_URL, params=params, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    feat = features[0]
    lon, lat = feat["geometry"]["coordinates"]
    return {
        "lat": lat,
        "lon": lon,
        "label": feat["properties"].get("label", ""),
        "score": feat["properties"].get("score", 0.0),
    }
