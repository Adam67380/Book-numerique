"""Client Pappers — dirigeants et mandats (SCI candidates)."""
import time
import requests

_BASE = "https://api.pappers.fr/v2"
SCI_FORME = "6540"


class PappersClient:
    def __init__(self, api_key: str):
        self._key = api_key

    def _get(self, path: str, params: dict) -> dict:
        params["api_token"] = self._key
        resp = requests.get(f"{_BASE}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_dirigeants(self, siren: str) -> list[dict]:
        """Retourne la liste des dirigeants d'une entreprise (par SIREN)."""
        data = self._get("/entreprise", {"siren": siren, "extrait_kbis": False})
        return data.get("dirigeants", [])

    def get_mandats(self, dirigeant: dict) -> list[dict]:
        """
        Retourne les mandats d'un dirigeant (personne physique).
        On recherche par nom/prénom pour récupérer les entreprises liées.
        """
        nom = dirigeant.get("nom", "")
        prenom = dirigeant.get("prenom", "")
        if not nom:
            return []
        data = self._get(
            "/recherche-dirigeants",
            {"nom": nom, "prenom": prenom, "par_page": 20},
        )
        mandats = []
        for result in data.get("resultats", []):
            for entreprise in result.get("entreprises", []):
                mandats.append(entreprise)
        return mandats

    def is_sci(self, mandat: dict) -> bool:
        return mandat.get("forme_juridique_code", "") == SCI_FORME

    def get_sci_candidates(self, siren: str) -> list[dict]:
        """Pipeline complet : SIREN → dirigeants → mandats → SCI candidates."""
        scis = []
        dirigeants = self.get_dirigeants(siren)
        for d in dirigeants:
            time.sleep(0.3)  # throttle
            mandats = self.get_mandats(d)
            scis.extend(m for m in mandats if self.is_sci(m))
        # Dédoublonner par SIREN
        seen = set()
        unique = []
        for s in scis:
            key = s.get("siren", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
