"""Recherche d'offres d'emploi sur le web + filtrage IA par Claude Haiku.

Cherche sur Indeed, Welcome to the Jungle, APEC, LinkedIn et autres,
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
# Recherche web multi-moteurs
# ──────────────────────────────────────────────────────────────────────

# Plateformes cibles pour la recherche d'offres
JOB_PLATFORMS = {
    "indeed": "site:indeed.fr",
    "wttj": "site:welcometothejungle.com",
    "apec": "site:apec.fr",
    "linkedin": "site:linkedin.com/jobs",
    "hellowork": "site:hellowork.com",
}

# User-Agent réaliste pour éviter les blocages
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _web_search(query: str, max_results: int = 10) -> list[dict]:
    """Recherche web via plusieurs moteurs (Google HTML > DuckDuckGo HTML > ddgs lib).

    Retourne une liste de dicts: {"title", "url", "snippet"}.
    """
    # Essayer Google d'abord (fonctionne sur la plupart des réseaux d'entreprise)
    results = _google_html_search(query, max_results)
    if results:
        return results

    # Fallback : DuckDuckGo HTML
    results = _duckduckgo_html_search(query, max_results)
    if results:
        return results

    # Dernier recours : librairie ddgs
    results = _ddgs_lib_search(query, max_results)
    return results


def _google_html_search(query: str, max_results: int = 10) -> list[dict]:
    """Recherche via Google HTML (pas de JS nécessaire)."""
    results = []
    try:
        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": max_results, "hl": "fr", "gl": "fr"},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parser les résultats Google
        for g in soup.select("div.g, div[data-sokoban-container]"):
            link = g.select_one("a[href^='http']")
            if not link:
                continue
            url = link.get("href", "")
            # Ignorer les liens Google internes
            if "google.com" in url:
                continue

            title_el = g.select_one("h3")
            snippet_el = (
                g.select_one("div[data-sncf]")
                or g.select_one("div.VwiC3b")
                or g.select_one("span.aCOpRe")
                or g.select_one("div[style='-webkit-line-clamp:2']")
            )
            # Fallback : prendre le texte du bloc entier si pas de snippet
            if not snippet_el:
                snippet_el = g

            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if title and url:
                results.append({"title": title, "url": url, "snippet": snippet[:500]})

            if len(results) >= max_results:
                break

    except Exception as e:
        print(f"    Google : {e}")

    return results


def _duckduckgo_html_search(query: str, max_results: int = 10) -> list[dict]:
    """Recherche via DuckDuckGo HTML (fallback)."""
    results = []
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "fr-fr"},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if title_el:
                url = title_el.get("href", "")
                if "uddg=" in url:
                    url = urllib.parse.unquote(
                        url.split("uddg=")[1].split("&")[0]
                    )
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": url,
                    "snippet": (
                        snippet_el.get_text(strip=True) if snippet_el else ""
                    ),
                })
    except Exception as e:
        print(f"    DuckDuckGo : {e}")

    return results


def _ddgs_lib_search(query: str, max_results: int = 10) -> list[dict]:
    """Recherche via la librairie ddgs/duckduckgo_search (dernier recours)."""
    results = []
    # Essayer le nouveau nom de package d'abord, puis l'ancien
    DDGS = None
    try:
        from ddgs import DDGS as _DDGS
        DDGS = _DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS as _DDGS
            DDGS = _DDGS
        except ImportError:
            pass

    if DDGS is None:
        return results

    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="fr-fr", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        print(f"    ddgs lib : {e}")

    return results


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
        platforms = list(JOB_PLATFORMS.keys())

    # Construire les requêtes de recherche par plateforme
    all_results = []
    search_terms = [kw]
    # Ajouter des variantes courtes
    terms = [t.strip() for t in kw.split() if len(t.strip()) > 2]
    for i in range(0, len(terms), 2):
        group = " ".join(terms[i:i + 2])
        if group != kw and len(group) > 4:
            search_terms.append(group)

    search_terms = search_terms[:3]  # Max 3 variantes

    for platform in platforms:
        site_filter = JOB_PLATFORMS.get(platform, "")
        for term in search_terms:
            query = f"{term} {loc} emploi CDI 2026 {site_filter}".strip()
            print(f"  Recherche sur {platform}: \"{term}\"...")

            results = _web_search(query, max_results=max_results_per_platform)

            for r in results:
                r["platform"] = platform
                r["search_term"] = term

            all_results.extend(results)
            time.sleep(0.5)  # Politesse entre requêtes

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
