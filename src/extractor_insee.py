"""
Étape 1 — Extraction des magasins cibles depuis l'API SIRENE (INSEE)
et synchronisation dans Airtable (upsert sur SIRET).

Cibles : NAF 47.11C (supérettes), 47.11D (supermarchés), 47.11F (hypermarchés)
Zone   : variable d'env ZONE_COMMUNES (codes INSEE, séparés par virgules)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Iterable, Iterator

import requests
from dotenv import load_dotenv

try:
    from pyairtable import Api as AirtableApi
except ImportError:
    AirtableApi = None  # géré au runtime

# ---------------------------------------------------------------------------
# Config & logging
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extractor_insee")

INSEE_KEY = os.environ.get("INSEE_KEY", "")
INSEE_SECRET = os.environ.get("INSEE_SECRET", "")
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
ZONE_COMMUNES = [c.strip() for c in os.environ.get("ZONE_COMMUNES", "").split(",") if c.strip()]

NAF_CIBLES = ["47.11C", "47.11D", "47.11F"]
AIRTABLE_TABLE = "Leads"

INSEE_TOKEN_URL = "https://api.insee.fr/token"
INSEE_SIRET_URL = "https://api.insee.fr/entreprises/sirene/V3.11/siret"


# ---------------------------------------------------------------------------
# INSEE — OAuth2 + SIRET search
# ---------------------------------------------------------------------------
def get_insee_token(key: str, secret: str) -> str:
    log.info("Authentification INSEE (OAuth2 client_credentials)...")
    resp = requests.post(
        INSEE_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(key, secret),
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Échec auth INSEE ({resp.status_code}): {resp.text[:300]}"
        )
    token = resp.json()["access_token"]
    log.info("Token INSEE obtenu OK.")
    return token


def fetch_etablissements(token: str, commune_code: str, naf_codes: list[str]) -> Iterator[dict]:
    """Yield les établissements actifs d'une commune sur la liste de codes NAF."""
    naf_filter = " OR ".join(f'activitePrincipaleEtablissement:"{n}"' for n in naf_codes)
    q = (
        f"({naf_filter})"
        f" AND etatAdministratifEtablissement:A"
        f" AND codeCommuneEtablissement:{commune_code}"
    )
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    cursor = "*"
    page = 0
    while True:
        page += 1
        log.info("INSEE commune=%s page=%d cursor=%s", commune_code, page, cursor[:10])
        resp = requests.get(
            INSEE_SIRET_URL,
            headers=headers,
            params={"q": q, "nombre": 100, "curseur": cursor},
            timeout=20,
        )
        if resp.status_code == 404:
            log.warning("Aucun résultat pour commune=%s.", commune_code)
            return
        if resp.status_code != 200:
            raise RuntimeError(f"INSEE error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        etabs = data.get("etablissements", [])
        if not etabs:
            return
        for etab in etabs:
            # Garde-fou RGPD : exclure diffusion partielle
            if etab.get("statutDiffusionEtablissement") == "P":
                continue
            yield etab
        next_cursor = data.get("header", {}).get("curseurSuivant")
        if not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor
        time.sleep(0.2)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def _build_adresse(adr: dict) -> str:
    parts = [
        adr.get("numeroVoieEtablissement"),
        adr.get("indiceRepetitionEtablissement"),
        adr.get("typeVoieEtablissement"),
        adr.get("libelleVoieEtablissement"),
    ]
    voie = " ".join(p for p in parts if p)
    cp = adr.get("codePostalEtablissement", "") or ""
    commune = adr.get("libelleCommuneEtablissement", "") or ""
    return f"{voie}, {cp} {commune}".strip(", ")


def _enseigne(etab: dict) -> str:
    period = (etab.get("periodesEtablissement") or [{}])[0]
    for k in ("enseigne1Etablissement", "enseigne2Etablissement", "enseigne3Etablissement"):
        v = period.get(k)
        if v:
            return v
    ul = etab.get("uniteLegale", {}) or {}
    return (
        ul.get("denominationUniteLegale")
        or ul.get("denominationUsuelle1UniteLegale")
        or (f"{ul.get('prenom1UniteLegale','')} {ul.get('nomUniteLegale','')}".strip())
        or ""
    )


def normalize(etab: dict) -> dict:
    adr = etab.get("adresseEtablissement", {}) or {}
    period = (etab.get("periodesEtablissement") or [{}])[0]
    return {
        "siret": etab.get("siret", ""),
        "enseigne": _enseigne(etab),
        "adresse": _build_adresse(adr),
        "commune": adr.get("libelleCommuneEtablissement", ""),
        "code_commune": adr.get("codeCommuneEtablissement", ""),
        "naf": period.get("activitePrincipaleEtablissement", ""),
    }


# ---------------------------------------------------------------------------
# Airtable upsert (par SIRET)
# ---------------------------------------------------------------------------
def upsert_airtable(records: list[dict]) -> tuple[int, int]:
    if AirtableApi is None:
        raise RuntimeError("pyairtable n'est pas installé.")
    if not AIRTABLE_TOKEN or AIRTABLE_TOKEN.startswith("TON_TOKEN"):
        log.error("AIRTABLE_TOKEN absent ou placeholder — étape Airtable sautée.")
        return 0, 0

    api = AirtableApi(AIRTABLE_TOKEN)
    table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE)

    # On lit la liste des SIRET déjà présents pour éviter les doublons.
    log.info("Lecture des leads existants dans Airtable (table=%s)...", AIRTABLE_TABLE)
    existing = {}
    for row in table.iterate(fields=["siret"], page_size=100):
        for r in row:
            siret = (r.get("fields", {}) or {}).get("siret")
            if siret:
                existing[siret] = r["id"]
    log.info("%d leads déjà en base.", len(existing))

    created = 0
    updated = 0
    to_create: list[dict] = []
    for rec in records:
        fields = {
            "siret": rec["siret"],
            "enseigne": rec["enseigne"],
            "nom_magasin": rec["enseigne"],
            "adresse": rec["adresse"],
            "commune": rec["commune"],
            "naf": rec["naf"],
            "source": "SIRENE",
            "statut": "Nouveau",
        }
        if rec["siret"] in existing:
            try:
                table.update(existing[rec["siret"]], fields)
                updated += 1
            except Exception as e:
                log.warning("Update échec siret=%s : %s", rec["siret"], e)
        else:
            to_create.append(fields)

    if to_create:
        try:
            table.batch_create(to_create)
            created = len(to_create)
        except Exception as e:
            log.error("batch_create a échoué (%s), fallback ligne par ligne.", e)
            for f in to_create:
                try:
                    table.create(f)
                    created += 1
                except Exception as e2:
                    log.warning("create échec siret=%s : %s", f.get("siret"), e2)

    return created, updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if not (INSEE_KEY and INSEE_SECRET):
        log.error("INSEE_KEY/INSEE_SECRET manquants dans .env")
        return 2
    if not ZONE_COMMUNES:
        log.error("ZONE_COMMUNES vide dans .env")
        return 2

    log.info("Zone pilote : %s | NAF : %s", ZONE_COMMUNES, NAF_CIBLES)
    token = get_insee_token(INSEE_KEY, INSEE_SECRET)

    all_records: list[dict] = []
    for commune in ZONE_COMMUNES:
        n = 0
        for etab in fetch_etablissements(token, commune, NAF_CIBLES):
            rec = normalize(etab)
            all_records.append(rec)
            n += 1
            log.info("  • %-14s | %-25s | %s", rec["siret"], rec["enseigne"][:25], rec["adresse"][:60])
        log.info("Commune %s : %d magasins.", commune, n)

    log.info("Total extrait : %d magasins.", len(all_records))

    if not all_records:
        log.warning("Aucun magasin trouvé — rien à pousser dans Airtable.")
        return 0

    created, updated = upsert_airtable(all_records)
    log.info("Airtable : %d créés, %d mis à jour.", created, updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
