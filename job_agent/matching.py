"""Algorithme de matching entre profil candidat et offres d'emploi."""

import difflib
import re
import unicodedata

from job_agent.api.base import JobOffer
from job_agent.profile import EDUCATION_LEVELS

# Synonymes courants pour améliorer le matching
SKILL_SYNONYMS = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "ml": "machine learning",
    "ia": "intelligence artificielle",
    "ai": "intelligence artificielle",
    "bi": "business intelligence",
    "power bi": "business intelligence",
    "ga4": "google analytics 4",
    "ga": "google analytics",
    "gtm": "google tag manager",
    "ux": "expérience utilisateur",
    "ui": "interface utilisateur",
    "seo": "référencement naturel",
    "sea": "référencement payant",
    "sql": "sql",
    "bdd": "base de données",
    "crm": "gestion relation client",
    "cms": "content management system",
    "ci/cd": "intégration continue",
    "devops": "devops",
    "ab test": "ab testing",
    "test a/b": "ab testing",
}

# Poids de chaque composante du score (total = 100)
WEIGHTS = {
    "competences": 40,
    "localisation": 15,
    "experience": 15,
    "formation": 10,
    "salaire": 10,
    "contrat": 10,
}


def normalize_text(text: str) -> str:
    """Normalise un texte : minuscules, sans accents, sans ponctuation."""
    text = text.lower().strip()
    # Retirer les accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Garder uniquement lettres, chiffres et espaces
    text = re.sub(r"[^a-z0-9\s+/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_synonyms(skill: str) -> set[str]:
    """Retourne un ensemble contenant le skill et ses synonymes."""
    normalized = normalize_text(skill)
    result = {normalized}
    for key, value in SKILL_SYNONYMS.items():
        norm_key = normalize_text(key)
        norm_value = normalize_text(value)
        if normalized == norm_key or normalized == norm_value:
            result.add(norm_key)
            result.add(norm_value)
    return result


def skill_matches(profile_skill: str, offer_skill: str) -> bool:
    """Vérifie si une compétence du profil correspond à une de l'offre."""
    ps = normalize_text(profile_skill)
    os_norm = normalize_text(offer_skill)

    # Correspondance exacte
    if ps == os_norm:
        return True

    # Inclusion (substring)
    if ps in os_norm or os_norm in ps:
        return True

    # Vérifier les synonymes
    ps_variants = expand_synonyms(profile_skill)
    os_variants = expand_synonyms(offer_skill)
    if ps_variants & os_variants:
        return True

    # Similarité avec difflib (seuil 0.8)
    ratio = difflib.SequenceMatcher(None, ps, os_norm).ratio()
    if ratio >= 0.8:
        return True

    return False


def score_competences(profile: dict, offer: JobOffer) -> tuple[float, list[str], list[str]]:
    """Score de matching des compétences. Retourne (score, matched, gaps)."""
    if not offer.competences_requises:
        return 1.0, [], []

    profile_skills = profile.get("competences", [])
    matched = []
    gaps = []

    for req_skill in offer.competences_requises:
        found = False
        for p_skill in profile_skills:
            if skill_matches(p_skill, req_skill):
                matched.append(req_skill)
                found = True
                break
        if not found:
            # Vérifier aussi dans la description
            gaps.append(req_skill)

    total = len(offer.competences_requises)
    score = len(matched) / total if total > 0 else 1.0
    return score, matched, gaps


def score_localisation(profile: dict, offer: JobOffer) -> float:
    """Score de correspondance géographique."""
    if offer.teletravail:
        return 1.0

    desired = normalize_text(profile.get("localisation", ""))
    offer_loc = normalize_text(offer.localisation)

    if not desired or not offer_loc:
        return 0.7  # Neutre si pas d'info

    if desired in offer_loc or offer_loc in desired:
        return 1.0

    # Vérifier le département (2 premiers chiffres du code postal)
    return 0.3  # Localisation différente


def parse_experience_years(text: str) -> int | None:
    """Extrait le nombre d'années d'expérience d'un texte."""
    text = text.lower()
    if any(kw in text for kw in ["débutant", "debutant", "junior", "sans expérience"]):
        return 0

    match = re.search(r"(\d+)\s*(?:an|année|ans)", text)
    if match:
        return int(match.group(1))
    return None


def score_experience(profile: dict, offer: JobOffer) -> tuple[float, str]:
    """Score d'adéquation de l'expérience."""
    profile_years = profile.get("experience_annees", 0)
    required = parse_experience_years(offer.experience_requise)

    if required is None:
        return 0.8, ""  # Pas d'info

    if profile_years >= required:
        return 1.0, ""

    gap = required - profile_years
    ratio = profile_years / required if required > 0 else 1.0
    tip = f"L'offre demande {required} ans d'expérience (vous en avez {profile_years})"
    return max(ratio, 0.2), tip


def score_formation(profile: dict, offer: JobOffer) -> tuple[float, str]:
    """Score d'adéquation du niveau de formation."""
    profile_level = profile.get("formation_niveau", 0)

    if not offer.formation_requise:
        return 0.8, ""

    # Chercher le niveau dans le texte de l'offre
    offer_text = offer.formation_requise.lower()
    offer_level = 0
    for name, level in EDUCATION_LEVELS.items():
        if name in offer_text:
            offer_level = max(offer_level, level)

    if offer_level == 0:
        return 0.8, ""

    if profile_level >= offer_level:
        return 1.0, ""

    tip = f"Formation requise : {offer.formation_requise} (vous avez un niveau {profile.get('formation', 'non précisé')})"
    return max(profile_level / offer_level, 0.3), tip


def score_salaire(profile: dict, offer: JobOffer) -> float:
    """Score de correspondance salariale."""
    p_min = profile.get("salaire_min")
    p_max = profile.get("salaire_max")
    o_min = offer.salaire_min
    o_max = offer.salaire_max

    if not o_min and not o_max:
        return 0.7  # Pas d'info salaire

    if not p_min and not p_max:
        return 0.7

    # Vérifier le chevauchement des fourchettes
    p_min = p_min or 0
    p_max = p_max or float("inf")
    o_min = o_min or 0
    o_max = o_max or float("inf")

    if o_max >= p_min and o_min <= p_max:
        return 1.0  # Chevauchement
    elif o_max < p_min:
        # Offre en dessous des attentes
        ratio = o_max / p_min if p_min > 0 else 0
        return max(ratio, 0.2)
    else:
        return 0.8  # Offre au-dessus (c'est positif)


def score_contrat(profile: dict, offer: JobOffer) -> float:
    """Score de correspondance du type de contrat."""
    desired = [c.upper() for c in profile.get("types_contrat", [])]
    if not desired or not offer.type_contrat:
        return 0.7

    if offer.type_contrat.upper() in desired:
        return 1.0
    return 0.1


def compute_match(profile: dict, offer: JobOffer) -> dict:
    """Calcule le score de matching global entre un profil et une offre.

    Retourne un dict avec :
        - score: float (0-100)
        - details: dict des scores par composante
        - gaps: liste des lacunes identifiées
        - matched_skills: compétences matchées
        - tips: conseils liés aux écarts
    """
    # Compétences
    comp_score, matched_skills, skill_gaps = score_competences(profile, offer)

    # Localisation
    loc_score = score_localisation(profile, offer)

    # Expérience
    exp_score, exp_tip = score_experience(profile, offer)

    # Formation
    edu_score, edu_tip = score_formation(profile, offer)

    # Salaire
    sal_score = score_salaire(profile, offer)

    # Contrat
    con_score = score_contrat(profile, offer)

    # Score pondéré
    weighted = (
        comp_score * WEIGHTS["competences"]
        + loc_score * WEIGHTS["localisation"]
        + exp_score * WEIGHTS["experience"]
        + edu_score * WEIGHTS["formation"]
        + sal_score * WEIGHTS["salaire"]
        + con_score * WEIGHTS["contrat"]
    )

    # Construire les tips
    tips = []
    if skill_gaps:
        tips.append(f"Compétences manquantes : {', '.join(skill_gaps)}")
    if exp_tip:
        tips.append(exp_tip)
    if edu_tip:
        tips.append(edu_tip)

    return {
        "score": round(weighted, 1),
        "details": {
            "competences": round(comp_score * 100, 1),
            "localisation": round(loc_score * 100, 1),
            "experience": round(exp_score * 100, 1),
            "formation": round(edu_score * 100, 1),
            "salaire": round(sal_score * 100, 1),
            "contrat": round(con_score * 100, 1),
        },
        "matched_skills": matched_skills,
        "skill_gaps": skill_gaps,
        "tips": tips,
    }
