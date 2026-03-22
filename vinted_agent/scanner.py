"""Scanner Vinted — Surveille les nouvelles annonces et détecte les bonnes affaires."""

import time
from datetime import datetime

from .api import VintedAPI, parse_item
from .config import load_config


class VintedScanner:
    """Scanne Vinted pour trouver des articles intéressants pour la revente."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.api = VintedAPI(country=self.config.get("country", "fr"))
        self.seen_ids: set[int] = set()

    def _is_good_deal(self, item: dict, brand_config: dict) -> bool:
        """Vérifie si un article est une bonne affaire pour la revente."""
        filters = self.config.get("filters", {})

        price = item.get("price", 0)
        if price <= 0:
            return False

        # Vérifier le potentiel de marge
        resale_min = brand_config.get("resale_min", 0)
        if resale_min > 0 and price >= resale_min * 0.8:
            return False  # Marge trop faible

        # Filtrer par nombre de photos (qualité de l'annonce)
        # Note: le champ exact dépend de la réponse API
        min_photos = filters.get("min_photos", 0)
        if min_photos > 0:
            photo_count = item.get("photo_count", 1)
            if photo_count < min_photos:
                return False

        # Filtrer les articles trop populaires (concurrence)
        max_favs = filters.get("max_favourite_count", 0)
        if max_favs > 0:
            if item.get("favourite_count", 0) > max_favs:
                return False

        # Filtrer par pays
        exclude_countries = filters.get("exclude_countries", [])
        if exclude_countries and item.get("country", "") in exclude_countries:
            return False

        return True

    def _format_item(self, item: dict) -> str:
        """Formate un article pour l'affichage."""
        lines = [
            f"  💰 {item['price']:.2f}€ — {item['title']}",
            f"     Marque: {item['brand']} | Taille: {item['size']}",
            f"     Vendeur: {item['user']} ({item['country']})",
            f"     ❤️  {item['favourite_count']} favoris",
            f"     🔗 {item['url']}",
        ]
        return "\n".join(lines)

    def scan_brand(self, brand_config: dict) -> list[dict]:
        """Scanne une marque spécifique et retourne les bonnes affaires."""
        brand_name = brand_config["name"]
        keywords = brand_config.get("keywords", [brand_name])
        price_from = brand_config.get("price_from")
        price_to = brand_config.get("price_to")
        brand_ids = brand_config.get("brand_ids", "")

        deals = []

        for keyword in keywords:
            print(f"\n🔍 [{brand_name}] Recherche: '{keyword}'")

            items_raw = self.api.search(
                query=keyword,
                price_from=price_from,
                price_to=price_to,
                per_page=self.config.get("max_results_per_search", 20),
                brand_ids=brand_ids,
            )

            if not items_raw:
                print(f"   → Aucun résultat")
                continue

            print(f"   → {len(items_raw)} résultat(s)")

            for raw in items_raw:
                item = parse_item(raw)
                item_id = item.get("id")

                # Ignorer les articles déjà vus
                if item_id in self.seen_ids:
                    continue
                self.seen_ids.add(item_id)

                if self._is_good_deal(item, brand_config):
                    deals.append(item)

        return deals

    def scan_all(self) -> list[dict]:
        """Scanne toutes les marques configurées."""
        all_deals = []
        brands = self.config.get("brands", [])

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*60}")
        print(f"🕐 [{timestamp}] Début du scan — {len(brands)} marque(s)")
        print(f"{'='*60}")

        for brand_config in brands:
            try:
                deals = self.scan_brand(brand_config)
                all_deals.extend(deals)
            except Exception as e:
                print(f"  ❌ Erreur pour {brand_config.get('name', '?')}: {e}")

        print(f"\n{'='*60}")
        if all_deals:
            print(f"🎯 {len(all_deals)} bonne(s) affaire(s) trouvée(s) !\n")
            for item in all_deals:
                print(self._format_item(item))
                print()
        else:
            print("😐 Aucune bonne affaire pour le moment.")
        print(f"{'='*60}\n")

        return all_deals

    def run(self):
        """Lance le scanner en boucle continue."""
        interval = self.config.get("scan_interval_seconds", 120)
        print(f"🚀 Agent Vinted démarré — scan toutes les {interval}s")
        print(f"   Appuyez sur Ctrl+C pour arrêter\n")

        try:
            while True:
                self.scan_all()
                print(f"⏳ Prochain scan dans {interval}s...\n")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Agent Vinted arrêté.")
