"""Client API Vinted avec gestion correcte des cookies et sessions.

Vinted n'a pas d'API publique. Pour accéder à l'API interne, il faut :
1. Visiter le site pour obtenir un cookie de session
2. Utiliser ce cookie dans les requêtes API
3. Respecter les délais entre requêtes pour éviter le blocage
"""

import time
import random
import requests
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import Timeout, ConnectionError, JSONDecodeError


# Domaines Vinted par pays
VINTED_DOMAINS = {
    "fr": "www.vinted.fr",
    "be": "www.vinted.be",
    "es": "www.vinted.es",
    "it": "www.vinted.it",
    "de": "www.vinted.de",
    "nl": "www.vinted.nl",
    "uk": "www.vinted.co.uk",
}

# User-Agent réaliste
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class VintedAPI:
    """Client pour l'API interne de Vinted."""

    def __init__(self, country: str = "fr", timeout: int = 20):
        self.domain = VINTED_DOMAINS.get(country, VINTED_DOMAINS["fr"])
        self.base_url = f"https://{self.domain}"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"{self.base_url}/",
            "Origin": self.base_url,
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        self._session_valid = False

    def _init_session(self) -> bool:
        """Visite le site pour obtenir les cookies de session."""
        try:
            print("  🔑 Initialisation de la session Vinted...")
            resp = self.session.get(
                self.base_url,
                timeout=self.timeout,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                self._session_valid = True
                print("  ✅ Session initialisée")
                return True
            else:
                print(f"  ⚠️  Status {resp.status_code} lors de l'init session")
                return False
        except (Timeout, ConnectionError) as e:
            print(f"  ❌ Erreur réseau lors de l'init session : {e}")
            return False

    def _ensure_session(self):
        """S'assure qu'une session valide existe."""
        if not self._session_valid:
            for attempt in range(3):
                if self._init_session():
                    return
                wait = 2 ** (attempt + 1)
                print(f"  ⏳ Nouvelle tentative dans {wait}s...")
                time.sleep(wait)
            raise RuntimeError("Impossible d'initialiser la session Vinted")

    def search(
        self,
        query: str,
        price_from: float | None = None,
        price_to: float | None = None,
        catalog_ids: str = "",
        order: str = "newest_first",
        per_page: int = 20,
        page: int = 1,
        brand_ids: str = "",
    ) -> list[dict]:
        """Recherche des articles sur Vinted.

        Args:
            query: Texte de recherche (ex: "Ralph Lauren blouson")
            price_from: Prix minimum en euros
            price_to: Prix maximum en euros
            catalog_ids: IDs de catégories (séparés par virgules)
            order: Tri — newest_first, price_low_to_high, price_high_to_low
            per_page: Nombre de résultats par page (max 96)
            page: Numéro de page
            brand_ids: IDs de marques Vinted (séparés par virgules)

        Returns:
            Liste d'articles trouvés
        """
        self._ensure_session()

        params = {
            "search_text": query,
            "order": order,
            "per_page": min(per_page, 96),
            "page": page,
        }
        if catalog_ids:
            params["catalog_ids"] = catalog_ids
        if brand_ids:
            params["brand_ids"] = brand_ids
        if price_from is not None:
            params["price_from"] = str(price_from)
        if price_to is not None:
            params["price_to"] = str(price_to)

        url = f"{self.base_url}/api/v2/catalog/items"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Délai aléatoire pour éviter la détection
                delay = random.uniform(1.5, 4.0)
                time.sleep(delay)

                resp = self.session.get(url, params=params, timeout=self.timeout)

                # Si Vinted renvoie une redirection ou une page HTML
                if resp.status_code in (301, 302, 403):
                    print(f"  ⚠️  Blocage détecté (status {resp.status_code}), "
                          f"réinitialisation session...")
                    self._session_valid = False
                    self._ensure_session()
                    continue

                if resp.status_code == 429:
                    wait = 2 ** (attempt + 2)
                    print(f"  ⚠️  Rate limit atteint, attente {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code == 204 or not resp.text.strip():
                    return []

                # Vérifier que la réponse est du JSON
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" not in content_type and "text/json" not in content_type:
                    print(f"  ⚠️  Réponse non-JSON (Content-Type: {content_type})")
                    # Réinitialiser la session car les cookies ont peut-être expiré
                    self._session_valid = False
                    if attempt < max_retries - 1:
                        print("  🔄 Réinitialisation de la session...")
                        self._ensure_session()
                        continue
                    return []

                try:
                    data = resp.json()
                except JSONDecodeError:
                    print(f"  ⚠️  Réponse non parsable (status {resp.status_code})")
                    self._session_valid = False
                    if attempt < max_retries - 1:
                        self._ensure_session()
                        continue
                    return []

                items = data.get("items", [])
                return items

            except (Timeout, ReadTimeoutError) as e:
                wait = 2 ** (attempt + 1)
                print(f"  ⏱️  Timeout, nouvelle tentative dans {wait}s... ({e.__class__.__name__})")
                time.sleep(wait)

            except ConnectionError as e:
                wait = 2 ** (attempt + 1)
                print(f"  🌐 Erreur connexion, tentative {attempt + 1}/{max_retries} "
                      f"dans {wait}s...")
                time.sleep(wait)

        print(f"  ❌ Échec après {max_retries} tentatives pour '{query}'")
        return []

    def get_item(self, item_id: int) -> dict | None:
        """Récupère les détails d'un article par son ID."""
        self._ensure_session()
        url = f"{self.base_url}/api/v2/items/{item_id}"

        try:
            time.sleep(random.uniform(1.0, 2.5))
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("item", data)
            return None
        except (Timeout, ConnectionError, JSONDecodeError):
            return None


def parse_item(raw: dict) -> dict:
    """Extrait les champs utiles d'un article brut Vinted."""
    return {
        "id": raw.get("id"),
        "title": raw.get("title", ""),
        "price": float(raw.get("price", {}).get("amount", 0))
            if isinstance(raw.get("price"), dict)
            else float(raw.get("total_item_price", {}).get("amount", 0)
                       if isinstance(raw.get("total_item_price"), dict) else 0),
        "brand": raw.get("brand_title", ""),
        "size": raw.get("size_title", ""),
        "status": raw.get("status", ""),
        "photo_url": raw.get("photo", {}).get("url", "")
            if isinstance(raw.get("photo"), dict) else "",
        "url": raw.get("url", ""),
        "user": raw.get("user", {}).get("login", "")
            if isinstance(raw.get("user"), dict) else "",
        "country": raw.get("user", {}).get("country_title", "")
            if isinstance(raw.get("user"), dict) else "",
        "favourite_count": raw.get("favourite_count", 0),
    }
