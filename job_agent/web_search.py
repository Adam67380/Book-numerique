"""Recherche d'offres d'emploi sur le web + filtrage IA par Claude Haiku.

Requête directement les sites d'emploi (Indeed, WTTJ, Hellowork, APEC),
puis fait passer chaque offre en revue par Haiku pour vérifier :
- Que l'offre est encore en ligne / récente
- Que le poste correspond réellement au profil
- Score de pertinence + résumé
"""

import json
import os
import re
import time
import urllib.parse
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from job_agent.api.base import JobOffer


# ──────────────────────────────────────────────────────────────────────
# Session HTTP partagée (réutilise les connexions + proxy système)
# ──────────────────────────────────────────────────────────────────────

_session = requests.Session()
_session.trust_env = True  # Utilise le proxy système (Windows)
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


# ──────────────────────────────────────────────────────────────────────
# Scrapers par plateforme (requêtes directes, pas de moteur de recherche)
# ──────────────────────────────────────────────────────────────────────

def _search_indeed(keywords: str, location: str, limit: int = 10) -> list[dict]:
    """Recherche Indeed via flux RSS (le HTML bloque le scraping)."""
    results = []
    try:
        # Le flux RSS d'Indeed n'est pas bloqué contrairement au HTML
        resp = _session.get(
            "https://fr.indeed.com/rss",
            params={"q": keywords, "l": location, "sort": "date"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:limit]:
            title = item.find("title")
            link = item.find("link")
            desc = item.find("description")
            pub_date = item.find("pubDate")

            if not title or not link:
                continue

            snippet = ""
            if desc:
                # Nettoyer le HTML de la description
                desc_soup = BeautifulSoup(desc.get_text(), "html.parser")
                snippet = desc_soup.get_text(strip=True)[:300]
            if pub_date:
                snippet = f"[{pub_date.get_text(strip=True)}] {snippet}"

            results.append({
                "title": title.get_text(strip=True),
                "url": link.get_text(strip=True),
                "snippet": snippet,
                "platform": "indeed",
            })

    except Exception as e:
        print(f"    Indeed RSS : {e}")

    return results


def _search_wttj(keywords: str, location: str, limit: int = 10) -> list[dict]:
    """Recherche WTTJ via leur API Algolia (publique)."""
    results = []

    # Essayer l'API Algolia de WTTJ (endpoint public utilisé par leur frontend)
    try:
        resp = _session.post(
            "https://csekhvms53-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query",
            params={
                "x-algolia-application-id": "CSEKHVMS53",
                "x-algolia-api-key": "YjViMmIxNjkwNjYzNWViNzRkMjRiOGZhYTRlZDBiZjI2MTgyNGQ5MGUyYTljMGIwMTE3ZTgxYjk2ZWVlYjEwYnRhZ0ZpbHRlcnM9",
            },
            json={
                "query": keywords,
                "hitsPerPage": limit,
                "facetFilters": [
                    [f"office.city:{location}"] if location else [],
                ],
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json()
            for hit in data.get("hits", []):
                name = hit.get("name", "")
                org = hit.get("organization", {})
                company = org.get("name", "Inconnue")
                office = hit.get("office", {})
                city = office.get("city", location) if isinstance(office, dict) else location
                contract = hit.get("contract_type", {})
                contract_label = contract.get("fr", str(contract)) if isinstance(contract, dict) else str(contract)
                published = hit.get("published_at", "")

                org_slug = org.get("slug", "") if isinstance(org, dict) else ""
                job_slug = hit.get("slug", hit.get("reference", ""))

                url = f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{job_slug}"

                # Description nettoyée
                desc = hit.get("description", "") or ""
                desc_clean = BeautifulSoup(desc, "html.parser").get_text(strip=True)[:200] if desc else ""

                snippet = f"{company} — {city} — {contract_label}"
                if published:
                    snippet += f" — Publié: {published[:10]}"
                if desc_clean:
                    snippet += f" — {desc_clean}"

                results.append({
                    "title": name,
                    "url": url,
                    "snippet": snippet,
                    "platform": "wttj",
                })

    except Exception as e:
        print(f"    WTTJ Algolia : {e}")
        # Fallback : page HTML
        results = _search_wttj_html(keywords, location, limit)

    # Si Algolia n'a rien retourné, essayer HTML
    if not results:
        results = _search_wttj_html(keywords, location, limit)

    return results


def _search_wttj_html(keywords: str, location: str, limit: int = 10) -> list[dict]:
    """Fallback WTTJ : scrape la page HTML de recherche."""
    results = []
    try:
        resp = _session.get(
            "https://www.welcometothejungle.com/fr/jobs",
            params={"query": keywords, "refinementList[offices.city][]": location},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Chercher les liens vers des offres individuelles
        for link in soup.select("a[href*='/jobs/']"):
            href = link.get("href", "")
            if "/companies/" not in href:
                continue
            if not href.startswith("http"):
                href = "https://www.welcometothejungle.com" + href
            title = link.get_text(strip=True)
            if title and len(title) > 3:
                results.append({
                    "title": title[:100],
                    "url": href,
                    "snippet": "",
                    "platform": "wttj",
                })
                if len(results) >= limit:
                    break

    except Exception as e:
        print(f"    WTTJ HTML : {e}")

    return results


def _search_hellowork(keywords: str, location: str, limit: int = 10) -> list[dict]:
    """Recherche directe sur Hellowork."""
    results = []
    try:
        kw_slug = keywords.replace(" ", "-").lower()
        resp = _session.get(
            f"https://www.hellowork.com/fr-fr/emploi/recherche.html",
            params={"k": keywords, "l": location, "ray": 50},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("li[data-cy='offerItem'], div.offer-card, article"):
            link = card.select_one("a[href*='/emploi/']")
            title_el = card.select_one("h3, h2, [data-cy='offerTitle']")
            if not (link or title_el):
                continue
            href = ""
            if link:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.hellowork.com" + href

            results.append({
                "title": (title_el or link).get_text(strip=True)[:100],
                "url": href,
                "snippet": card.get_text(separator=" — ", strip=True)[:300],
                "platform": "hellowork",
            })
            if len(results) >= limit:
                break

    except Exception as e:
        print(f"    Hellowork : {e}")

    return results


def _search_apec(keywords: str, location: str, limit: int = 10) -> list[dict]:
    """Recherche via l'API APEC."""
    results = []
    try:
        # L'APEC a une API JSON interne
        resp = _session.post(
            "https://api.apec.fr/portail-offre/rest/v1/offres",
            json={
                "motsCles": keywords,
                "lieux": [{"lieu": location}] if location else [],
                "pagination": {"range": f"0-{limit - 1}"},
                "tri": "DATE",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            for offre in data.get("resultats", []):
                results.append({
                    "title": offre.get("intitule", ""),
                    "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{offre.get('numeroOffre', '')}",
                    "snippet": (
                        f"{offre.get('nomCompagnie', '')} — "
                        f"{offre.get('lieux', '')} — "
                        f"{offre.get('typeContrat', '')} — "
                        f"Publié le {offre.get('datePublication', 'inconnu')} — "
                        f"{offre.get('texteHtml', offre.get('description', ''))[:200]}"
                    ),
                    "platform": "apec",
                })
                if len(results) >= limit:
                    break
        else:
            # Fallback HTML
            results = _search_apec_html(keywords, limit)

    except Exception as e:
        print(f"    APEC API : {e}")
        results = _search_apec_html(keywords, limit)

    return results


def _search_apec_html(keywords: str, limit: int = 10) -> list[dict]:
    """Fallback APEC : scrape la page de résultats."""
    results = []
    try:
        resp = _session.get(
            "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
            params={"motsCles": keywords},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("div.card-offer, li.search-result"):
            link = card.select_one("a[href*='detail-offre']")
            title_el = card.select_one("h2, h3, .card-title")
            if not (link or title_el):
                continue
            href = ""
            if link:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.apec.fr" + href

            results.append({
                "title": (title_el or link).get_text(strip=True)[:100],
                "url": href,
                "snippet": card.get_text(separator=" — ", strip=True)[:300],
                "platform": "apec",
            })
            if len(results) >= limit:
                break

    except Exception as e:
        print(f"    APEC HTML : {e}")

    return results


# Map des plateformes vers leurs fonctions de recherche
PLATFORM_SEARCHERS = {
    "indeed": _search_indeed,
    "wttj": _search_wttj,
    "hellowork": _search_hellowork,
    "apec": _search_apec,
}


# ──────────────────────────────────────────────────────────────────────
# Récupération du contenu des pages
# ──────────────────────────────────────────────────────────────────────

def _fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """Récupère le texte principal d'une page web (tronqué)."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Supprimer scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Nettoyer les lignes vides multiples
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────
# Filtrage et scoring par Claude Haiku
# ──────────────────────────────────────────────────────────────────────

FILTER_PROMPT = """\
Tu es un expert en recrutement. On te donne des résultats de recherche web \
d'offres d'emploi et le profil du candidat.

DATE DU JOUR : {today}

PROFIL DU CANDIDAT :
{profile}

---

RÉSULTATS DE RECHERCHE WEB :
{results}

---

INSTRUCTIONS :
1. Pour chaque résultat, détermine s'il s'agit d'une VRAIE offre d'emploi individuelle \
(pas une page de listing générique, pas un article, pas un profil LinkedIn).
2. Vérifie que l'offre semble ENCORE EN LIGNE et RÉCENTE. Indices :
   - Date de publication mentionnée (< 2 mois = OK)
   - Mention "il y a X jours/semaines" = OK
   - Aucune date mais le contenu semble actuel = OK avec réserve
   - Date > 3 mois ou indices d'expiration = EXCLURE
3. Évalue la pertinence pour le profil du candidat (0-100).
4. Extrais les informations structurées.

Réponds UNIQUEMENT en JSON valide, sous cette forme :
{{
  "offres": [
    {{
      "id": "web_1",
      "titre": "Titre du poste",
      "entreprise": "Nom de l'entreprise",
      "localisation": "Ville",
      "type_contrat": "CDI/CDD/VIE/Stage",
      "salaire": "fourchette ou null",
      "competences": ["skill1", "skill2"],
      "url": "URL de l'offre",
      "score": 75,
      "raison": "Explication courte du score",
      "date_estimee": "mars 2026 ou inconnu",
      "encore_en_ligne": true,
      "description_courte": "Résumé de 2-3 phrases"
    }}
  ]
}}

RÈGLES STRICTES :
- N'invente PAS d'offres. Ne retourne que celles trouvées dans les résultats.
- Si un résultat est une page de listing (ex: "50+ offres de Data Analyst"), IGNORE-le.
- Si l'offre semble expirée ou trop ancienne, mets "encore_en_ligne": false.
- Score 0 si l'offre n'a rien à voir avec le profil.
- Sois honnête sur la date : "inconnu" si tu ne peux pas déterminer.
"""


def _get_anthropic_client():
    """Crée un client Anthropic."""
    import anthropic
    return anthropic.Anthropic()


def _build_profile_text(profile: dict) -> str:
    """Résume le profil pour le prompt."""
    skills = ", ".join(profile.get("competences", []))
    return (
        f"Nom : {profile.get('nom', 'N/A')}\n"
        f"Formation : {profile.get('formation', 'N/A')}\n"
        f"Expérience : {profile.get('experience_annees', 0)} ans\n"
        f"Compétences : {skills}\n"
        f"Localisation : {profile.get('localisation', 'N/A')} "
        f"(rayon {profile.get('rayon_km', 30)} km)\n"
        f"Contrats : {', '.join(profile.get('types_contrat', ['CDI']))}\n"
        f"Salaire visé : {profile.get('salaire_min', '?')} - "
        f"{profile.get('salaire_max', '?')} EUR/an\n"
        f"Mots-clés : {profile.get('mots_cles', 'N/A')}"
    )


def _filter_with_haiku(
    profile: dict, search_results: list[dict], batch_size: int = 15
) -> list[dict]:
    """Envoie les résultats à Claude Haiku pour filtrage et scoring.

    Retourne une liste d'offres validées et scorées.
    """
    client = _get_anthropic_client()
    profile_text = _build_profile_text(profile)
    today = datetime.now().strftime("%d/%m/%Y")
    all_offers = []

    for i in range(0, len(search_results), batch_size):
        batch = search_results[i:i + batch_size]

        # Formater les résultats pour le prompt
        results_text = ""
        for j, r in enumerate(batch, 1):
            results_text += f"\n--- RÉSULTAT {j} ---\n"
            results_text += f"Titre : {r['title']}\n"
            results_text += f"URL : {r['url']}\n"
            results_text += f"Extrait : {r['snippet']}\n"
            if r.get("page_content"):
                results_text += f"Contenu de la page :\n{r['page_content']}\n"

        prompt = FILTER_PROMPT.format(
            today=today,
            profile=profile_text,
            results=results_text,
        )

        batch_num = i // batch_size + 1
        total_batches = (len(search_results) + batch_size - 1) // batch_size
        print(f"    Analyse IA des résultats web (lot {batch_num}/{total_batches})...")

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Extraire le JSON
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                offers = data.get("offres", [])
                all_offers.extend(offers)

        except Exception as e:
            print(f"    Erreur analyse IA (lot {batch_num}) : {e}")

    return all_offers


# ──────────────────────────────────────────────────────────────────────
# Fonction principale
# ──────────────────────────────────────────────────────────────────────

def web_search_jobs(
    profile: dict,
    keywords: str | None = None,
    location: str | None = None,
    platforms: list[str] | None = None,
    max_results_per_platform: int = 8,
    fetch_pages: bool = True,
) -> list[dict]:
    """Recherche des offres d'emploi sur le web, filtrées et scorées par Haiku.

    Args:
        profile: Profil du candidat (dict YAML).
        keywords: Mots-clés de recherche (défaut: profil).
        location: Localisation (défaut: profil).
        platforms: Liste de plateformes à chercher (défaut: toutes).
        max_results_per_platform: Nombre de résultats par plateforme.
        fetch_pages: Récupérer le contenu des pages pour plus de contexte.

    Returns:
        Liste de dicts avec les offres filtrées et scorées.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Erreur : ANTHROPIC_API_KEY requise pour la recherche web.")
        print("  Le filtrage IA par Claude Haiku nécessite une clé API Anthropic.")
        return []

    kw = keywords or profile.get("mots_cles", "")
    loc = location or profile.get("localisation", "")

    if not kw:
        print("  Erreur : pas de mots-clés pour la recherche.")
        return []

    if platforms is None:
        platforms = list(PLATFORM_SEARCHERS.keys())

    # Requêter chaque plateforme directement
    all_results = []
    search_terms = [kw]
    # Ajouter des variantes courtes pour élargir
    terms = [t.strip() for t in kw.split() if len(t.strip()) > 2]
    for i in range(0, len(terms), 2):
        group = " ".join(terms[i:i + 2])
        if group != kw and len(group) > 4:
            search_terms.append(group)

    search_terms = search_terms[:3]  # Max 3 variantes

    for platform in platforms:
        searcher = PLATFORM_SEARCHERS.get(platform)
        if not searcher:
            print(f"  Plateforme inconnue : {platform}")
            continue

        for term in search_terms:
            print(f"  {platform}: \"{term}\"...")

            try:
                results = searcher(term, loc, limit=max_results_per_platform)
                for r in results:
                    r["search_term"] = term
                all_results.extend(results)
                if results:
                    print(f"    → {len(results)} résultat(s)")
                else:
                    print(f"    → aucun résultat")
            except Exception as e:
                print(f"    → erreur : {e}")

            time.sleep(0.3)  # Politesse entre requêtes

    # Dédupliquer par URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r["url"].split("?")[0].rstrip("/")  # Normaliser
        if url not in seen_urls and url:
            seen_urls.add(url)
            unique_results.append(r)

    print(f"\n  {len(unique_results)} résultats uniques trouvés sur le web")

    if not unique_results:
        return []

    # Récupérer le contenu des pages (top résultats)
    if fetch_pages:
        print("  Récupération du contenu des offres...")
        fetched = 0
        for r in unique_results[:30]:  # Limiter à 30 pages
            content = _fetch_page_text(r["url"])
            if content:
                r["page_content"] = content
                fetched += 1
            time.sleep(0.3)  # Politesse
        print(f"  {fetched}/{min(len(unique_results), 30)} pages récupérées")

    # Filtrage et scoring par Haiku
    print("\n  Claude Haiku analyse chaque offre (fraîcheur + pertinence)...")
    filtered = _filter_with_haiku(profile, unique_results)

    # Ne garder que les offres encore en ligne et pertinentes
    valid_offers = [
        o for o in filtered
        if o.get("encore_en_ligne", False) and o.get("score", 0) > 20
    ]

    # Trier par score décroissant
    valid_offers.sort(key=lambda o: o.get("score", 0), reverse=True)

    return valid_offers


def offers_to_job_offers(web_offers: list[dict]) -> list[JobOffer]:
    """Convertit les offres web en objets JobOffer pour réutiliser le matching."""
    job_offers = []
    for i, o in enumerate(web_offers):
        offer = JobOffer(
            id=o.get("id", f"web_{i+1}"),
            titre=o.get("titre", "Sans titre"),
            entreprise=o.get("entreprise", "Inconnue"),
            localisation=o.get("localisation", ""),
            description=o.get("description_courte", ""),
            competences_requises=o.get("competences", []),
            type_contrat=o.get("type_contrat", ""),
            url=o.get("url", ""),
            salaire_min=_parse_salary(o.get("salaire"), "min"),
            salaire_max=_parse_salary(o.get("salaire"), "max"),
            raw={
                "score_ia": o.get("score", 0),
                "raison_ia": o.get("raison", ""),
                "date_estimee": o.get("date_estimee", "inconnu"),
                "source": "web",
            },
        )
        job_offers.append(offer)
    return job_offers


def _parse_salary(salaire_str: str | None, which: str = "min") -> float | None:
    """Extrait un salaire min ou max d'une chaîne."""
    if not salaire_str or salaire_str == "null":
        return None
    numbers = re.findall(r"(\d[\d\s]*\d|\d+)", salaire_str.replace(" ", ""))
    nums = [int(n.replace(" ", "")) for n in numbers if n]
    # Si les chiffres semblent mensuels (< 10000), convertir en annuel
    nums = [n * 12 if n < 10000 else n for n in nums]
    if not nums:
        return None
    if which == "min":
        return float(min(nums))
    return float(max(nums))
