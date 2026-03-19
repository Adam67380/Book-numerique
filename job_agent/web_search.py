"""Recherche d'offres d'emploi sur le web via l'API Claude (web_search tool).

La recherche web est effectuée côté serveur Anthropic, ce qui contourne
les restrictions réseau (proxy, firewall) du poste de travail.
Claude Haiku cherche, filtre par date, et score chaque offre.
"""

import json
import os
import re
from datetime import datetime

from job_agent.api.base import JobOffer


# ──────────────────────────────────────────────────────────────────────
# Prompt pour la recherche + analyse par Claude
# ──────────────────────────────────────────────────────────────────────

WEB_SEARCH_PROMPT = """\
Tu es un agent de recherche d'emploi. Tu dois chercher des offres d'emploi \
RÉELLES et RÉCENTES pour ce candidat.

DATE DU JOUR : {today}

PROFIL DU CANDIDAT :
{profile}

CONSIGNES :
1. Utilise l'outil web_search pour chercher des offres d'emploi sur ces plateformes :
   - Indeed.fr
   - Welcome to the Jungle (welcometothejungle.com)
   - APEC (apec.fr)
   - LinkedIn Jobs
   - Hellowork

2. Fais PLUSIEURS recherches avec des mots-clés variés :
{search_queries}

3. Pour chaque offre trouvée, vérifie qu'elle est RÉCENTE (< 2 mois).

4. Une fois toutes les recherches effectuées, retourne un JSON avec les offres \
pertinentes trouvées. Format STRICT :

```json
{{
  "offres": [
    {{
      "id": "web_1",
      "titre": "Titre exact du poste",
      "entreprise": "Nom de l'entreprise",
      "localisation": "Ville",
      "type_contrat": "CDI/CDD/VIE",
      "salaire": "fourchette salariale ou null",
      "competences": ["skill1", "skill2"],
      "url": "URL directe vers l'offre",
      "score": 75,
      "raison": "Pourquoi cette offre match le profil",
      "date_estimee": "mars 2026",
      "encore_en_ligne": true,
      "description_courte": "Résumé en 2-3 phrases"
    }}
  ]
}}
```

RÈGLES STRICTES :
- Ne retourne QUE des offres réelles trouvées via la recherche web.
- N'INVENTE aucune offre.
- EXCLUE les offres expirées (> 2 mois).
- EXCLUE les pages de listing génériques (ex: "500 offres de Data Analyst").
- Score de pertinence strict :
  - 85-100 : Parfait match (même domaine, compétences alignées)
  - 70-84 : Bon match avec écarts mineurs
  - 50-69 : Match partiel
  - 30-49 : Faible pertinence
  - 0-29 : Hors sujet
- "Business Analyst Banque" ≠ "Digital Analyst" → domaines différents
- Un poste demandant 5+ ans pour un profil à {experience} ans → pénaliser
"""


def _get_client():
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


def _build_search_queries(keywords: str, location: str) -> str:
    """Construit les suggestions de recherche pour le prompt."""
    terms = [t.strip() for t in keywords.split() if len(t.strip()) > 2]
    queries = [
        f'   - "{keywords}" emploi {location} CDI 2026',
    ]
    # Sous-groupes de 2 mots
    for i in range(0, len(terms), 2):
        group = " ".join(terms[i:i + 2])
        if group != keywords:
            queries.append(f'   - "{group}" emploi {location}')
    # Termes importants seuls
    for term in terms:
        if len(term) >= 5:
            queries.append(f'   - "{term}" offre emploi {location}')

    return "\n".join(queries[:6])


def _extract_json_from_response(messages: list) -> list[dict]:
    """Extrait le JSON final de la conversation avec Claude."""
    # Parcourir les messages de la fin vers le début
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            text = content
        else:
            # Chercher les blocs texte
            text = ""
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")

        # Chercher le JSON dans le texte
        json_match = re.search(r"\{[\s\S]*\"offres\"[\s\S]*\}", text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("offres", [])
            except json.JSONDecodeError:
                continue

    return []


def web_search_jobs(
    profile: dict,
    keywords: str | None = None,
    location: str | None = None,
    platforms: list[str] | None = None,
    max_results_per_platform: int = 8,
    fetch_pages: bool = True,
) -> list[dict]:
    """Recherche d'offres via Claude web_search (côté serveur Anthropic).

    La recherche web est effectuée par les serveurs Anthropic,
    pas depuis le poste local — contourne les restrictions réseau.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Erreur : ANTHROPIC_API_KEY requise pour la recherche web.")
        return []

    kw = keywords or profile.get("mots_cles", "")
    loc = location or profile.get("localisation", "")

    if not kw:
        print("  Erreur : pas de mots-clés pour la recherche.")
        return []

    client = _get_client()
    profile_text = _build_profile_text(profile)
    today = datetime.now().strftime("%d/%m/%Y")
    search_queries = _build_search_queries(kw, loc)
    experience = profile.get("experience_annees", 0)

    prompt = WEB_SEARCH_PROMPT.format(
        today=today,
        profile=profile_text,
        search_queries=search_queries,
        experience=experience,
    )

    print("  Claude recherche des offres sur le web (côté serveur Anthropic)...")
    print(f"  Mots-clés : {kw}")
    print(f"  Localisation : {loc}")
    print()

    try:
        # Appel avec l'outil web_search intégré à l'API Claude
        # La recherche se fait côté Anthropic (pas bloqué par le proxy)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16000,
            tools=[{"type": "web_search_20250305"}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Gérer la boucle agentic (Claude peut faire plusieurs recherches)
        messages = [{"role": "user", "content": prompt}]
        search_count = 0

        while response.stop_reason == "tool_use":
            # Compter les recherches web
            for block in response.content:
                if hasattr(block, "type") and block.type == "server_tool_use":
                    search_count += 1
                    if hasattr(block, "input") and isinstance(block.input, dict):
                        query = block.input.get("query", "")
                        print(f"    Recherche {search_count}: \"{query}\"")

            # Ajouter la réponse assistant
            messages.append({
                "role": "assistant",
                "content": [_block_to_dict(b) for b in response.content],
            })

            # Construire les résultats des outils
            tool_results = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "web_search_tool_result":
                    tool_results.append(_block_to_dict(block))

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Continuer la conversation
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=16000,
                tools=[{"type": "web_search_20250305"}],
                messages=messages,
            )

        # Extraire le texte final
        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        print(f"\n  {search_count} recherche(s) web effectuée(s)")

        # Parser le JSON des offres
        json_match = re.search(r"\{[\s\S]*\"offres\"[\s\S]*\}", final_text)
        if not json_match:
            print("  Pas d'offres structurées trouvées dans la réponse.")
            print(f"  Réponse brute :\n{final_text[:500]}")
            return []

        data = json.loads(json_match.group())
        offers = data.get("offres", [])

        # Filtrer : encore en ligne + score > 20
        valid = [
            o for o in offers
            if o.get("encore_en_ligne", False) and o.get("score", 0) > 20
        ]
        valid.sort(key=lambda o: o.get("score", 0), reverse=True)

        print(f"  {len(valid)} offre(s) pertinente(s) et récente(s) trouvée(s)")
        return valid

    except Exception as e:
        print(f"  Erreur recherche web : {e}")
        return []


def _block_to_dict(block) -> dict:
    """Convertit un bloc de réponse Anthropic en dict sérialisable."""
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if hasattr(block, "to_dict"):
        return block.to_dict()
    # Fallback manuel
    d = {"type": getattr(block, "type", "unknown")}
    if hasattr(block, "text"):
        d["text"] = block.text
    if hasattr(block, "id"):
        d["id"] = block.id
    if hasattr(block, "name"):
        d["name"] = block.name
    if hasattr(block, "input"):
        d["input"] = block.input
    if hasattr(block, "content"):
        if isinstance(block.content, list):
            d["content"] = [_block_to_dict(b) if hasattr(b, "type") else b for b in block.content]
        else:
            d["content"] = block.content
    return d


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
    numbers = re.findall(r"(\d[\d\s]*\d|\d+)", str(salaire_str).replace(" ", ""))
    nums = [int(n.replace(" ", "")) for n in numbers if n]
    nums = [n * 12 if n < 10000 else n for n in nums]
    if not nums:
        return None
    if which == "min":
        return float(min(nums))
    return float(max(nums))
