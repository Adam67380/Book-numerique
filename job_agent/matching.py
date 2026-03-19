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
    "titre": 25,
    "competences": 30,
    "localisation": 15,
    "experience": 10,
    "formation": 5,
    "salaire": 5,
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


def score_titre(profile: dict, offer: JobOffer) -> float:
    """Score de pertinence du titre de l'offre par rapport au profil.

    Compare le titre de l'offre avec les mots-clés du profil pour
    filtrer les postes hors-sujet (ex: Directeur, Poseur signalétique).
    Utilise des correspondances au niveau des mots entiers pour éviter
    les faux positifs par sous-chaînes.
    """
    titre_norm = normalize_text(offer.titre)
    if not titre_norm:
        return 0.2

    titre_words = set(titre_norm.split())

    # Construire la liste de mots-clés pertinents depuis le profil
    mots_cles_raw = profile.get("mots_cles", "")
    keywords = set()
    if mots_cles_raw:
        for mot in mots_cles_raw.lower().split():
            mot = mot.strip()
            if len(mot) >= 3:  # Ignorer les mots trop courts (ux, bi)
                keywords.add(normalize_text(mot))

    # Ajouter les compétences clés du profil (celles >= 4 caractères)
    # pour éviter les faux positifs avec des abréviations courtes
    for skill in profile.get("competences", []):
        norm = normalize_text(skill)
        if len(norm) >= 4:
            keywords.add(norm)

    if not keywords:
        return 0.3

    # Compter combien de mots-clés apparaissent dans le titre
    # en utilisant des correspondances au niveau des mots entiers
    matches = 0
    for kw in keywords:
        # Vérifier si le mot-clé correspond à un ou plusieurs mots du titre
        if _is_word_boundary_match(kw, titre_norm):
            matches += 1
        else:
            # Vérifier aussi via synonymes
            kw_variants = expand_synonyms(kw)
            for variant in kw_variants:
                if _is_word_boundary_match(variant, titre_norm):
                    matches += 1
                    break

    if matches == 0:
        # Aucun mot-clé dans le titre → probablement hors-sujet
        return 0.1

    # Score progressif plus exigeant
    if matches >= 4:
        return 1.0
    elif matches >= 3:
        return 0.85
    elif matches == 2:
        return 0.7
    else:
        return 0.45  # 1 seul match = faible confiance


def _is_word_boundary_match(needle: str, haystack: str) -> bool:
    """Vérifie qu'une sous-chaîne correspond à des mots entiers dans le texte."""
    pattern = r"(?:^|\s)" + re.escape(needle) + r"(?:\s|$)"
    return bool(re.search(pattern, haystack))


def skill_matches(profile_skill: str, offer_skill: str) -> bool:
    """Vérifie si une compétence du profil correspond à une de l'offre."""
    ps = normalize_text(profile_skill)
    os_norm = normalize_text(offer_skill)

    if not ps or not os_norm:
        return False

    # Correspondance exacte
    if ps == os_norm:
        return True

    # Vérifier les synonymes (avant substring pour être plus précis)
    ps_variants = expand_synonyms(profile_skill)
    os_variants = expand_synonyms(offer_skill)
    if ps_variants & os_variants:
        return True

    # Inclusion (substring) — seulement si le mot court fait >= 4 caractères
    # et correspond à des mots entiers (pas juste une sous-chaîne de caractères)
    shorter = ps if len(ps) <= len(os_norm) else os_norm
    longer = os_norm if len(ps) <= len(os_norm) else ps
    if len(shorter) >= 4 and _is_word_boundary_match(shorter, longer):
        return True

    # Similarité avec difflib — seuil plus strict pour les mots courts
    min_len = min(len(ps), len(os_norm))
    threshold = 0.85 if min_len >= 8 else 0.92
    ratio = difflib.SequenceMatcher(None, ps, os_norm).ratio()
    if ratio >= threshold:
        return True

    return False


def score_competences(profile: dict, offer: JobOffer) -> tuple[float, list[str], list[str]]:
    """Score de matching des compétences. Retourne (score, matched, gaps)."""
    if not offer.competences_requises:
        return 0.3, [], []  # Pas d'info → score faible (on ne peut pas valider)

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
        return 0.3  # Pas d'info → score faible

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

    # Si le champ structuré ne donne rien, chercher dans la description
    if required is None and offer.description:
        required = parse_experience_years(offer.description)

    if required is None:
        return 0.3, ""  # Pas d'info → score faible

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
        return 0.3, ""  # Pas d'info → score faible

    # Chercher le niveau dans le texte de l'offre
    offer_text = offer.formation_requise.lower()
    offer_level = 0
    for name, level in EDUCATION_LEVELS.items():
        if name in offer_text:
            offer_level = max(offer_level, level)

    if offer_level == 0:
        return 0.3, ""

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
        return 0.3  # Pas d'info salaire → score faible

    if not p_min and not p_max:
        return 0.3

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
        return 0.3

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
    # Pertinence du titre
    tit_score = score_titre(profile, offer)

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
        tit_score * WEIGHTS["titre"]
        + comp_score * WEIGHTS["competences"]
        + loc_score * WEIGHTS["localisation"]
        + exp_score * WEIGHTS["experience"]
        + edu_score * WEIGHTS["formation"]
        + sal_score * WEIGHTS["salaire"]
        + con_score * WEIGHTS["contrat"]
    )

    # Construire les tips
    tips = []
    if tit_score < 0.5:
        tips.append("⚠ Le titre du poste ne correspond pas bien à votre profil")
    if skill_gaps:
        tips.append(f"Compétences manquantes : {', '.join(skill_gaps)}")
    if exp_tip:
        tips.append(exp_tip)
    if edu_tip:
        tips.append(edu_tip)

    return {
        "score": round(weighted, 1),
        "details": {
            "titre": round(tit_score * 100, 1),
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
