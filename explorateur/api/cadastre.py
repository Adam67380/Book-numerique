"""Client IGN API Carto — récupération de parcelle cadastrale."""
import requests

_BASE = "https://apicarto.ign.fr/api/cadastre"


def get_parcelle(lat: float, lon: float) -> dict | None:
    """
    Retourne la parcelle la plus proche du point lat/lon.
    {parcelle_id, surface_m2, geometry_geojson}
    """
    resp = requests.get(
        f"{_BASE}/parcelle",
        params={"lon": lon, "lat": lat, "_limit": 1},
        timeout=15,
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    feat = features[0]
    props = feat["properties"]
    return {
        "parcelle_id": props.get("id", ""),
        "surface_m2": props.get("contenance", 0),
        "geometry": feat.get("geometry"),
        "commune": props.get("commune", ""),
        "section": props.get("section", ""),
        "numero": props.get("numero", ""),
    }
