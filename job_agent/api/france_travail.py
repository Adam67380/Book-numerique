"""Client API France Travail (ex Pôle Emploi) - Offres d'emploi v2."""

import re
import time
import urllib3
import requests

# Désactiver les avertissements SSL pour les réseaux d'entreprise
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .base import JobAPIClient, JobOffer

AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
API_BASE = "https://api.francetravail.io/partenaire/offresdemploi/v2"
GEO_API = "https://geo.api.gouv.fr"

# Codes département pour les grandes villes
VILLE_DEPARTEMENTS = {
    "paris": "75",
    "marseille": "13",
    "lyon": "69",
    "toulouse": "31",
    "nice": "06",
    "nantes": "44",
    "strasbourg": "67",
    "montpellier": "34",
    "bordeaux": "33",
    "lille": "59",
    "rennes": "35",
    "reims": "51",
    "toulon": "83",
    "grenoble": "38",
    "dijon": "21",
    "angers": "49",
    "nimes": "30",
    "clermont-ferrand": "63",
    "tours": "37",
    "amiens": "80",
    "metz": "57",
    "rouen": "76",
    "nancy": "54",
    "orleans": "45",
    "mulhouse": "68",
    "caen": "14",
    "perpignan": "66",
    "brest": "29",
    "limoges": "87",
    "besancon": "25",
    "poitiers": "86",
}


class FranceTravailClient(JobAPIClient):
    """Client pour l'API Offres d'emploi de France Travail."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0

    def authenticate(self) -> None:
        """Obtient un token OAuth2 via client_credentials."""
        if self.access_token and time.time() < self.token_expiry:
            return

        resp = requests.post(
            AUTH_URL,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
            verify=False,
        )
        if not resp.ok:
            print(f"  Erreur authentification ({resp.status_code}): {resp.text[:200]}")
            resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"Réponse auth invalide (status {resp.status_code}): {resp.text[:200]}")

        self.access_token = data["access_token"]
        self.token_expiry = time.time() + data.get("expires_in", 1500) - 60
        print("  Authentification France Travail OK.")

    def _headers(self) -> dict:
        self.authenticate()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _resolve_location(self, location: str) -> dict:
        """Résout un nom de ville en paramètres API (commune ou département)."""
        loc_lower = location.lower().strip()

        # Si c'est un code département (ex: "75", "67")
        if loc_lower.isdigit() and len(loc_lower) <= 3:
            return {"departement": loc_lower}

        # Vérifier la table des grandes villes
        if loc_lower in VILLE_DEPARTEMENTS:
            return {"departement": VILLE_DEPARTEMENTS[loc_lower]}

        # Essayer l'API geo.gouv.fr pour obtenir le code commune
        try:
            resp = requests.get(
                f"{GEO_API}/communes",
                params={"nom": location, "limit": 1, "fields": "code,nom,codeDepartement"},
                timeout=10,
                verify=False,
            )
            if resp.ok:
                results = resp.json()
                if results:
                    return {"commune": results[0]["code"]}
        except Exception:
            pass

        # Fallback : utiliser comme mot-clé dans la recherche
        return {}

    def search(self, keywords: str, location: str = "", radius_km: int = 30,
               limit: int = 20) -> list[JobOffer]:
        """Recherche d'offres via l'API France Travail."""
        params = {
            "motsCles": keywords,
            "range": f"0-{min(limit, 149)}",
        }
        if location:
            loc_params = self._resolve_location(location)
            if loc_params:
                params.update(loc_params)
                if "commune" in loc_params:
                    params["distance"] = radius_km
            else:
                # Ajouter la ville aux mots-clés si non résolue
                params["motsCles"] = f"{keywords} {location}"

        headers = self._headers()
        resp = requests.get(
            f"{API_BASE}/offres/search",
            params=params,
            headers=headers,
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()

        # Gérer les réponses vides (204 No Content ou body vide)
        if resp.status_code == 204 or not resp.text.strip():
            print("  Aucune offre trouvée pour ces critères.")
            return []

        try:
            data = resp.json()
        except ValueError:
            print(f"  Réponse inattendue de l'API (status {resp.status_code}): {resp.text[:200]}")
            return []

        results = data.get("resultats", [])
        return [self._parse_offer(r) for r in results]

    def get_offer(self, offer_id: str) -> JobOffer:
        """Récupère le détail d'une offre par ID."""
        resp = requests.get(
            f"{API_BASE}/offres/{offer_id}",
            headers=self._headers(),
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        return self._parse_offer(resp.json())

    def _parse_offer(self, raw: dict) -> JobOffer:
        """Convertit une réponse API en JobOffer normalisé."""
        # Compétences
        competences = []
        for c in raw.get("competences", []):
            libelle = c.get("libelle", "")
            if libelle:
                competences.append(libelle.lower().strip())

        # Salaire
        salaire_min, salaire_max = self._parse_salaire(raw.get("salaire", {}))

        # Télétravail
        teletravail = False
        description = raw.get("description", "")
        intitule = raw.get("intitule", "")
        if any(kw in (description + intitule).lower() for kw in ["télétravail", "remote", "teletravail"]):
            teletravail = True

        # Localisation
        lieu = raw.get("lieuTravail", {})
        localisation = lieu.get("libelle", "")

        # Expérience
        experience = raw.get("experienceExige", "")
        exp_libelle = raw.get("experienceLibelle", "")
        experience_str = exp_libelle if exp_libelle else experience

        # Formation
        formations = raw.get("formations", [])
        formation_str = ""
        if formations:
            formation_str = formations[0].get("niveauLibelle", "")

        # Entreprise
        entreprise = raw.get("entreprise", {})
        nom_entreprise = entreprise.get("nom", "Non précisé")

        # URL
        url = raw.get("origineOffre", {}).get("urlOrigine", "")
        if not url:
            url = f"https://candidat.francetravail.fr/offres/recherche/detail/{raw.get('id', '')}"

        return JobOffer(
            id=raw.get("id", ""),
            titre=intitule,
            entreprise=nom_entreprise,
            localisation=localisation,
            description=description,
            competences_requises=competences,
            experience_requise=experience_str,
            formation_requise=formation_str,
            salaire_min=salaire_min,
            salaire_max=salaire_max,
            type_contrat=raw.get("typeContrat", ""),
            url=url,
            teletravail=teletravail,
            raw=raw,
        )

    @staticmethod
    def _parse_salaire(salaire: dict) -> tuple[float | None, float | None]:
        """Parse le champ salaire de l'API (texte libre) en min/max numériques."""
        libelle = salaire.get("libelle", "")
        if not libelle:
            return None, None

        # Chercher des montants numériques dans le texte
        nombres = re.findall(r"[\d]+[\s]?[\d]*(?:[.,]\d+)?", libelle.replace(" ", ""))
        nombres = [float(n.replace(",", ".").replace(" ", "")) for n in nombres if n]

        if not nombres:
            return None, None

        # Convertir en annuel si c'est mensuel
        is_mensuel = any(kw in libelle.lower() for kw in ["mois", "mensuel", "menseul"])
        if is_mensuel:
            nombres = [n * 12 for n in nombres]
        # Convertir si horaire
        is_horaire = any(kw in libelle.lower() for kw in ["heure", "horaire", "/h"])
        if is_horaire:
            nombres = [n * 1820 for n in nombres]  # ~35h/semaine * 52 semaines

        if len(nombres) >= 2:
            return min(nombres), max(nombres)
        return nombres[0], nombres[0]
