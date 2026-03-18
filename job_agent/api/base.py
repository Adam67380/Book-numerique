"""Modèle de données JobOffer et classe abstraite pour les clients API."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class JobOffer:
    """Représentation normalisée d'une offre d'emploi."""
    id: str
    titre: str
    entreprise: str
    localisation: str
    description: str
    competences_requises: list[str] = field(default_factory=list)
    experience_requise: str = ""
    formation_requise: str = ""
    salaire_min: float | None = None
    salaire_max: float | None = None
    type_contrat: str = ""
    url: str = ""
    teletravail: bool = False
    raw: dict = field(default_factory=dict, repr=False)


class JobAPIClient(ABC):
    """Interface abstraite pour les clients d'API d'offres d'emploi."""

    @abstractmethod
    def authenticate(self) -> None:
        """Authentification auprès de l'API."""
        ...

    @abstractmethod
    def search(self, keywords: str, location: str, radius_km: int = 30,
               limit: int = 20) -> list[JobOffer]:
        """Recherche d'offres d'emploi."""
        ...

    @abstractmethod
    def get_offer(self, offer_id: str) -> JobOffer:
        """Récupère le détail d'une offre par son ID."""
        ...
