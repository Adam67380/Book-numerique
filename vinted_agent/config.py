"""Configuration des recherches Vinted pour l'achat/revente."""

import yaml
import os

# Configuration par défaut
DEFAULT_CONFIG = {
    "country": "fr",
    "scan_interval_seconds": 120,  # 2 minutes entre chaque cycle
    "max_results_per_search": 20,

    "brands": [
        {
            "name": "Ralph Lauren",
            "keywords": ["Ralph Lauren polo", "Ralph Lauren chemise", "Ralph Lauren blouson"],
            "price_from": 5,
            "price_to": 40,
            "resale_min": 25,  # Prix de revente minimum estimé
        },
        {
            "name": "Tommy Hilfiger",
            "keywords": ["Tommy Hilfiger veste", "Tommy Hilfiger pull", "Tommy Hilfiger chemise"],
            "price_from": 5,
            "price_to": 35,
            "resale_min": 20,
        },
        {
            "name": "Lacoste",
            "keywords": ["Lacoste polo", "Lacoste sweat", "Lacoste veste"],
            "price_from": 5,
            "price_to": 30,
            "resale_min": 20,
        },
        {
            "name": "The North Face",
            "keywords": ["The North Face doudoune", "The North Face veste", "The North Face polaire"],
            "price_from": 10,
            "price_to": 60,
            "resale_min": 40,
        },
        {
            "name": "Nike",
            "keywords": ["Nike vintage sweat", "Nike veste", "Nike coupe-vent"],
            "price_from": 5,
            "price_to": 30,
            "resale_min": 20,
        },
    ],

    # Filtres globaux
    "filters": {
        "exclude_countries": [],       # Ex: ["Italie", "Espagne"]
        "min_photos": 2,               # Nombre minimum de photos
        "max_favourite_count": 50,      # Éviter articles trop populaires (concurrence)
    },

    # Notifications
    "notifications": {
        "enabled": False,
        "discord_webhook": "",         # URL webhook Discord (optionnel)
    },
}


def load_config(path: str = "config/vinted_config.yaml") -> dict:
    """Charge la configuration depuis un fichier YAML ou utilise les valeurs par défaut."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        # Fusion : les valeurs utilisateur écrasent les défauts
        config = {**DEFAULT_CONFIG, **user_config}
        if "brands" in user_config:
            config["brands"] = user_config["brands"]
        if "filters" in user_config:
            config["filters"] = {**DEFAULT_CONFIG["filters"], **user_config["filters"]}
        return config
    return DEFAULT_CONFIG.copy()


def save_default_config(path: str = "config/vinted_config.yaml"):
    """Sauvegarde la configuration par défaut dans un fichier YAML."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"✅ Configuration sauvegardée dans {path}")
