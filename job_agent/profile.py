"""Gestion du profil candidat (chargement, validation, création interactive)."""

import os
import yaml

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yaml")

EDUCATION_LEVELS = {
    "bac": 1,
    "bac+2": 2,
    "bac+3": 3,
    "licence": 3,
    "master": 4,
    "bac+5": 4,
    "doctorat": 5,
    "phd": 5,
}


def load_profile(path: str = None) -> dict:
    """Charge le profil depuis un fichier YAML."""
    path = path or PROFILE_PATH
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Profil introuvable : {path}\n"
            "Lancez 'python -m job_agent init-profile' pour en créer un."
        )
    with open(path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    errors = validate_profile(profile)
    if errors:
        raise ValueError("Profil invalide :\n" + "\n".join(f"  - {e}" for e in errors))
    return normalize_profile(profile)


def validate_profile(profile: dict) -> list[str]:
    """Valide le profil et retourne la liste des erreurs."""
    errors = []
    if not profile:
        return ["Le fichier profil est vide."]

    required = ["nom", "competences", "experience_annees", "formation"]
    for field in required:
        if field not in profile or not profile[field]:
            errors.append(f"Champ obligatoire manquant : '{field}'")

    if "competences" in profile and not isinstance(profile["competences"], list):
        errors.append("'competences' doit être une liste.")

    if "experience_annees" in profile:
        try:
            int(profile["experience_annees"])
        except (ValueError, TypeError):
            errors.append("'experience_annees' doit être un nombre entier.")

    if "formation" in profile:
        formation = str(profile["formation"]).lower().strip()
        if formation not in EDUCATION_LEVELS:
            errors.append(
                f"'formation' invalide : '{profile['formation']}'. "
                f"Valeurs possibles : {', '.join(EDUCATION_LEVELS.keys())}"
            )
    return errors


def normalize_profile(profile: dict) -> dict:
    """Normalise les données du profil."""
    profile["competences"] = [s.lower().strip() for s in profile.get("competences", [])]
    profile["formation_niveau"] = EDUCATION_LEVELS.get(
        str(profile.get("formation", "")).lower().strip(), 0
    )
    profile["experience_annees"] = int(profile.get("experience_annees", 0))
    profile["langues"] = [l.lower().strip() for l in profile.get("langues", [])]
    profile["types_contrat"] = [c.upper().strip() for c in profile.get("types_contrat", ["CDI"])]
    profile["localisation"] = profile.get("localisation", "")
    profile["rayon_km"] = int(profile.get("rayon_km", 30))
    profile["salaire_min"] = profile.get("salaire_min")
    profile["salaire_max"] = profile.get("salaire_max")
    profile["mots_cles"] = profile.get("mots_cles", "")
    return profile


def create_profile_interactive(output_path: str = None):
    """Assistant interactif pour créer un profil."""
    output_path = output_path or PROFILE_PATH
    print("\n=== Création de votre profil candidat ===\n")

    nom = input("Votre nom complet : ").strip()
    competences_raw = input("Vos compétences (séparées par des virgules) : ").strip()
    competences = [s.strip() for s in competences_raw.split(",") if s.strip()]
    experience = input("Années d'expérience : ").strip()
    formation = input("Niveau d'études (bac, bac+2, bac+3, master, doctorat) : ").strip()
    langues_raw = input("Langues parlées (séparées par des virgules) : ").strip()
    langues = [l.strip() for l in langues_raw.split(",") if l.strip()]
    localisation = input("Ville/département souhaité : ").strip()
    rayon = input("Rayon de recherche en km (défaut: 30) : ").strip() or "30"
    salaire_min = input("Salaire minimum annuel brut en EUR (optionnel) : ").strip()
    salaire_max = input("Salaire maximum annuel brut en EUR (optionnel) : ").strip()
    contrats_raw = input("Types de contrat (CDI, CDD, interim, freelance - séparés par virgules) : ").strip()
    contrats = [c.strip() for c in contrats_raw.split(",") if c.strip()] or ["CDI"]
    mots_cles = input("Mots-clés pour la recherche d'offres : ").strip()

    profile = {
        "nom": nom,
        "competences": competences,
        "experience_annees": int(experience) if experience.isdigit() else 0,
        "formation": formation.lower(),
        "langues": langues,
        "localisation": localisation,
        "rayon_km": int(rayon) if rayon.isdigit() else 30,
        "salaire_min": int(salaire_min) if salaire_min.isdigit() else None,
        "salaire_max": int(salaire_max) if salaire_max.isdigit() else None,
        "types_contrat": contrats,
        "mots_cles": mots_cles,
        "api": {
            "france_travail": {
                "client_id": "",
                "client_secret": "",
            }
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\nProfil sauvegardé dans : {output_path}")
    print("N'oubliez pas d'ajouter vos clés API France Travail dans le fichier.")
    return profile
