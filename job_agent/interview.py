"""Générateur de conseils d'entretien basé sur l'analyse des écarts profil/offre."""

from job_agent.api.base import JobOffer

# Base de connaissances pour les compétences courantes
SKILL_ADVICE = {
    "python": {
        "description": "Langage de programmation polyvalent, très demandé en data/IA",
        "ressources": "Cours officiel Python, DataCamp, Codecademy",
        "adjacent": ["sql", "pandas", "numpy", "r"],
    },
    "sql": {
        "description": "Langage de requête pour bases de données",
        "ressources": "SQLZoo, Mode Analytics SQL Tutorial",
        "adjacent": ["python", "power bi", "excel"],
    },
    "power bi": {
        "description": "Outil Microsoft de visualisation et reporting",
        "ressources": "Microsoft Learn, Guy in a Cube (YouTube)",
        "adjacent": ["excel", "tableau", "data visualization", "sql"],
    },
    "tableau": {
        "description": "Plateforme de data visualization",
        "ressources": "Tableau Public, Tableau eLearning",
        "adjacent": ["power bi", "data visualization", "sql"],
    },
    "google analytics": {
        "description": "Outil de web analytics de Google",
        "ressources": "Google Skillshop, certification GA4 gratuite",
        "adjacent": ["ga4", "gtm", "contentsquare", "web analytics"],
    },
    "contentsquare": {
        "description": "Plateforme d'analyse d'expérience digitale",
        "ressources": "ContentSquare Academy, certifications officielles",
        "adjacent": ["ga4", "ux", "web analytics", "hotjar"],
    },
    "javascript": {
        "description": "Langage de programmation web front-end et back-end",
        "ressources": "MDN Web Docs, freeCodeCamp",
        "adjacent": ["html", "css", "react", "typescript"],
    },
    "docker": {
        "description": "Plateforme de conteneurisation d'applications",
        "ressources": "Docker Documentation, Play with Docker",
        "adjacent": ["kubernetes", "devops", "ci/cd"],
    },
    "agile": {
        "description": "Méthodologie de gestion de projet itérative",
        "ressources": "Scrum Guide (gratuit), Scrum.org",
        "adjacent": ["scrum", "kanban", "jira", "gestion de projet"],
    },
    "machine learning": {
        "description": "Apprentissage automatique et IA",
        "ressources": "Andrew Ng (Coursera), fast.ai",
        "adjacent": ["python", "data science", "deep learning", "tensorflow"],
    },
    "excel": {
        "description": "Tableur Microsoft pour l'analyse de données",
        "ressources": "ExcelJet, Chandoo.org",
        "adjacent": ["power bi", "sql", "vba"],
    },
}

# Questions comportementales par catégorie de poste
BEHAVIORAL_QUESTIONS = {
    "analytics": [
        "Décrivez un projet où vos analyses ont directement influencé une décision business.",
        "Comment priorisez-vous vos analyses quand vous avez plusieurs demandes ?",
        "Racontez une situation où vos données contredisaient l'intuition de l'équipe.",
    ],
    "marketing": [
        "Comment mesurez-vous le ROI d'une campagne marketing ?",
        "Décrivez une campagne que vous avez optimisée grâce aux données.",
        "Comment communiquez-vous des résultats complexes à des non-techniques ?",
    ],
    "tech": [
        "Décrivez un problème technique complexe que vous avez résolu.",
        "Comment gérez-vous les deadlines serrées sur un projet technique ?",
        "Parlez d'un projet où vous avez dû apprendre une nouvelle technologie rapidement.",
    ],
    "management": [
        "Comment gérez-vous les conflits au sein d'une équipe ?",
        "Décrivez votre expérience avec la méthodologie Agile.",
        "Comment priorisez-vous les tâches dans un projet complexe ?",
    ],
    "default": [
        "Parlez-moi d'un défi professionnel que vous avez surmonté.",
        "Qu'est-ce qui vous motive dans ce type de poste ?",
        "Comment vous tenez-vous informé des évolutions de votre domaine ?",
    ],
}


def detect_job_category(offer: JobOffer) -> str:
    """Détecte la catégorie d'un poste pour adapter les conseils."""
    text = (offer.titre + " " + offer.description).lower()

    categories = {
        "analytics": ["analytics", "analyst", "données", "data", "bi", "reporting"],
        "marketing": ["marketing", "acquisition", "seo", "sea", "campagne", "ads"],
        "tech": ["développeur", "developer", "devops", "ingénieur", "tech lead"],
        "management": ["manager", "chef de projet", "product owner", "directeur"],
    }

    scores = {}
    for cat, keywords in categories.items():
        scores[cat] = sum(1 for kw in keywords if kw in text)

    if not any(scores.values()):
        return "default"
    return max(scores, key=scores.get)


def generate_tips(profile: dict, offer: JobOffer, match_details: dict) -> str:
    """Génère des conseils d'entretien personnalisés."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  PRÉPARATION ENTRETIEN : {offer.titre}")
    lines.append(f"  {offer.entreprise}")
    lines.append("=" * 60)
    lines.append("")

    score = match_details["score"]
    lines.append(f"  Score de compatibilité : {score}%")
    lines.append("")

    # 1. Compétences manquantes
    skill_gaps = match_details.get("skill_gaps", [])
    if skill_gaps:
        lines.append("─" * 60)
        lines.append("  COMPÉTENCES À RENFORCER")
        lines.append("─" * 60)
        for gap in skill_gaps:
            lines.append(f"\n  ▸ {gap.capitalize()}")
            # Chercher des conseils spécifiques
            advice = _find_skill_advice(gap)
            if advice:
                lines.append(f"    → {advice['description']}")
                lines.append(f"    📚 Ressources : {advice['ressources']}")
                # Compétences adjacentes du profil
                profile_skills = profile.get("competences", [])
                adjacent_match = [
                    s for s in advice.get("adjacent", [])
                    if any(s.lower() in ps.lower() or ps.lower() in s.lower()
                           for ps in profile_skills)
                ]
                if adjacent_match:
                    lines.append(
                        f"    💡 En entretien, valorisez vos compétences en : "
                        f"{', '.join(adjacent_match)}"
                    )
            else:
                lines.append(f"    💡 Mentionnez votre capacité d'apprentissage rapide")
                lines.append(f"       et votre curiosité technologique")
        lines.append("")

    # 2. Points forts à mettre en avant
    matched = match_details.get("matched_skills", [])
    if matched:
        lines.append("─" * 60)
        lines.append("  VOS POINTS FORTS POUR CE POSTE")
        lines.append("─" * 60)
        lines.append(f"  ✓ Compétences matchées : {', '.join(matched)}")
        lines.append("  → Préparez des exemples concrets pour chacune (méthode STAR)")
        lines.append("")

    # 3. Analyse des écarts
    tips = match_details.get("tips", [])
    other_tips = [t for t in tips if "compétences manquantes" not in t.lower()]
    if other_tips:
        lines.append("─" * 60)
        lines.append("  POINTS D'ATTENTION")
        lines.append("─" * 60)
        for tip in other_tips:
            lines.append(f"  ⚠ {tip}")
        lines.append("")

    # 4. Questions comportementales
    category = detect_job_category(offer)
    questions = BEHAVIORAL_QUESTIONS.get(category, BEHAVIORAL_QUESTIONS["default"])
    lines.append("─" * 60)
    lines.append("  QUESTIONS D'ENTRETIEN PROBABLES")
    lines.append("─" * 60)
    for i, q in enumerate(questions, 1):
        lines.append(f"  {i}. {q}")
    lines.append("")

    # 5. Conseils généraux
    lines.append("─" * 60)
    lines.append("  CONSEILS GÉNÉRAUX")
    lines.append("─" * 60)
    lines.append(f"  1. Renseignez-vous sur {offer.entreprise} : actualités, valeurs, produits")
    lines.append(f"  2. Préparez vos réponses avec la méthode STAR :")
    lines.append(f"     Situation → Tâche → Action → Résultat")
    lines.append(f"  3. Préparez 2-3 questions à poser au recruteur")

    if score < 60:
        lines.append(f"  4. Score < 60% : misez sur votre motivation et votre capacité")
        lines.append(f"     d'apprentissage. Montrez des projets personnels ou formations en cours.")
    elif score < 80:
        lines.append(f"  4. Score 60-80% : bon profil ! Comblez les petits écarts avec des")
        lines.append(f"     exemples de montée en compétence rapide dans vos postes précédents.")
    else:
        lines.append(f"  4. Score > 80% : excellent match ! Concentrez-vous sur votre valeur")
        lines.append(f"     ajoutée unique et ce que vous apporteriez de plus à l'équipe.")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def _find_skill_advice(skill: str) -> dict | None:
    """Cherche des conseils pour une compétence donnée."""
    skill_lower = skill.lower().strip()
    # Correspondance exacte
    if skill_lower in SKILL_ADVICE:
        return SKILL_ADVICE[skill_lower]
    # Correspondance partielle
    for key, advice in SKILL_ADVICE.items():
        if key in skill_lower or skill_lower in key:
            return advice
    return None
