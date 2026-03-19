"""Scoring des offres par LLM (Claude) — évaluation intelligente de la pertinence."""

import json
import os
import re

from job_agent.api.base import JobOffer


def _get_client():
    """Crée un client Anthropic."""
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "Le package 'anthropic' est requis pour le scoring IA.\n"
            "Installez-le avec : pip install anthropic"
        )
    return anthropic.Anthropic()


def _build_profile_summary(profile: dict) -> str:
    """Résume le profil candidat pour le prompt."""
    skills = ", ".join(profile.get("competences", []))
    return (
        f"Nom : {profile.get('nom', 'N/A')}\n"
        f"Formation : {profile.get('formation', 'N/A')}\n"
        f"Expérience : {profile.get('experience_annees', 0)} ans\n"
        f"Compétences : {skills}\n"
        f"Localisation souhaitée : {profile.get('localisation', 'N/A')} "
        f"(rayon {profile.get('rayon_km', 30)} km)\n"
        f"Contrats recherchés : {', '.join(profile.get('types_contrat', ['CDI']))}\n"
        f"Salaire visé : {profile.get('salaire_min', '?')} - {profile.get('salaire_max', '?')} EUR/an\n"
        f"Mots-clés métier : {profile.get('mots_cles', 'N/A')}\n"
        f"Langues : {', '.join(profile.get('langues', []))}"
    )


def _build_offer_summary(offer: JobOffer) -> str:
    """Résume une offre pour le prompt."""
    parts = [
        f"Titre : {offer.titre}",
        f"Entreprise : {offer.entreprise}",
        f"Lieu : {offer.localisation}",
        f"Contrat : {offer.type_contrat}",
    ]
    if offer.experience_requise:
        parts.append(f"Expérience : {offer.experience_requise}")
    if offer.formation_requise:
        parts.append(f"Formation : {offer.formation_requise}")
    if offer.salaire_min or offer.salaire_max:
        sal = f"{offer.salaire_min or '?'} - {offer.salaire_max or '?'} EUR"
        parts.append(f"Salaire : {sal}")
    if offer.competences_requises:
        parts.append(f"Compétences demandées : {', '.join(offer.competences_requises)}")
    if offer.teletravail:
        parts.append("Télétravail : Oui")
    # Tronquer la description à 800 caractères pour limiter les tokens
    desc = offer.description[:800] if offer.description else ""
    if desc:
        parts.append(f"Description : {desc}")
    return "\n".join(parts)


SCORING_PROMPT = """\
Tu es un expert en recrutement. Tu dois évaluer la pertinence de chaque offre d'emploi \
pour ce candidat. Sois strict et réaliste.

PROFIL DU CANDIDAT :
{profile}

---

Évalue chaque offre ci-dessous. Pour chaque offre, donne :
- score : un entier de 0 à 100 (pertinence réelle pour CE candidat)
- raison : une phrase courte expliquant le score

Critères de scoring STRICTS :
- 85-100 : Le poste correspond parfaitement au profil (même domaine, compétences alignées, expérience adéquate)
- 70-84 : Bon match avec quelques écarts mineurs
- 50-69 : Match partiel (certains aspects correspondent mais pas le cœur du poste)
- 30-49 : Faible pertinence (domaine adjacent mais pas le bon métier)
- 0-29 : Hors sujet (aucun rapport avec le profil)

ATTENTION aux pièges courants :
- "Business Analyst Crédit/Banque/Assurance" ≠ "Digital Analyst / Web Analyst" → domaines très différents
- "Développeur .Net" n'est PAS un poste data/analytics
- "Executive Assistant" n'a RIEN à voir avec un profil analytics
- "Poseur signalétique", "Responsable boutique" → complètement hors sujet
- Un poste demandant 5-8 ans d'expérience pour un profil à 3 ans → pénaliser
- Alternance/apprentissage peut convenir SI le domaine est pertinent

OFFRES À ÉVALUER :
{offers}

Réponds UNIQUEMENT en JSON, sous la forme d'une liste :
[{{"id": "ID_OFFRE", "score": SCORE, "raison": "EXPLICATION"}}]
"""


def score_offers_with_llm(
    profile: dict,
    offers: list[JobOffer],
    batch_size: int = 20,
) -> dict[str, dict]:
    """Score les offres via Claude API.

    Retourne un dict {offer_id: {"score": int, "raison": str}}.
    Les offres sont envoyées par lots pour optimiser les appels API.
    """
    client = _get_client()
    profile_summary = _build_profile_summary(profile)
    results = {}

    for i in range(0, len(offers), batch_size):
        batch = offers[i:i + batch_size]
        offers_text = ""
        for j, offer in enumerate(batch, 1):
            offers_text += f"\n--- OFFRE {j} (ID: {offer.id}) ---\n"
            offers_text += _build_offer_summary(offer) + "\n"

        prompt = SCORING_PROMPT.format(
            profile=profile_summary,
            offers=offers_text,
        )

        batch_num = i // batch_size + 1
        total_batches = (len(offers) + batch_size - 1) // batch_size
        print(f"    Analyse IA des offres (lot {batch_num}/{total_batches})...")

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Extraire le JSON de la réponse
            parsed = _parse_llm_response(text, batch)
            results.update(parsed)

        except Exception as e:
            print(f"    Erreur scoring IA (lot {batch_num}): {e}")
            # Fallback : ne pas scorer ces offres (elles garderont le score algo)

    return results


def _parse_llm_response(text: str, batch: list[JobOffer]) -> dict[str, dict]:
    """Parse la réponse JSON du LLM."""
    results = {}

    # Trouver le JSON dans la réponse
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not json_match:
        return results

    try:
        items = json.loads(json_match.group())
    except json.JSONDecodeError:
        return results

    for item in items:
        offer_id = str(item.get("id", ""))
        score = item.get("score", 50)
        raison = item.get("raison", "")

        # Valider le score
        score = max(0, min(100, int(score)))

        results[offer_id] = {
            "score": score,
            "raison": raison,
        }

    return results
