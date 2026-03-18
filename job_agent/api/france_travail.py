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
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.token_expiry = time.time() + data.get("expires_in", 1500) - 60

    def _headers(self) -> dict:
        self.authenticate()
        return {"Authorization": f"Bearer {self.access_token}"}

    def search(self, keywords: str, location: str = "", radius_km: int = 30,
               limit: int = 20) -> list[JobOffer]:
        """Recherche d'offres via l'API France Travail."""
        params = {
            "motsCles": keywords,
            "range": f"0-{min(limit, 149)}",
        }
        if location:
            params["commune"] = location
            params["distance"] = radius_km

        resp = requests.get(
            f"{API_BASE}/offres/search",
            params=params,
            headers=self._headers(),
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
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
