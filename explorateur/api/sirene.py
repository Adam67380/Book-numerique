"""Client SIRENE (INSEE) — établissements actifs NAF 47.11D/F, hors diffusion partielle."""
import time
import requests
from typing import Iterator

_TOKEN_URL = "https://api.insee.fr/token"
_BASE_URL = "https://api.insee.fr/entreprises/sirene/V3.11"


def _get_token(key: str, secret: str) -> str:
    resp = requests.post(
        _TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(key, secret),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class SireneClient:
    def __init__(self, key: str, secret: str):
        self._key = key
        self._secret = secret
        self._token: str | None = None
        self._token_ts: float = 0.0

    def _auth_header(self) -> dict:
        if not self._token or time.time() - self._token_ts > 3500:
            self._token = _get_token(self._key, self._secret)
            self._token_ts = time.time()
        return {"Authorization": f"Bearer {self._token}"}

    def get_etablissements(self, commune_code: str, naf_codes: list[str]) -> Iterator[dict]:
        """
        Yield établissements actifs pour une commune et une liste de codes NAF,
        en excluant ceux en diffusion partielle (statutDiffusionEtablissement == 'P').
        """
        naf_filter = " OR ".join(f'activitePrincipaleEtablissement:"{n}"' for n in naf_codes)
        q = (
            f"({naf_filter})"
            f" AND etatAdministratifEtablissement:A"
            f" AND codeCommuneEtablissement:{commune_code}"
        )
        cursor = "*"
        while True:
            resp = requests.get(
                f"{_BASE_URL}/siret",
                headers=self._auth_header(),
                params={"q": q, "nombre": 100, "curseur": cursor, "champs": (
                    "siret,siren,denominationUniteLegale,nomUniteLegale,prenom1UniteLegale,"
                    "activitePrincipaleEtablissement,adresseEtablissement,"
                    "statutDiffusionEtablissement,etatAdministratifEtablissement,"
                    "categorieJuridiqueUniteLegale"
                )},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            etablissements = data.get("etablissements", [])
            for etab in etablissements:
                # Garde-fou RGPD : exclure diffusion partielle
                if etab.get("statutDiffusionEtablissement") == "P":
                    continue
                yield etab
            next_cursor = data.get("header", {}).get("curseurSuivant")
            if not next_cursor or next_cursor == cursor or not etablissements:
                break
            cursor = next_cursor
            time.sleep(0.2)  # politesse API
